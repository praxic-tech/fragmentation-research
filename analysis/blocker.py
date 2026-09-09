"""
blocker.py — candidate generation at corpus scale, and how good it is.

The hierarchical attacker's first stage narrows 16,524 fragments down to a
manageable candidate set. Within a pool that is a dense O(n^2) scan, which is
fine at 178 fragments. Over the whole corpus it is 136,513,026 pairs, so it
needs an inverted index — and the blocker's quality then becomes the thing that
decides whether small-N evaluation describes anything real.

Without this measurement, small-N is an ORACLE-RESTRICTED regime: we hand the
attacker a clean pool containing exactly the fragments of N documents and
nothing else. A real blocker does not do that. It returns some true candidates,
misses others, and admits hard false positives that look similar precisely
because similarity is what selected them. Measuring one concrete blocker is what
turns "we assumed candidate sets of size N" into "candidate sets of size N are
what this blocker actually produces".

THE GRAPH DEFINITION IS FROZEN
------------------------------
"top-k graph -> block" is underspecified, and the choice changes both block size
and recall enormously. Declared, once:

    An UNDIRECTED EDGE exists between fragments i and j when EITHER endpoint
    selects the other in its top-k.  (union-kNN, not mutual-kNN)

    A CANDIDATE BLOCK is an uncapped raw CONNECTED COMPONENT of that edge set.

BOUNDED CONNECTIVITY, NOT RAW CONNECTIVITY
------------------------------------------
A top-k graph percolates. In the limit every fragment lands in one giant
component and "every document is connected" becomes trivially true while telling
you nothing. So the reported quantity is

    P(all fragments of document d lie in one block of size <= B)

as a CURVE over B. A document connected only inside a 9,000-fragment component
has not been usefully blocked.

Pair recall is reported too but understates a blocker: a downstream graph solver
does not need all C(m,2) edges of an m-fragment document, only enough to connect
it. A sparse chain of m-1 correct edges is sufficient, and pair recall scores
that as poor.

AN INVERTED INDEX IS AN OPPORTUNITY, NOT A GUARANTEE
----------------------------------------------------
A common token produces an enormous posting list, and one such term can
reintroduce the quadratic cost the index was meant to avoid. Posting-list sizes,
comparisons generated, peak memory and wall-clock are all instrumented and
printed, because "we used an inverted index" is not evidence that it scaled.

    python analysis/blocker.py --k 10 --sample 2000
    python analysis/blocker.py --k 10                  # full corpus
"""

import argparse
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE_DIR)

DEFAULT_FRAGMENTS = os.path.join(ROOT, "data", "prose", "prose_fragments.jsonl")
DEFAULT_OUT = os.path.join(ROOT, "results", "blocker")

# Same tokeniser and weighting as adversaries/memon_linkage.build_tfidf. The
# blocker MUST use the similarity the attacker's candidate generation uses, or
# the measurement describes a different system than the one being evaluated.
_TOKEN = re.compile(r"[a-z0-9]+")


def tok(t):
    return _TOKEN.findall(t.lower())


def load_fragments(path, sample=None, seed=42):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    if sample and sample < len(rows):
        # Sample whole DOCUMENTS, never loose fragments: sampling fragments
        # would silently remove a document's partners and make recall
        # unmeasurable.
        import random
        by_rec = defaultdict(list)
        for r in rows:
            by_rec[r["record_id"]].append(r)
        rids = sorted(by_rec)
        rng = random.Random(seed)
        keep, n = [], 0
        for rid in rng.sample(rids, len(rids)):
            if n >= sample:
                break
            keep.extend(by_rec[rid])
            n += len(by_rec[rid])
        rows = keep
    return rows


