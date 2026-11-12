"""
classical_t0.py — tier 0 of the strong non-LLM attacker ladder (RUN_DECISIONS D19).

Two attackers, both main comparisons (D19), both new code: memon.py,
memon_joint.py, memon_linkage.py and embedding_joint.py are imported, never
edited.

T0-PUP  Pal & Memon's Parallel Unique Path decoder, as published, on the frozen
        character n-gram boundary statistic (n = d = 2). It reassembles all N
        documents at once: N paths, each proposes its best unused successor, the
        globally best proposal is committed. Groups are the paths. No training,
        no free parameter. This is the decoder the "Memon-inspired" attacker
        cites but does not implement (memon_joint orders each cluster with
        order_from_sim instead).

T0-classical  The strongest classical attacker we could specify without a
        neural network: case-specific content terms + kNN spectral clustering to
        exactly N for grouping; a relative-position regressor trained on disjoint
        case reports for ordering. Its three tuned values come from the
        development split of the disjoint corpus only.

Masking happens here, as in memon_joint: an offline attacker builds no prompt,
so nothing else would stop raw ids reaching a tie rule. Every tie below is
broken by the masked alias, which carries no order.
"""

import hashlib
import math
import os
import re
import sys
from collections import Counter

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "harness"))
sys.path.insert(0, os.path.join(ROOT, "adversaries"))

from masking import assert_ids_masked, mask_fragment_ids   # noqa: E402
from memon import build_model, build_vocab, score_pair     # noqa: E402
from memon_linkage import build_tfidf                      # noqa: E402

N_GRAM = 2      # frozen Memon-inspired order (D12)
D_STEPS = 2


# ── T0-PUP ────────────────────────────────────────────────────────────────────

def boundary_matrix(ids, text_by_id, model, vocab, n=N_GRAM, d=D_STEPS):
    """S[i, j] = score_pair(i -> j), -inf on the diagonal.

    With d <= n, score_pair reads only the last n characters of A and the first
    d of B (plus whether A has n characters at all), so scores are cached on
    that key. Same numbers as calling score_pair on the full texts.
    """
    m = len(ids)
    tails = [text_by_id[f][-n:] if len(text_by_id[f]) >= n else None for f in ids]
    heads = [text_by_id[f][:d] for f in ids]
    cache = {}
    S = np.full((m, m), -np.inf)
    for i in range(m):
        for j in range(m):
            if i == j:
                continue
            key = (tails[i], heads[j])
            if key not in cache:
                cache[key] = -math.inf if tails[i] is None else score_pair(
                    tails[i], heads[j], model, vocab, n, d)
            S[i, j] = cache[key]
    return S


def pup(S, n_paths):
    """Parallel Unique Path over score matrix S (higher = better successor).

    Rows/columns are in masked-alias order, so index order is a neutral tie
    rule. Starts: the n_paths fragments whose best incoming score is lowest
    (least predictable from any other fragment), standing in for file headers.
    """
    m = S.shape[0]
    k = min(n_paths, m)
    best_in = np.where(np.isfinite(S), S, -1e300).max(axis=0)
    starts = sorted(range(m), key=lambda j: (best_in[j], j))[:k]
    used = np.zeros(m, dtype=bool)
    used[starts] = True
    paths = [[s] for s in starts]
    big_neg = -1e300
    while not used.all():
        best = None                                   # (score, -path, cand)
        for p, path in enumerate(paths):
            row = np.where(np.isfinite(S[path[-1]]), S[path[-1]], big_neg)
            row = np.where(used, -np.inf, row)
            c = int(np.argmax(row))                   # first max = lowest alias
            cand = (row[c], -p, -c)
            if best is None or cand > best:
                best = cand
        _s, negp, negc = best
        paths[-negp].append(-negc)
        used[-negc] = True
    return paths


def attack_pup(fragments, n_docs, seed=42, mask_seed=None):
    masked, id_map = mask_fragment_ids(fragments, seed=seed if mask_seed is None else mask_seed)
    back = dict(id_map)
    ids = sorted(f["fragment_id"] for f in masked)
    assert_ids_masked(ids, where="classical_t0.attack_pup")
    text_by_id = {f["fragment_id"]: f["text"] for f in masked}
    model, vocab = build_model(masked, N_GRAM), build_vocab(masked)
    S = boundary_matrix(ids, text_by_id, model, vocab)
    paths = pup(S, n_docs)
    groups = [[ids[i] for i in p] for p in paths]
    placed = [x for g in groups for x in g]
    assert sorted(placed) == ids, "T0-PUP dropped or duplicated ids"
    finite = np.isfinite(S)
    np.fill_diagonal(finite, True)
    sizes = sorted((len(g) for g in groups), reverse=True)
    return [[back[x] for x in g] for g in groups], {
        "attacker": "T0-PUP", "n": N_GRAM, "d": D_STEPS, "n_fragments": len(ids),
        "n_docs_given": n_docs, "n_groups": len(groups), "largest": sizes[0] if sizes else 0,
        "singletons": sum(1 for s in sizes if s == 1),
        "share_pairs_unscorable": float(1.0 - finite.mean())}


# ── T0-classical: grouping ────────────────────────────────────────────────────

_TOKEN = re.compile(r"[a-z0-9]+(?:[.\-/][a-z0-9]+)*")


def _stop_words():
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
    return ENGLISH_STOP_WORDS


def content_tokens(text, stop=None):
    stop = _stop_words() if stop is None else stop
    return [t for t in _TOKEN.findall(text.lower()) if len(t) > 1 and t not in stop]


