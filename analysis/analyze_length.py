#!/usr/bin/env python3
"""
analyze_length.py — fragment-count distribution for choosing the real upper bound.

Reports the shape from REAL data so the bound is picked from percentiles rather
than guessed. Uses `n_sentences_full` (the true uncapped sentence count) rather
than `n_fragments`, because n_fragments is clipped by the pull's own cap — using
it would let the cap we are trying to measure truncate the measurement.

Usage:  python analysis/analyze_length.py            # defaults to data/prose
"""

import argparse
import json
import statistics as st
from pathlib import Path


def pct(sorted_vals, p):
    if not sorted_vals:
        return 0
    k = (len(sorted_vals) - 1) * (p / 100.0)
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(Path(__file__).resolve().parent.parent / "data" / "prose"))
    ap.add_argument("--bucket", type=int, default=5)
    args = ap.parse_args()

    meta = [json.loads(l) for l in
            (Path(args.data) / "prose_meta.jsonl").open(encoding="utf-8") if l.strip()]
    # true, uncapped counts
    ns = sorted(m.get("n_sentences_full", m["n_fragments"]) for m in meta)
    n_trunc = sum(1 for m in meta if m.get("truncated"))
    N = len(ns)

    print("=" * 72)
    print(f" FRAGMENT-COUNT DISTRIBUTION — {N} documents (true, uncapped)")
    print("=" * 72)
    if n_trunc:
        print(f" WARNING: {n_trunc} document(s) exceeded the pull's 100-sentence")
        print(f" upper bound, so their fragments were clipped. The counts below are")
        print(f" the TRUE sentence counts from n_sentences_full, but any document")
        print(f" longer than 100 is itself right-censored at its true length.")
        print()

    # ── histogram ────────────────────────────────────────────────────────────
    b = args.bucket
    buckets = {}
    for n in ns:
        lo = (n // b) * b
        buckets[(lo, lo + b - 1)] = buckets.get((lo, lo + b - 1), 0) + 1
    widest = max(buckets.values())
    print(f"{'bucket':>12s} {'docs':>6s} {'%':>6s}  histogram")
    for (lo, hi), c in sorted(buckets.items()):
        bar = "#" * max(1, round(40 * c / widest))
        print(f"{f'{lo}-{hi}':>12s} {c:6d} {100*c/N:5.1f}%  {bar}")

    # ── percentiles ──────────────────────────────────────────────────────────
    print()
    print("=" * 72)
    print(" PERCENTILES (n_fragments per document)")
    print("=" * 72)
    for p in (50, 90, 95, 99):
        print(f"  {p:2d}th percentile : {pct(ns, p):8.1f}")
    print(f"  max             : {max(ns):8d}")
    print(f"  min             : {min(ns):8d}")
    print(f"  mean / median   : {st.mean(ns):8.1f} / {st.median(ns):.1f}")

    # ── exclusion / truncation impact at candidate bounds ────────────────────
    print()
    print("=" * 72)
    print(" IMPACT OF EACH CANDIDATE UPPER BOUND")
    print("=" * 72)
    print(f"{'cutoff':>8s} {'bound':>7s} {'docs OVER bound':>17s} {'% of corpus':>12s}"
          f" {'frags kept':>12s}")
    total_frags = sum(ns)
    for p in (90, 95, 99):
        bound = int(pct(ns, p))
        over = sum(1 for n in ns if n > bound)
        kept = sum(min(n, bound) for n in ns)
        print(f"{f'{p}th':>8s} {bound:7d} {over:17d} {100*over/N:11.1f}%"
              f" {kept:8,d} ({100*kept/total_frags:.1f}%)")
    print()
    print("  'docs OVER bound' = documents that would be TRUNCATED at that bound")
    print("  (they are kept, but clipped). Nothing is dropped from the corpus.")
    print()
    print("  Note: a bound applied by truncation removes length VARIANCE at the top")
    print("  end — every document above the bound collapses to exactly the bound.")
    print("  prose_v3's 12-cap did this to 96% of documents.")

    # ── other length metrics ─────────────────────────────────────────────────
    print()
    print("=" * 72)
    print(" OTHER LENGTH METRICS")
    print("=" * 72)
    for field, label in (("total_chars", "document chars"),
                         ("total_words", "document words"),
                         ("mean_fragment_chars", "mean fragment chars")):
        v = sorted(m[field] for m in meta)
        print(f"  {label:22s} median {st.median(v):9.1f}   "
              f"p95 {pct(v,95):9.1f}   max {max(v):9.1f}")


if __name__ == "__main__":
    main()
