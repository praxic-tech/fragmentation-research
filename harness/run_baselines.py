#!/usr/bin/env python3
"""
run_baselines.py — run the random + Memon baselines against an arbitrary corpus.

The main harness (harness/harness.py) hardcodes its dataset paths, so this thin
runner points the SAME evaluation functions at a corpus given on the command
line. Nothing here reimplements scoring — it imports eval_random / eval_memon /
print_comparison_table from the harness so numbers are directly comparable to
the main table.

Usage:
    python harness/run_baselines.py --runs 2000                      # data/prose
    python harness/run_baselines.py --data results/grid/random_clause    # one grid cell
"""

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent      # repo root
DEFAULT_DATA = ROOT / "data" / "prose"
sys.path.insert(0, str(ROOT / "harness"))

from loader import load_fragments, load_answer_key, group_fragments_by_record   # noqa: E402
import harness as H                                                             # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DEFAULT_DATA),
                    help="folder holding prose_fragments.jsonl + prose_answer_key.jsonl")
    ap.add_argument("--runs", type=int, default=2000,
                    help="random-baseline Monte Carlo runs")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--grouping", default="fixed",
                    choices=["fixed", "legacy-greedy", "legacy-mst"],
                    help="Game L grouping; legacy options reproduce pre-fix tables only")
    ap.add_argument("--label", default=None, help="title for the results table")
    args = ap.parse_args()

    data = Path(args.data)
    frag_path = data / "prose_fragments.jsonl"
    key_path  = data / "prose_answer_key.jsonl"
    for p in (frag_path, key_path):
        if not p.exists():
            sys.exit(f"ERROR: missing {p}")

    import random
    random.seed(args.seed)
    np.random.seed(args.seed)

    fragments   = load_fragments(frag_path)
    true_order  = load_answer_key(key_path)
    true_groups = group_fragments_by_record(fragments)

    label = args.label or data.name
    sizes = [len(v) for v in true_groups.values()]
    print("=" * 70)
    print(f" Evaluating: {label}")
    print("=" * 70)
    print(f"  {len(fragments)} fragments across {len(true_groups)} records")
    print(f"  Fragment counts per record: min={min(sizes)}, max={max(sizes)}, "
          f"mean={np.mean(sizes):.1f}")
    print()

    results = {}

    print(f"Random baseline ({args.runs:,} runs) ...")
    o_taus, l_ps, l_rs, l_fs = H.eval_random(fragments, true_order, true_groups,
                                             args.runs)
    sd = float(o_taus.std(ddof=1))
    results["Random"] = {
        "o_tau":       float(o_taus.mean()),
        "o_tau_std":   sd,
        "l_precision": float(l_ps.mean()),
        "l_recall":    float(l_rs.mean()),
        "l_f1":        float(l_fs.mean()),
    }
    print(f"  Game O tau : {o_taus.mean():+.4f} +- {sd:.4f}"
          f"   2sigma CI [{o_taus.mean()-2*sd:+.4f}, {o_taus.mean()+2*sd:+.4f}]")
    print(f"  Game L F1: {l_fs.mean():.4f} +- {l_fs.std(ddof=1):.4f}")

    for method, name in [("greedy", "Memon-Greedy"), ("mst", "Memon-MST")]:
        print(f"\n{name} ...")
        results[name] = H.eval_memon(fragments, true_order, true_groups, method,
                                     grouping_variant=args.grouping)
        r = results[name]
        print(f"  Game O tau : {r['o_tau']:+.4f}")
        print(f"  Game L   : F1={r['l_f1']:.4f}  P={r['l_precision']:.4f}  "
              f"R={r['l_recall']:.4f}")
    print(f"\n  [Game L grouping = '{args.grouping}' for both rows]")

    print()
    H.print_comparison_table(results, f"{label} Results", args.seed, args.runs)


if __name__ == "__main__":
    main()