def build_vectors(rows):
    """L2-normalised TF-IDF, identical weighting to build_tfidf."""
    docs = {r["fragment_id"]: tok(r["text"]) for r in rows}
    df = Counter()
    for toks in docs.values():
        df.update(set(toks))
    n = len(docs)
    vecs = {}
    for f, toks in docs.items():
        tf = Counter(toks)
        v = {t: (1 + math.log(c)) * math.log((n + 1) / (df[t] + 1))
             for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vecs[f] = {t: x / norm for t, x in v.items()}
    return vecs, df


def build_index(vecs, df, max_df_frac=1.0):
    """term -> [(fragment_id, weight)], optionally dropping ubiquitous terms.

    max_df_frac is a declared knob, not a silent optimisation: dropping terms
    that appear in more than this fraction of fragments bounds the worst posting
    list, at the cost of ignoring some real signal. It is reported.
    """
    n = len(vecs)
    cutoff = max_df_frac * n
    index = defaultdict(list)
    dropped = 0
    for f, v in vecs.items():
        for t, w in v.items():
            if df[t] > cutoff:
                dropped += 1
                continue
            index[t].append((f, w))
    return index, dropped


def top_k_via_index(vecs, index, k):
    """Each fragment's k nearest neighbours by cosine, without a dense matrix.

    Accumulates dot products only over fragments that SHARE A TERM, which is
    where the saving comes from. Instrumented, because sparsity is a property of
    the data rather than a guarantee of the method.
    """
    neighbours = {}
    comparisons = 0
    t0 = time.time()
    for f, v in vecs.items():
        acc = defaultdict(float)
        for t, w in v.items():
            for g, gw in index.get(t, ()):
                if g != f:
                    acc[g] += w * gw
                    comparisons += 1
        top = sorted(acc.items(), key=lambda kv: (-kv[1], kv[0]))[:k]
        neighbours[f] = top
    return neighbours, {
        "comparisons": comparisons,
        "seconds": round(time.time() - t0, 2),
        "mean_candidates_per_fragment":
            round(comparisons / max(1, len(vecs)), 1),
    }


def build_graph(neighbours):
    """FROZEN: undirected edge when EITHER endpoint selects the other."""
    edges = set()
    for f, top in neighbours.items():
        for g, _s in top:
            edges.add((f, g) if f <= g else (g, f))
    return edges


def components(ids, edges):
    parent = {f: f for f in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in edges:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj
    out = defaultdict(list)
    for f in ids:
        out[find(f)].append(f)
    return [sorted(v) for v in out.values()]


def evaluate(rows, neighbours, edges, b_values):
    """Blocker quality. Recall, bounded connectivity, contamination, reduction."""
    owner = {r["fragment_id"]: r["record_id"] for r in rows}
    ids = [r["fragment_id"] for r in rows]
    by_rec = defaultdict(list)
    for r in rows:
        by_rec[r["record_id"]].append(r["fragment_id"])

    # pair recall over TRUE within-document pairs
    true_pairs = sum(len(v) * (len(v) - 1) // 2 for v in by_rec.values())
    kept_true = sum(1 for a, b in edges if owner[a] == owner[b])
    n = len(ids)
    possible = n * (n - 1) // 2

    comps = components(ids, edges)
    comp_of = {f: i for i, c in enumerate(comps) for f in c}
    sizes = sorted(len(c) for c in comps)

    # BOUNDED connectivity: a document is usefully blocked only if all of its
    # fragments sit in ONE component AND that component is small enough to be
    # worth handing to a reconstruction stage.
    bounded = {}
    for b in b_values:
        ok = 0
        for rid, frs in by_rec.items():
            cs = {comp_of[f] for f in frs}
            if len(cs) == 1 and len(comps[next(iter(cs))]) <= b:
                ok += 1
        bounded[b] = ok / len(by_rec)

    whole_doc_one_comp = sum(
        1 for frs in by_rec.values() if len({comp_of[f] for f in frs}) == 1)

    # contamination: how many distinct source documents land in each block
    sources = [len({owner[f] for f in c}) for c in comps]

    return {
        "n_fragments": n,
        "n_documents": len(by_rec),
        "possible_pairs": possible,
        "true_pairs": true_pairs,
        "edges": len(edges),
        "pair_recall": kept_true / true_pairs if true_pairs else 0.0,
        "reduction_ratio": 1 - len(edges) / possible if possible else 0.0,
        "n_blocks": len(comps),
        "block_size_min": sizes[0] if sizes else 0,
        "block_size_median": sizes[len(sizes) // 2] if sizes else 0,
        "block_size_max": sizes[-1] if sizes else 0,
        "largest_block_frac": (sizes[-1] / n) if n else 0.0,
        "docs_in_one_block": whole_doc_one_comp / len(by_rec),
        "bounded_connectivity": bounded,
        "sources_per_block_mean": sum(sources) / len(sources) if sources else 0,
        "sources_per_block_max": max(sources) if sources else 0,
    }


def parse_args():
    ap = argparse.ArgumentParser(description="Measure the TF-IDF blocker.")
    ap.add_argument("--fragments", default=DEFAULT_FRAGMENTS)
    ap.add_argument("--k", type=int, nargs="+", default=[5, 10, 20])
    ap.add_argument("--sample", type=int, default=None,
                    help="approximate fragment budget; whole documents only")
    ap.add_argument("--max-df-frac", type=float, default=1.0)
    ap.add_argument("--b-values", type=int, nargs="+",
                    default=[7, 14, 28, 56, 112, 500])
    ap.add_argument("--out", default=DEFAULT_OUT)
    return ap.parse_args()


def main():
    a = parse_args()
    rows = load_fragments(a.fragments, sample=a.sample)
    print(f"corpus : {len(rows)} fragments, "
          f"{len({r['record_id'] for r in rows})} documents")

    t0 = time.time()
    vecs, df = build_vectors(rows)
    index, dropped = build_index(vecs, df, a.max_df_frac)
    posting = sorted(len(v) for v in index.values())
    print(f"index  : {len(index)} terms, {time.time() - t0:.1f}s to build, "
          f"{dropped} postings dropped at max_df={a.max_df_frac}")
    print(f"         posting lists: median {posting[len(posting)//2]}, "
          f"p99 {posting[int(len(posting)*0.99)]}, max {posting[-1]}")
    if posting[-1] > 0.5 * len(rows):
        print(f"         [!] the largest posting list covers "
              f"{posting[-1]/len(rows):.0%} of the corpus -- one common term is "
              f"reintroducing quadratic cost")

    results = {}
    print(f"\n{'k':>4}{'edges':>10}{'recall':>9}{'reduction':>11}"
          f"{'blocks':>8}{'max blk':>9}{'src/blk':>9}{'sec':>7}")
    for k in a.k:
        nb, perf = top_k_via_index(vecs, index, k)
        edges = build_graph(nb)
        ev = evaluate(rows, nb, edges, a.b_values)
        ev["k"] = k
        ev["perf"] = perf
        results[k] = ev
        print(f"{k:>4}{ev['edges']:>10}{ev['pair_recall']:>9.3f}"
              f"{ev['reduction_ratio']:>11.5f}{ev['n_blocks']:>8}"
              f"{ev['block_size_max']:>9}{ev['sources_per_block_mean']:>9.1f}"
              f"{perf['seconds']:>7.1f}")

    print(f"\nBOUNDED CONNECTIVITY -- P(all of a document's fragments in ONE "
          f"block of size <= B)")
    print(f"{'k':>4}" + "".join(f"{('B=' + str(b)):>10}" for b in a.b_values)
          + f"{'any size':>10}")
    for k in a.k:
        ev = results[k]
        row = "".join(f"{ev['bounded_connectivity'][b]:>10.3f}"
                      for b in a.b_values)
        print(f"{k:>4}{row}{ev['docs_in_one_block']:>10.3f}")

    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, "blocker_measurement.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"graph_definition":
                   "undirected edge when either endpoint selects the other in "
                   "its top-k; block = uncapped connected component",
                   "sample": a.sample, "max_df_frac": a.max_df_frac,
                   "results": {str(k): v for k, v in results.items()}},
                  fh, indent=2)
    print(f"\nwrote {path}")


if __name__ == "__main__":
    main()
