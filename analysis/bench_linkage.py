#!/usr/bin/env python3
"""
bench_linkage.py — benchmark Game L (linkage) clustering variants with guardrails.

The harness's Memon grouping is degenerate: single-linkage over a mostly-zero
similarity matrix chains ~90% of fragments into one cluster and pads the group
count with singletons. Its F1 is an artefact of blob size, and it scores BELOW
the trivial "put everything in one cluster" strategy.

This script sweeps (similarity x linkage) combinations against both corpora and
applies two pass/fail guardrails:

  GATE 1 (prose, must PASS):  F1 > trivial one-big-cluster F1.
      If a method cannot beat doing nothing, it is still broken.

  GATE 2 (identifiers, must PASS): F1 within 2 sigma of the random baseline.
      There is genuinely no signal linking a name to its SSN, so a CORRECT
      method must still fail here. A method that lifts identifier linkage above
      chance has not fixed Memon — it fabricates signal, and would contaminate
      the identifier result the two-regime thesis rests on. This gate matters
      MORE than gate 1.

A variant is only trustworthy if it passes BOTH.

Usage:
    python bench_linkage.py
    python bench_linkage.py --runs 2000
"""

import argparse
import math
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import linkage as hier_linkage, fcluster
from scipy.spatial.distance import squareform

ROOT = Path(__file__).resolve().parent.parent          # repo root
sys.path.insert(0, str(ROOT / "harness"))

from loader import load_fragments, group_fragments_by_record   # noqa: E402
from scoring import score_linkage                              # noqa: E402
from orderers import text_similarity as word_bigram_jaccard    # noqa: E402  (current metric)
import harness as H                                            # noqa: E402


# ════════════════════════════════════════════════════════════════════════════
# Similarity variants
# ════════════════════════════════════════════════════════════════════════════

def _tok(t):
    return re.findall(r"[a-z0-9]+", t.lower())


def char_ngram_jaccard(a, b, n=4):
    """Character n-gram Jaccard. Much denser than word-bigram: short clinical
    sentences rarely share an adjacent WORD pair but routinely share character
    runs, so this returns a graded score instead of abstaining with 0.0."""
    A = {a[i:i+n] for i in range(len(a) - n + 1)}
    B = {b[i:i+n] for i in range(len(b) - n + 1)}
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def build_tfidf(frag_ids, text_by_id):
    """L2-normalised TF-IDF vectors -> cosine similarity via dot product.
    Weights shared RARE terms (a surname, a drug) far above shared common ones
    ('the patient'), which is exactly the discrimination linkage needs."""
    docs = {f: _tok(text_by_id[f]) for f in frag_ids}
    df = Counter()
    for toks in docs.values():
        df.update(set(toks))
    N = len(docs)
    vecs = {}
    for f, toks in docs.items():
        tf = Counter(toks)
        v = {}
        for t, c in tf.items():
            v[t] = (1 + math.log(c)) * math.log((N + 1) / (df[t] + 1))
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs[f] = {t: x / norm for t, x in v.items()}
    def sim(a, b):
        va, vb = vecs[a], vecs[b]
        if len(va) > len(vb):
            va, vb = vb, va
        return sum(x * vb.get(t, 0.0) for t, x in va.items())
    return sim


SIMILARITIES = {
    "word-bigram (current)": lambda ids, txt: (lambda a, b: word_bigram_jaccard(txt[a], txt[b])),
    "char-4gram":            lambda ids, txt: (lambda a, b: char_ngram_jaccard(txt[a], txt[b])),
    "tfidf-cosine":          lambda ids, txt: build_tfidf(ids, txt),
}


# ════════════════════════════════════════════════════════════════════════════
# Clustering
# ════════════════════════════════════════════════════════════════════════════

def cluster(frag_ids, sim_fn, n_groups, method, seed=42):
    """Agglomerative clustering into exactly n_groups via scipy.

    Tie-breaking matters here. On the identifier corpus almost every pairwise
    similarity is exactly 0.0, so every merge height ties and fcluster(maxclust)
    collapses to ONE cluster instead of n_groups — which scores the trivial
    one-big-cluster F1 and looks like signal where there is none. We add a
    deterministic jitter (1e-6, far below any real similarity difference) so
    ties resolve arbitrarily rather than degenerately: with no signal the result
    is a random-like partition sitting at the true chance floor, which is the
    honest answer.
    """
    n = len(frag_ids)
    rng = np.random.default_rng(seed)
    D = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = 1.0 - sim_fn(frag_ids[i], frag_ids[j])
            D[i, j] = D[j, i] = d
    D += rng.random((n, n)) * 1e-6          # break exact ties
    D = (D + D.T) / 2.0                     # keep it symmetric
    np.fill_diagonal(D, 0.0)
    Z = hier_linkage(squareform(D, checks=False), method=method)
    labels = fcluster(Z, t=n_groups, criterion="maxclust")
    groups = defaultdict(list)
    for idx, lab in enumerate(labels):
        groups[int(lab)].append(frag_ids[idx])
    return dict(groups)


def trivial_one_cluster_f1(frag_ids, true_groups):
    """The do-nothing strategy: every fragment in one cluster."""
    return score_linkage({0: list(frag_ids)}, true_groups)


