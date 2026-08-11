#!/usr/bin/env python3
"""
estimate_cost.py — LLM cost of one full adversary run on prose_v4.

Cost is driven by REAL per-document character counts from the corpus, not from
assumed fragment sizes.

Sonnet 5 pricing: $2 / M input tokens, $10 / M output tokens.

Scenarios: untruncated, and upper bounds at the 90th (56), 95th (71) and
99th (100) percentiles of the fragment-count distribution.

  Ordering (Game O) — one call per document:
      input  = doc_chars / 4 + 150 (instruction)
      output = n_fragments * 15
  Linkage (Game L) — chunked into pools of 100 records:
      input  = pool_chars / 4 + 200
      output = pool_fragments * 3

A calibration factor from a real API call can be applied with
--cal-in / --cal-out (see calibrate_call.py).

Usage:
    python estimate_cost.py --data ./data/prose_v4
    python estimate_cost.py --data ./data/prose_v4 --cal-in 1.07 --cal-out 0.82
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

IN_PER_M, OUT_PER_M = 2.0, 10.0     # Sonnet 5 USD per million tokens
POOL_RECORDS = 100


def load(data):
    d = Path(data)
    frs = [json.loads(l) for l in (d / "prose_fragments.jsonl").open(encoding="utf-8") if l.strip()]
    meta = {m["record_id"]: m for m in
            (json.loads(l) for l in (d / "prose_meta.jsonl").open(encoding="utf-8") if l.strip())}
    by = defaultdict(list)
    for f in frs:
        by[f["record_id"]].append(f)
    return by, meta


def scenario(by, meta, bound):
    """Return per-document (n_fragments, chars) under an upper bound.
    bound=None -> untruncated: use the TRUE full-document figures from meta,
    because documents past the pull's 100-sentence bound had their stored
    fragments clipped and would otherwise be undercounted."""
    out = {}
    for rec, frags in by.items():
        m = meta[rec]
        if bound is None:
            out[rec] = (m.get("n_sentences_full", len(frags)), m.get("doc_chars_full", 0))
        else:
            keep = frags[:bound]
            out[rec] = (len(keep), sum(len(f["text"]) for f in keep))
    return out


def cost(docs, cal_in=1.0, cal_out=1.0, cal_l_out=None):
    """cal_out applies to ordering output; cal_l_out to linkage output.
    They are separated because the calibration measured them differently:
    ordering completed normally (valid factor), while the linkage call hit the
    max_tokens ceiling and produced no answer, so its factor is a FLOOR, not a
    measurement."""
    if cal_l_out is None:
        cal_l_out = cal_out
    # Ordering: one call per document
    o_in = sum(c / 4 + 150 for _, c in docs.values())
    o_out = sum(n * 15 for n, _ in docs.values())
    # Linkage: pools of POOL_RECORDS documents
    recs = sorted(docs)
    l_in = l_out = 0.0
    pools = 0
    for i in range(0, len(recs), POOL_RECORDS):
        chunk = recs[i:i + POOL_RECORDS]
        pf = sum(docs[r][0] for r in chunk)
        pc = sum(docs[r][1] for r in chunk)
        l_in += pc / 4 + 200
        l_out += pf * 3
        pools += 1
    o_in, o_out = o_in * cal_in, o_out * cal_out
    l_in, l_out = l_in * cal_in, l_out * cal_l_out
    d = lambda i, o: i / 1e6 * IN_PER_M + o / 1e6 * OUT_PER_M
    return {
        "o_in": o_in, "o_out": o_out, "o_cost": d(o_in, o_out),
        "l_in": l_in, "l_out": l_out, "l_cost": d(l_in, l_out),
        "pools": pools,
        "total": d(o_in, o_out) + d(l_in, l_out),
        "frags": sum(n for n, _ in docs.values()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="./data/prose_v4")
    ap.add_argument("--cal-in", type=float, default=1.0)
    ap.add_argument("--cal-out", type=float, default=1.0,
                    help="ordering output factor (measured)")
    ap.add_argument("--cal-l-out", type=float, default=None,
                    help="linkage output factor (FLOOR — the calibration call hit "
                         "the max_tokens ceiling, so this is a lower bound)")
    args = ap.parse_args()

    by, meta = load(args.data)
    cal = (args.cal_in != 1.0 or args.cal_out != 1.0)
    tag = (f"CALIBRATED (input x{args.cal_in:.3f}, ord-out x{args.cal_out:.3f}, "
           f"lnk-out x{args.cal_l_out or args.cal_out:.3f})"
           if cal else "UNCALIBRATED — raw estimate, not yet validated against a real call")

    print("=" * 92)
    print(f" LLM COST — one full run on prose_v4 (500 docs) | Sonnet 5 "
          f"${IN_PER_M}/M in, ${OUT_PER_M}/M out")
    print(f" {tag}")
    print("=" * 92)
    print(f"{'scenario':>14s} {'frags':>8s} {'ord in':>10s} {'ord out':>9s} {'ord $':>8s}"
          f" {'lnk in':>10s} {'lnk out':>9s} {'lnk $':>8s} {'TOTAL $':>9s} {'5-run $':>9s}")
    print("-" * 92)
    rows = []
    for label, bound in (("untruncated", None), ("90th (56)", 56),
                         ("95th (71)", 71), ("99th (100)", 100)):
        c = cost(scenario(by, meta, bound), args.cal_in, args.cal_out, args.cal_l_out)
        rows.append((label, c))
        print(f"{label:>14s} {c['frags']:8,d} {c['o_in']:10,.0f} {c['o_out']:9,.0f} "
              f"{c['o_cost']:8.2f} {c['l_in']:10,.0f} {c['l_out']:9,.0f} {c['l_cost']:8.2f} "
              f"{c['total']:9.2f} {c['total']*5:9.2f}")
    print("-" * 92)
    print(f"  linkage pools: {rows[0][1]['pools']} (100 records each)")
    if not cal:
        print("\n  NOTE: uncalibrated. Run calibrate_call.py and re-run with "
              "--cal-in/--cal-out.")


if __name__ == "__main__":
    main()
