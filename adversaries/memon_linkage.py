#!/usr/bin/env python3
"""
memon_linkage.py — Game L (linkage) grouping, selectable between the LEGACY
(degenerate) implementation and the FIXED one.

Both variants are kept so the same code can reproduce either number for
auditability. Nothing here modifies harness/orderers.py — the legacy path
IMPORTS the live functions unchanged, so "legacy" is guaranteed to be the
number the team has already seen.

    variant="legacy-greedy"  -> harness greedy_grouping  (single-linkage, degenerate)
    variant="legacy-mst"     -> harness mst_grouping     (MST-cut, degenerate)
    variant="fixed"          -> TF-IDF cosine + average linkage  (validated)

ORDERING IS NOT TOUCHED. This module only provides Game L grouping.

Why the legacy path is degenerate
---------------------------------
`greedy_grouping` is single-linkage: two clusters merge if ANY member pair is
similar. Over a word-bigram Jaccard matrix that is ~83% exact zeros, the few
non-zero pairs chain most of the corpus into one component; the requested group
count is then met by shedding singletons. Result: up to 91% of a corpus in one
cluster, an F1 equal to the trivial "one big cluster" strategy, and precision
pinned at the random floor. `mst_grouping` fails equivalently — cutting the
weakest MST edges removes leaves rather than splitting the blob.

Why the fix works
-----------------
1. TF-IDF cosine replaces word-bigram Jaccard. Jaccard over adjacent word pairs
   abstains (0.0) on most sentence pairs; TF-IDF gives a graded score on nearly
   every pair and weights shared RARE terms (a drug, a diagnosis) above shared
   boilerplate ("the patient").
2. Average linkage replaces single linkage, so clusters merge on aggregate
   similarity and a few spurious edges cannot weld the corpus together.
3. Deterministic jitter breaks exact ties. With an all-zero similarity matrix
   (the identifier corpus) every merge height ties and scipy's fcluster collapses
   to ONE cluster — which scores the trivial F1 and looks like signal where there
   is none. Jitter makes no-signal data resolve to a random-like partition at the
   true chance floor, which is the honest answer.
"""

import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from scipy.cluster.hierarchy import linkage as hier_linkage, fcluster
from scipy.spatial.distance import squareform

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness"))
from orderers import greedy_grouping, mst_grouping     # noqa: E402  (live code, unmodified)

VARIANTS = ("legacy-greedy", "legacy-mst", "fixed")


def _tok(t):
    return re.findall(r"[a-z0-9]+", t.lower())


def build_tfidf(frag_ids, text_by_id):
    """L2-normalised TF-IDF vectors; cosine similarity = dot product."""
    docs = {f: _tok(text_by_id[f]) for f in frag_ids}
    df = Counter()
    for toks in docs.values():
        df.update(set(toks))
    N = len(docs)
    vecs = {}
    for f, toks in docs.items():
        tf = Counter(toks)
        v = {t: (1 + math.log(c)) * math.log((N + 1) / (df[t] + 1))
             for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs[f] = {t: x / norm for t, x in v.items()}

    def sim(a, b):
        va, vb = vecs[a], vecs[b]
        if len(va) > len(vb):
            va, vb = vb, va
        return sum(x * vb.get(t, 0.0) for t, x in va.items())
    return sim


def _agglomerative(frag_ids, sim_fn, n_groups, method="average", seed=42):
    n = len(frag_ids)
    rng = np.random.default_rng(seed)
    D = np.empty((n, n), dtype=np.float64)
    for i in range(n):
        D[i, i] = 0.0
        for j in range(i + 1, n):
            d = 1.0 - sim_fn(frag_ids[i], frag_ids[j])
            D[i, j] = D[j, i] = d
    D += rng.random((n, n)) * 1e-6          # break exact ties (see module docstring)
    D = (D + D.T) / 2.0
    np.fill_diagonal(D, 0.0)
    Z = hier_linkage(squareform(D, checks=False), method=method)
    labels = fcluster(Z, t=n_groups, criterion="maxclust")
    groups = defaultdict(list)
    for idx, lab in enumerate(labels):
        groups[int(lab)].append(frag_ids[idx])
    return dict(groups)


def memon_grouping(fragments, n_groups, variant="fixed", seed=42):
    """Group fragments into n_groups. Returns {int: [fragment_id, ...]}.

    fragments: list of {"fragment_id", "text", ...}
    variant:   one of VARIANTS
    """
    if variant not in VARIANTS:
        raise ValueError(f"variant must be one of {VARIANTS}, got {variant!r}")

    if variant == "legacy-greedy":
        return greedy_grouping(fragments, n_groups)
    if variant == "legacy-mst":
        return mst_grouping(fragments, n_groups)

    frag_ids = [f["fragment_id"] for f in fragments]
    text_by_id = {f["fragment_id"]: f["text"] for f in fragments}
    sim = build_tfidf(frag_ids, text_by_id)
    return _agglomerative(frag_ids, sim, n_groups, method="average", seed=seed)


def partition_stats(groups, n_fragments):
    """Degeneracy diagnostics — an F1 means nothing if the partition is a blob."""
    sizes = sorted((len(v) for v in groups.values()), reverse=True)
    return {
        "n_groups":    len(groups),
        "largest":     sizes[0] if sizes else 0,
        "largest_pct": 100.0 * (sizes[0] / n_fragments) if sizes else 0.0,
        "singletons":  sum(1 for s in sizes if s == 1),
    }