# ════════════════════════════════════════════════════════════════════════════

def load(kind):
    if kind == "prose":
        p = ROOT / "data" / "prose" / "prose_fragments.jsonl"
    else:
        p = ROOT / "data" / "identifier" / "fragments.jsonl"
    frs = load_fragments(p)
    return frs, group_fragments_by_record(frs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=2000,
                    help="random-baseline runs (for the identifier 2-sigma gate)")
    args = ap.parse_args()

    corpora = {}
    for kind in ("prose", "identifier"):
        frs, true_groups = load(kind)
        ids = [f["fragment_id"] for f in frs]
        txt = {f["fragment_id"]: f["text"] for f in frs}
        triv = trivial_one_cluster_f1(ids, true_groups)
        corpora[kind] = dict(frs=frs, ids=ids, txt=txt, tg=true_groups, triv=triv)
        print(f"{kind:11s}: {len(ids)} fragments / {len(true_groups)} records "
              f"| trivial one-cluster F1 = {triv['f1']:.4f}")

    # Random floor on identifiers -> the 2-sigma gate
    frs, tg = corpora["identifier"]["frs"], corpora["identifier"]["tg"]
    true_order = {r: v for r, v in tg.items()}   # ordering unused here
    print(f"\nrandom baseline on identifiers ({args.runs:,} runs) ...")
    _, _, _, l_fs = H.eval_random(frs, true_order, tg, args.runs)
    rnd_mean, rnd_sd = float(l_fs.mean()), float(l_fs.std(ddof=1))
    id_gate = rnd_mean + 2 * rnd_sd
    print(f"  identifier random F1 = {rnd_mean:.4f} +- {rnd_sd:.4f}"
          f"  -> GATE 2 ceiling (2 sigma) = {id_gate:.4f}")

    prose_gate = corpora["prose"]["triv"]["f1"]
    print(f"  prose trivial F1     = {prose_gate:.4f}"
          f"  -> GATE 1 floor = {prose_gate:.4f}")

    # ── sweep ────────────────────────────────────────────────────────────────
    print("\n" + "=" * 96)
    print(f"{'similarity':22s} {'linkage':9s} | {'PROSE f1':>9s} {'largest':>8s} |"
          f" {'IDENT f1':>9s} {'largest':>8s} | {'gate1':>6s} {'gate2':>6s}  verdict")
    print("=" * 96)

    rows = []
    for sname, sfactory in SIMILARITIES.items():
        for method in ("single", "average", "complete"):
            res = {}
            for kind in ("prose", "identifier"):
                c = corpora[kind]
                sim = sfactory(c["ids"], c["txt"])
                g = cluster(c["ids"], sim, len(c["tg"]), method)
                s = score_linkage(g, c["tg"])
                res[kind] = (s["f1"], max(len(v) for v in g.values()), len(c["ids"]))
            p_f1, p_big, p_n = res["prose"]
            i_f1, i_big, i_n = res["identifier"]
            g1 = p_f1 > prose_gate
            g2 = i_f1 <= id_gate
            # A cluster many times the expected size means the partition is a blob;
            # its F1 reflects blob arithmetic, not linkage, whatever the gates say.
            p_exp = p_n / len(corpora["prose"]["tg"])
            i_exp = i_n / len(corpora["identifier"]["tg"])
            degen = (p_big > 5 * p_exp) or (i_big > 5 * i_exp)
            if degen:
                verdict = "DEGENERATE"
            elif g1 and g2:
                verdict = "PASS"
            elif g1 and not g2:
                verdict = "OVERFIT"
            else:
                verdict = "fail"
            rows.append((sname, method, p_f1, p_big, p_n, i_f1, i_big, i_n, g1, g2, verdict))
            print(f"{sname:22s} {method:9s} | {p_f1:9.4f} {p_big:4d}/{p_n:<4d}|"
                  f" {i_f1:9.4f} {i_big:4d}/{i_n:<4d}|"
                  f" {'PASS' if g1 else 'FAIL':>6s} {'PASS' if g2 else 'FAIL':>6s}  {verdict}")

    print("=" * 96)
    winners = [r for r in rows if r[-1] == "PASS"]
    if winners:
        best = max(winners, key=lambda r: r[2])
        print(f"\nBEST PASSING: {best[0]} + {best[1]} linkage")
        print(f"  prose F1      {best[2]:.4f}  (must beat trivial {prose_gate:.4f})  -> beats it by "
              f"{best[2]-prose_gate:+.4f}")
        print(f"  identifier F1 {best[5]:.4f}  (must stay <= {id_gate:.4f})        -> at floor")
    else:
        print("\nNO VARIANT PASSED BOTH GATES.")
        of = [r for r in rows if r[-1] == "OVERFIT"]
        if of:
            print("  Variants beating trivial on prose but ALSO lifting identifiers "
                  "above chance (overfit — do not use):")
            for r in of:
                print(f"    {r[0]} + {r[1]}: prose {r[2]:.4f}, identifier {r[5]:.4f} > {id_gate:.4f}")


if __name__ == "__main__":
    main()
