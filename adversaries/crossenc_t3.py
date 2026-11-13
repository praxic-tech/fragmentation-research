"""
crossenc_t3.py — tier 3 of the strong non-LLM attacker ladder (RUN_DECISIONS D19,
"tier 3 design"). A fine-tuned biomedical BERT cross-encoder plus a decoder.

The model reads ONE PAIR of fragments, "[CLS] A [SEP] B [SEP]", and outputs
five numbers:
    same      logit: A and B come from the same document
    precedes  logit: A is earlier than B in that document (trained on same-document pairs)
    adjacent  logit: B is the fragment immediately after A
    posA,posB pre-sigmoid relative position of A and of B in their own documents
It never sees an id, a label or a pool: only the two texts. Everything the
attacker knows about a pool is the m x m matrices of those outputs.

The decoder turns the matrices into exactly N ordered groups. Two decoders are
implemented; which one runs on evaluation is chosen on the development split of
the disjoint corpus (runs/t3_dev.py), never on an evaluation pool:
    cluster-rank  cluster on the symmetrised same-document probability to
                  exactly N groups, then order each group
    path-cover    N vertex-disjoint paths over the adjacency scores (greedy
                  edge selection + one-edge exchange local search)

New code only. Nothing here edits or replaces an existing attacker.
torch / transformers are imported lazily so the decoder runs anywhere numpy does.
"""

import hashlib
import json
import math
import os
import sys
from collections import Counter

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "harness"))
sys.path.insert(0, os.path.join(ROOT, "adversaries"))

from masking import assert_ids_masked, mask_fragment_ids   # noqa: E402

MODEL_NAME = "microsoft/BiomedNLP-BiomedBERT-base-uncased-abstract-fulltext"
MODEL_REV = "e1354b7a3a09615f6aba48dfad4b7a613eef7062"
DATA_SHA256 = "47a35e0c3c620bf13faca112d93c84c9bbaafe477231802eab809420ddba0110"
SIDE_CAP = 80            # word pieces kept per fragment (head of the fragment)
PAD_MULT = 8             # sequences padded to a multiple of 8 (few distinct shapes)
N_OUT = 5                # same, precedes, adjacent, posA, posB
I_SAME, I_PREC, I_ADJ, I_POSA, I_POSB = range(5)


# ── model (torch, lazy) ───────────────────────────────────────────────────────

def build_model(encoder):
    import torch.nn as nn

    class PairModel(nn.Module):
        def __init__(self, enc):
            super().__init__()
            self.encoder = enc
            self.drop = nn.Dropout(0.1)
            self.head = nn.Linear(enc.config.hidden_size, N_OUT)

        def forward(self, input_ids, attention_mask, token_type_ids):
            h = self.encoder(input_ids=input_ids, attention_mask=attention_mask,
                             token_type_ids=token_type_ids).last_hidden_state[:, 0]
            return self.head(self.drop(h))

    return PairModel(encoder)


def new_model(smoke=False):
    """Pretrained encoder at the pinned revision (or a tiny random one for smoke tests)."""
    from transformers import AutoConfig, AutoModel, BertConfig, BertModel
    if smoke:
        vocab = AutoConfig.from_pretrained(MODEL_NAME, revision=MODEL_REV).vocab_size
        cfg = BertConfig(vocab_size=vocab, hidden_size=64, num_hidden_layers=2, num_attention_heads=2,
                         intermediate_size=128, max_position_embeddings=512)
        return build_model(BertModel(cfg, add_pooling_layer=False))
    return build_model(AutoModel.from_pretrained(MODEL_NAME, revision=MODEL_REV, add_pooling_layer=False))


def load_tokenizer(model_dir=None):
    from transformers import AutoTokenizer
    if model_dir:
        return AutoTokenizer.from_pretrained(model_dir)
    return AutoTokenizer.from_pretrained(MODEL_NAME, revision=MODEL_REV)