def content_vectors(ids, text_by_id, n_docs, c):
    """Rows: L2 TF-IDF over terms in >= 2 and <= c*m/N fragments of this pool."""
    stop = _stop_words()
    toks = [content_tokens(text_by_id[f], stop) for f in ids]
    m = len(ids)
    df = Counter()
    for t in toks:
        df.update(set(t))
    cap = c * m / max(n_docs, 1)
    vocab = {t: i for i, t in enumerate(sorted(t for t, v in df.items() if 2 <= v <= cap))}
    X = np.zeros((m, len(vocab)))
    for r, t in enumerate(toks):
        for term, cnt in Counter(t).items():
            j = vocab.get(term)
            if j is not None:
                X[r, j] = (1.0 + math.log(cnt)) * (math.log((1 + m) / (1 + df[term])) + 1.0)
    norms = np.linalg.norm(X, axis=1)
    has = norms > 0
    X[has] /= norms[has, None]
    return X, has, len(vocab)


def knn_affinity(X, k):
    """Symmetric kNN graph on cosine similarity; a 1e-6 floor keeps it connected."""
    S = X @ X.T
    np.fill_diagonal(S, 0.0)
    m = S.shape[0]
    A = np.zeros_like(S)
    kk = min(k, m - 1)
    for i in range(m):
        nb = np.argsort(-S[i], kind="stable")[:kk]
        A[i, nb] = np.maximum(S[i, nb], 0.0)
    A = np.maximum(A, A.T)
    A += 1e-6
    np.fill_diagonal(A, 0.0)
    return A


def group_classical(ids, text_by_id, n_docs, k, c, seed=42):
    from sklearn.cluster import SpectralClustering
    m = len(ids)
    if m <= n_docs:
        return [[f] for f in ids], {"anchored": m, "kept_terms": 0}
    X, has, n_terms = content_vectors(ids, text_by_id, n_docs, c)
    anchored = [i for i in range(m) if has[i]]
    labels = np.full(m, -1)
    if len(anchored) > n_docs:
        A = knn_affinity(X[anchored], k)
        sc = SpectralClustering(n_clusters=n_docs, affinity="precomputed",
                                assign_labels="cluster_qr", random_state=seed)
        labels[anchored] = sc.fit_predict(A)
    else:                                   # degenerate: too few content-bearing fragments
        for r, i in enumerate(anchored):
            labels[i] = r
    clusters = {lab: [ids[i] for i in range(m) if labels[i] == lab] for lab in set(labels) if lab >= 0}
    # fragments with no kept term: highest mean full-vocabulary TF-IDF similarity
    loose = [ids[i] for i in range(m) if labels[i] < 0]
    if loose:
        sim = build_tfidf(ids, text_by_id)
        order = sorted(clusters, key=lambda lab: min(clusters[lab]))
        add = {lab: [] for lab in order}
        for f in loose:
            if order:
                best = max(order, key=lambda lab: (np.mean([sim(f, g) for g in clusters[lab]]),
                                                   -order.index(lab)))
                add[best].append(f)
            else:
                clusters.setdefault(0, []).append(f)
        for lab in order:
            clusters[lab].extend(add[lab])
    groups = sorted((sorted(v) for v in clusters.values() if v), key=lambda g: g[0])
    return groups, {"anchored": len(anchored), "loose": len(loose), "kept_terms": n_terms}


# ── T0-classical: ordering ────────────────────────────────────────────────────

class PositionModel:
    """Relative position in its document, from word 1-2-gram TF-IDF, ridge."""

    def __init__(self, alpha):
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import Ridge
        self.alpha = alpha
        self.vec = TfidfVectorizer(ngram_range=(1, 2), min_df=5, sublinear_tf=True,
                                   lowercase=True, dtype=np.float32)
        self.reg = Ridge(alpha=alpha, solver="sparse_cg", random_state=0)

    @staticmethod
    def targets(docs):
        X, y = [], []
        for sents in docs:
            n = len(sents)
            for i, s in enumerate(sents):
                X.append(s)
                y.append(i / (n - 1) if n > 1 else 0.5)
        return X, np.asarray(y, dtype=np.float64)

    def fit(self, docs):
        X, y = self.targets(docs)
        self.reg.fit(self.vec.fit_transform(X), y)
        return self

    def predict(self, texts):
        return self.reg.predict(self.vec.transform(list(texts)))


def order_by_position(cluster, text_by_id, pos_model):
    if len(cluster) <= 1:
        return list(cluster)
    p = pos_model.predict([text_by_id[f] for f in cluster])
    return [f for _p, f in sorted(zip(p, cluster))]      # ties -> lower alias


def attack_classical(fragments, n_docs, pos_model, k, c, seed=42, mask_seed=None):
    masked, id_map = mask_fragment_ids(fragments, seed=seed if mask_seed is None else mask_seed)
    back = dict(id_map)
    ids = sorted(f["fragment_id"] for f in masked)
    assert_ids_masked(ids, where="classical_t0.attack_classical")
    text_by_id = {f["fragment_id"]: f["text"] for f in masked}
    groups, gtel = group_classical(ids, text_by_id, n_docs, k, c, seed=seed)
    ordered = [order_by_position(g, text_by_id, pos_model) for g in groups]
    placed = [x for g in ordered for x in g]
    assert sorted(placed) == ids, "T0-classical dropped or duplicated ids"
    sizes = sorted((len(g) for g in ordered), reverse=True)
    return [[back[x] for x in g] for g in ordered], {
        "attacker": "T0-classical", "k": k, "c": c, "alpha": pos_model.alpha,
        "n_fragments": len(ids), "n_docs_given": n_docs, "n_groups": len(ordered),
        "largest": sizes[0] if sizes else 0, "singletons": sum(1 for s in sizes if s == 1), **gtel}


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
