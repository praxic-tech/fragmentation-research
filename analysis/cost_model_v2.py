#!/usr/bin/env python3
"""
cost_model_v2.py — cost model rebuilt on MEASURED anchors, not a fitted curve.
NO API CALLS.

Supersedes the estimator in corpus_sizing.py, which overstated the low end of
the ordering curve by 3-4x and used a linkage exponent borrowed from ordering.

Ordering output, measured (claude-sonnet-5, default effort, batch pricing):
     13 frags ->    323 tok
     22 frags ->    579 tok
     31 frags ->  4,444 tok  and  2,437 tok   <- same document, 1.82x apart
     76 frags -> 24,001 tok
Not a power law: roughly linear (~26 tok/frag) below ~22 fragments, then
reasoning switches on and it goes superlinear (log-log slope 1.88 above 31).

Linkage output, measured — the two configurations in the plan are direct
anchors, not extrapolations:
    5 docs full,  179 frags ->  8,958 tok   5/5 groups, 0 dups
    7 docs cap30, 132 frags -> 14,144 tok   7/7 groups, 0 dups   <- GRID
    7 docs full,  178 frags -> 21,234 tok   7/7 groups, 0 dups   <- HEADLINE
   10 docs full,  418 frags ->  >32,000     FAILED
   10 docs full,  460 frags ->  >48,000     FAILED
Group count drives cost harder than fragment count: 179 frags at 5 groups cost
8,958, while 178 frags at 7 groups cost 21,234.
"""

import json
import math
import random
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
IN_PER_M, OUT_PER_M = 1.0, 5.0

# Delimiters for the machine-readable block; run_grid.py reads between them.
JSON_BEGIN = "===COST_MODEL_JSON_BEGIN==="
JSON_END   = "===COST_MODEL_JSON_END==="          # sonnet-5 introductory + batch 50%
CAL_IN = 1.541 * 0.913                   # estimator factor, corrected by measurement
LABEL_CHARS = 11

# measured ordering anchors; 31 uses the mean of the two observed runs
ORD = [(13, 323), (22, 579), (31, 3440), (76, 24001)]
RUN_TO_RUN = 1.82                        # measured, same document, 31 fragments

# measured linkage anchors at 7 groups
LNK_FULL = (178, 21234)                  # headline pool: 7 docs, full length
LNK_CAP = (132, 14144)                   # grid pool: 7 docs, capped at 30


def load():
    fr = [json.loads(l) for l in
          (HERE.parent / "data/prose/prose_fragments.jsonl").open(encoding="utf-8") if l.strip()]
    n, ch = defaultdict(int), defaultdict(int)
    for f in fr:
        n[f["record_id"]] += 1
        ch[f["record_id"]] += len(f["text"])
    return sorted(n), n, ch, sum(ch.values()) / sum(n.values())


def ord_out(k):
    """Output tokens for ordering a k-fragment document. Piecewise through anchors."""
    k = max(3, k)
    if k <= ORD[0][0]:
        return ORD[0][1] * (k / ORD[0][0]) ** 1.11
    for (x1, y1), (x2, y2) in zip(ORD, ORD[1:]):
        if k <= x2:
            s = math.log(y2 / y1) / math.log(x2 / x1)
            return y1 * (k / x1) ** s
    return min(ORD[-1][1] * (k / ORD[-1][0]) ** 1.88, 64000)


def ord_cost(k, chars_per_frag):
    inp = ((chars_per_frag * k + k * LABEL_CHARS) / 4 + 150) * CAL_IN
    return inp / 1e6 * IN_PER_M + ord_out(k) / 1e6 * OUT_PER_M


def lnk_cost(frags, out, chars_per_frag):
    inp = ((chars_per_frag * frags + frags * LABEL_CHARS) / 4 + 200) * CAL_IN
    return inp / 1e6 * IN_PER_M + out / 1e6 * OUT_PER_M