def save_model(model, tokenizer, out_dir):
    from safetensors.torch import save_file
    os.makedirs(out_dir, exist_ok=True)
    state = {k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()}
    save_file(state, os.path.join(out_dir, "pair_model.safetensors"))
    with open(os.path.join(out_dir, "encoder_config.json"), "w", encoding="utf-8") as fh:
        json.dump(model.encoder.config.to_dict(), fh, indent=1, default=str)
    tokenizer.save_pretrained(out_dir)


def load_model(model_dir):
    from safetensors.torch import load_file
    from transformers import BertConfig, BertModel
    cfg = BertConfig.from_dict(json.load(open(os.path.join(model_dir, "encoder_config.json"), encoding="utf-8")))
    model = build_model(BertModel(cfg, add_pooling_layer=False))
    model.load_state_dict(load_file(os.path.join(model_dir, "pair_model.safetensors")))
    return model.eval()


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ── tokens and pair batches (numpy) ───────────────────────────────────────────

def encode_fragments(tokenizer, texts, chunk=20000):
    """Word-piece ids per text, no special tokens, head-truncated to SIDE_CAP."""
    out = []
    for i in range(0, len(texts), chunk):
        enc = tokenizer(list(texts[i:i + chunk]), add_special_tokens=False, truncation=True,
                        max_length=SIDE_CAP, return_attention_mask=False, return_token_type_ids=False)
        out.extend(np.asarray(x, dtype=np.int64) for x in enc["input_ids"])
    return out


def assemble(tok_a, tok_b, cls_id, sep_id, pad_id):
    """[CLS] A [SEP] B [SEP], padded to a multiple of PAD_MULT."""
    n = len(tok_a)
    longest = max(len(a) + len(b) for a, b in zip(tok_a, tok_b)) + 3
    L = int(math.ceil(longest / PAD_MULT) * PAD_MULT)
    ids = np.full((n, L), pad_id, dtype=np.int64)
    mask = np.zeros((n, L), dtype=np.int64)
    types = np.zeros((n, L), dtype=np.int64)
    for r, (a, b) in enumerate(zip(tok_a, tok_b)):
        la, lb = len(a), len(b)
        ids[r, 0] = cls_id
        ids[r, 1:1 + la] = a
        ids[r, 1 + la] = sep_id
        ids[r, 2 + la:2 + la + lb] = b
        ids[r, 2 + la + lb] = sep_id
        mask[r, :3 + la + lb] = 1
        types[r, 2 + la:3 + la + lb] = 1
    return ids, mask, types


def torch_infer_fn(model, device):
    import torch
    amp = device.type == "cuda"

    def infer(ids, mask, types):
        with torch.no_grad(), torch.autocast(device_type=device.type, enabled=amp):
            out = model(torch.from_numpy(ids).to(device), torch.from_numpy(mask).to(device),
                        torch.from_numpy(types).to(device))
        return out.float().cpu().numpy()
    return infer


def onnx_infer_fn(onnx_path, providers=None):
    import onnxruntime as ort
    avail = ort.get_available_providers()
    want = providers or [p for p in ("DmlExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider")
                         if p in avail]
    sess = ort.InferenceSession(onnx_path, providers=want)

    def infer(ids, mask, types):
        return sess.run(["out"], {"input_ids": ids, "attention_mask": mask, "token_type_ids": types})[0]
    infer.providers = sess.get_providers()
    return infer


def texts_sha(texts):
    h = hashlib.sha256()
    for t in texts:
        h.update(t.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def score_texts(texts, tokenizer, infer, max_batch=512, token_budget=40000):
    """All ordered pairs of `texts` (in the caller's order) through the model.

    Identical texts are scored once: the model sees text only, so two fragments
    with the same text get the same scores by construction.
    Returns S, P, A (m x m float32 logits, row = first fragment, column =
    second, diagonal 0) and pos (m, mean predicted relative position).
    """
    m = len(texts)
    uniq = sorted(set(texts))
    uidx = {t: i for i, t in enumerate(uniq)}
    u = len(uniq)
    dup = {uidx[t] for t, c in Counter(texts).items() if c > 1}
    toks = encode_fragments(tokenizer, uniq)
    lens = np.array([len(t) for t in toks])
    aa, bb = np.meshgrid(np.arange(u), np.arange(u), indexing="ij")
    keep = (aa != bb) | np.isin(aa, list(dup))
    a_idx, b_idx = aa[keep], bb[keep]
    order = np.argsort(lens[a_idx] + lens[b_idx], kind="stable")
    a_idx, b_idx = a_idx[order], b_idx[order]
    out = np.zeros((u, u, N_OUT), dtype=np.float32)
    cls_id, sep_id, pad_id = tokenizer.cls_token_id, tokenizer.sep_token_id, tokenizer.pad_token_id
    i = 0
    while i < len(a_idx):
        L = lens[a_idx[min(i + max_batch, len(a_idx)) - 1]] + lens[b_idx[min(i + max_batch, len(a_idx)) - 1]] + 3
        bs = int(max(1, min(max_batch, token_budget // max(int(L), 1))))
        ja, jb = a_idx[i:i + bs], b_idx[i:i + bs]
        ids, mask, types = assemble([toks[k] for k in ja], [toks[k] for k in jb], cls_id, sep_id, pad_id)
        out[ja, jb] = infer(ids, mask, types)
        i += bs
    f = np.array([uidx[t] for t in texts])
    full = out[f][:, f]                                  # m x m x 5
    off = ~np.eye(m, dtype=bool)
    sig = 1.0 / (1.0 + np.exp(-full[:, :, I_POSA:].astype(np.float64)))
    pa = np.where(off, sig[:, :, 0], 0.0).sum(1)         # i as first fragment
    pb = np.where(off, sig[:, :, 1], 0.0).sum(0)         # i as second fragment
    pos = (pa + pb) / max(2 * (m - 1), 1)
    S, P, A = (np.where(off, full[:, :, k], 0.0).astype(np.float32) for k in (I_SAME, I_PREC, I_ADJ))
    return {"S": S, "P": P, "A": A, "pos": pos.astype(np.float32), "n_pairs_scored": int(len(a_idx))}


# score store: one npz per unit, named by the SHA-256 of its texts in masked order

def store_path(store_dir, sha):
    return os.path.join(store_dir, sha[:2], sha + ".npz")


def store_save(store_dir, texts, sc):
    sha = texts_sha(texts)
    p = store_path(store_dir, sha)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp.npz"
    np.savez_compressed(tmp, S=sc["S"], P=sc["P"], A=sc["A"], pos=sc["pos"],
                        n=np.int64(len(texts)), n_pairs_scored=np.int64(sc["n_pairs_scored"]))
    os.replace(tmp, p)
    return sha


def store_load(store_dir, texts):
    p = store_path(store_dir, texts_sha(texts))
    if not os.path.exists(p):
        return None
    z = np.load(p)
    if int(z["n"]) != len(texts):
        raise AssertionError(f"score file {p} is for {int(z['n'])} texts, not {len(texts)}")
    return {k: z[k] for k in ("S", "P", "A", "pos")}


# ── decoders (numpy / scipy / sklearn; indices are in masked-alias order) ─────

def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.asarray(x, dtype=np.float64)))


def same_prob(S):
    W = _sigmoid((S + S.T) / 2.0)
    np.fill_diagonal(W, 0.0)
    return W


def before_logit(P):
    """R[i, j] > 0: i is earlier than j. Antisymmetric by construction."""
    return (P.astype(np.float64) - P.T.astype(np.float64)) / 2.0


def _ensure_n(labels, W, n):
    """Exactly n non-empty clusters, labels 0..n-1 (splits the loosest member off the largest)."""
    labels = np.unique(labels, return_inverse=True)[1]
    while labels.max() + 1 < min(n, len(labels)):
        big = np.bincount(labels).argmax()
        mem = np.flatnonzero(labels == big)
        loose = mem[np.argmin(W[np.ix_(mem, mem)].sum(1))]      # first min = lowest alias
        labels[loose] = labels.max() + 1
    return labels


def group_agglo(W, n):
    from scipy.cluster.hierarchy import cut_tree, linkage
    from scipy.spatial.distance import squareform
    D = 1.0 - W
    np.fill_diagonal(D, 0.0)
    Z = linkage(squareform(D, checks=False), method="average")
    return _ensure_n(cut_tree(Z, n_clusters=n).ravel(), W, n)


def group_spectral(W, n, seed=42):
    from sklearn.cluster import SpectralClustering
    A = W + 1e-6
    np.fill_diagonal(A, 0.0)
    sc = SpectralClustering(n_clusters=n, affinity="precomputed", assign_labels="cluster_qr", random_state=seed)
    return _ensure_n(sc.fit_predict(A), W, n)


def refine(labels, W, rounds=20):
    """Move each fragment to the cluster it has the highest mean same-probability
    with (itself excluded); sequential, in alias order; never empties a cluster."""
    labels = labels.copy()
    n = labels.max() + 1
    m = len(labels)
    for _ in range(rounds):
        moved = False
        for i in range(m):
            cur = labels[i]
            cnt = np.bincount(labels, minlength=n).astype(np.float64)
            if cnt[cur] <= 1:
                continue
            sums = np.bincount(labels, weights=W[i], minlength=n)      # W[i, i] = 0
            cnt[cur] -= 1
            mean = np.where(cnt > 0, sums / np.maximum(cnt, 1), -1.0)
            best = int(np.argmax(mean))                                # first max = lowest label
            if best != cur and mean[best] > mean[cur]:
                labels[i] = best
                moved = True
        if not moved:
            break
    return labels


def order_borda(idx, R):
    """Most-often-earlier first: sum over the group of tanh(R/2) = 2 p(before) - 1."""
    idx = list(idx)
    if len(idx) <= 1:
        return idx
    sc = np.tanh(R[np.ix_(idx, idx)] / 2.0).sum(1)
    return [i for _s, i in sorted(zip(-sc, idx))]                      # ties -> lower alias


def order_position(idx, pos):
    return [i for _p, i in sorted(zip(pos[list(idx)], idx))]


def path_cover(A, n_paths, sweeps=50):
    """n_paths vertex-disjoint paths maximising the summed log p(adjacent).

    Greedy: take edges best-first when the tail has no successor, the head no
    predecessor and they are in different paths, until m - n_paths edges are in.
    Then one-edge exchange: remove an edge and add the best legal edge between
    two path ends, while that raises the total. Deterministic; ties go to the
    lower flat index, i.e. the lower masked alias.
    """
    m = A.shape[0]
    k = min(n_paths, m)
    w = -np.logaddexp(0.0, -A.astype(np.float64))        # log sigmoid
    np.fill_diagonal(w, -np.inf)
    succ = np.full(m, -1)
    pred = np.full(m, -1)
    comp = np.arange(m)

    def find(x):
        while comp[x] != x:
            comp[x] = comp[comp[x]]
            x = comp[x]
        return x

    need = m - k
    if need > 0:
        for flat in np.argsort(-w, axis=None, kind="stable"):
            i, j = divmod(int(flat), m)
            if i == j or succ[i] != -1 or pred[j] != -1:
                continue
            ri, rj = find(i), find(j)
            if ri == rj:
                continue
            succ[i], pred[j] = j, i
            comp[ri] = rj
            need -= 1
            if need == 0:
                break

    def paths():
        out = []
        for h in range(m):
            if pred[h] == -1:
                p, x = [], h
                while x != -1:
                    p.append(x)
                    x = succ[x]
                out.append(p)
        return out

    for _ in range(sweeps):
        improved = False
        for a in range(m):
            b = succ[a]
            if b == -1:
                continue
            succ[a], pred[b] = -1, -1                    # cut a -> b
            ps = paths()
            tails = [p[-1] for p in ps]
            heads = [p[0] for p in ps]
            sub = w[np.ix_(tails, heads)].copy()
            np.fill_diagonal(sub, -np.inf)               # same path: would close a cycle
            flat = int(np.argmax(sub))
            t, h = tails[flat // len(ps)], heads[flat % len(ps)]
            if sub.flat[flat] > w[a, b] + 1e-12:
                succ[t], pred[h] = h, t
                improved = True
            else:
                succ[a], pred[b] = b, a
        if not improved:
            break
    return sorted(paths(), key=lambda p: min(p))


ORDERERS = ("borda", "position", "path1")
GROUPERS = ("agglo", "spectral")


def order_group(idx, sc, how):
    idx = sorted(idx)
    if len(idx) <= 1:
        return list(idx)
    if how == "borda":
        return order_borda(idx, before_logit(sc["P"]))
    if how == "position":
        return order_position(idx, sc["pos"])
    if how == "path1":
        (p,) = path_cover(sc["A"][np.ix_(idx, idx)], 1)
        return [idx[i] for i in p]
    raise ValueError(how)


def group_only(sc, n_docs, grouper, do_refine, seed=42):
    m = sc["S"].shape[0]
    if m <= n_docs:
        return np.arange(m)
    W = same_prob(sc["S"])
    labels = group_agglo(W, n_docs) if grouper == "agglo" else group_spectral(W, n_docs, seed)
    return refine(labels, W) if do_refine else labels


def decode(sc, n_docs, cfg, seed=42):
    """Ordered groups of indices (masked-alias order) under a frozen config:
    {"decoder": "cluster-rank"|"path-cover", "grouper", "refine", "orderer"}."""
    m = sc["S"].shape[0]
    if cfg["decoder"] == "path-cover":
        return path_cover(sc["A"], n_docs)
    labels = group_only(sc, n_docs, cfg["grouper"], cfg["refine"], seed)
    groups = [np.flatnonzero(labels == lab).tolist() for lab in range(labels.max() + 1)]
    groups = sorted((g for g in groups if g), key=lambda g: g[0])
    out = [order_group(g, sc, cfg["orderer"]) for g in groups]
    assert sorted(x for g in out for x in g) == list(range(m))
    return out


# ── attacker wrappers (masking, as in classical_t0) ───────────────────────────

def masked_view(fragments, seed=42, mask_seed=None):
    """What the attacker works on: sorted masked ids, their texts, and the map back."""
    masked, id_map = mask_fragment_ids(fragments, seed=seed if mask_seed is None else mask_seed)
    ids = sorted(f["fragment_id"] for f in masked)
    text_by_id = {f["fragment_id"]: f["text"] for f in masked}
    return ids, [text_by_id[i] for i in ids], dict(id_map)


def attack_from_scores(fragments, n_docs, store_dir, cfg, seed=42, mask_seed=None):
    ids, texts, back = masked_view(fragments, seed, mask_seed)
    assert_ids_masked(ids, where="crossenc_t3.attack_from_scores")
    sc = store_load(store_dir, texts)
    if sc is None:
        raise FileNotFoundError(f"no pair scores for unit with text sha {texts_sha(texts)[:16]}")
    groups = decode(sc, n_docs, cfg, seed)
    placed = [x for g in groups for x in g]
    assert sorted(placed) == list(range(len(ids))), "T3 dropped or duplicated ids"
    sizes = sorted((len(g) for g in groups), reverse=True)
    return [[back[ids[i]] for i in g] for g in groups], {
        "attacker": "T3-crossenc", **cfg, "n_fragments": len(ids), "n_docs_given": n_docs,
        "n_groups": len(groups), "largest": sizes[0] if sizes else 0,
        "singletons": sum(1 for s in sizes if s == 1)}