def main():
    ids, nfrag, nchar, CHF = load()
    KS = [nfrag[d] for d in ids]
    rng = random.Random(5)
    SUB = rng.sample(ids, 180)
    CAP, POOLS_GRID = 30, 180 // 7

    l_head = lnk_cost(*LNK_FULL, CHF)
    l_grid = lnk_cost(*LNK_CAP, CHF)

    print("MEASURED unit costs (batch, sonnet-5 intro)")
    print(f"  linkage, headline pool (7 docs full)   {l_head:8.4f}")
    print(f"  linkage, grid pool (7 docs cap 30)     {l_grid:8.4f}")
    print("  ordering, per document: " +
          "  ".join(f"{k}f={ord_cost(k, CHF):.4f}" for k in (10, 20, 30, 40, 54, 76)))
    print()

    def cell(mult):
        return sum(ord_cost(max(2, round(min(nfrag[d], CAP) * mult)), CHF) for d in SUB)

    o_sent, o_clause, o_tw = cell(1.0), cell(1.81), cell(1.617)

    head_o = sum(ord_cost(k, CHF) for k in KS)
    head_l = 71 * l_head
    grid_o = 4 * o_sent + 4 * o_clause + 3 * o_tw + (o_sent + 180 * 2000 / 1e6 * OUT_PER_M)
    grid_l = (POOLS_GRID * l_grid * 5
              + POOLS_GRID * lnk_cost(round(132 * 1.81), 14144 * 1.5, CHF)
              + POOLS_GRID * lnk_cost(round(132 * 1.617), 14144 * 1.35, CHF))
    repeats = 2 * (o_sent + POOLS_GRID * l_grid)
    ident = 71 * lnk_cost(28, 3000, CHF)
    ctrl = 2 * l_head + 100 * (((CHF * 30) / 4) * CAL_IN / 1e6 * IN_PER_M
                               + 300 / 1e6 * OUT_PER_M)

    rows = [
        ("1  Controls: leak canary + memorization probe", ctrl),
        ("2  Headline ordering, 500 docs, full length", head_o),
        ("3  Headline linkage, 71 pools, full length", head_l),
        ("4  Ordering grid, 12 cells x 180 docs cap 30", grid_o),
        ("5  Linkage grid, 7 cells x 25 pools cap 30", grid_l),
        ("6  Identifiers, 71 pools", ident),
        ("7  Repeats: grid reference x2 (variance bound)", repeats),
    ]
    total = 0.0
    for lbl, v in rows:
        total += v
        print(f"{lbl:48s} {v:8.2f}")
    print(f"{'   BASE':48s} {total:8.2f}")
    print(f"{'   buffer 40% (run-to-run measured at 1.82x)':48s} {total * 0.40:8.2f}")
    print(f"{'   TOTAL':48s} {total * 1.40:8.2f}")
    print(f"\n  headroom under $200: {200 - total * 1.40:.2f}")
    print(f"  ordering grid per cell: sentence {o_sent:.2f}  "
          f"clause {o_clause:.2f}  token-window {o_tw:.2f}")

    # Machine-readable block for harness/run_grid.py --dry-run. Priced PER
    # GRANULARITY, not as a flat per-cell average: clause costs ~4x sentence
    # here, so a count of pending cells cannot project a spend. Delimited
    # rather than "last {...}" because the payload is nested.
    payload = {
        "ordering_per_cell": {
            "sentence": round(o_sent, 4),
            "clause": round(o_clause, 4),
            "token-window": round(o_tw, 4),
        },
        "linkage_per_cell": {
            "sentence": round(POOLS_GRID * l_grid, 4),
            "clause": round(POOLS_GRID * lnk_cost(round(132 * 1.81),
                                                  14144 * 1.5, CHF), 4),
            "token-window": round(POOLS_GRID * lnk_cost(round(132 * 1.617),
                                                        14144 * 1.35, CHF), 4),
        },
        "totals": {"base_usd": round(total, 2),
                   "total_usd": round(total * 1.40, 2)},
    }
    print(JSON_BEGIN)
    print(json.dumps(payload, indent=2))
    print(JSON_END)


if __name__ == "__main__":
    main()
