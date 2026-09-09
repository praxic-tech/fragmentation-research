#!/usr/bin/env python3
"""
cost_model_v2.py — the cost model for the JOINT run. NO API CALLS.

Replaces the O+L model that lived here. That one priced an experiment that no
longer exists: one call per unit, no medoid-of-k, no repair retries, and no
pair-scoring cost class at all. Its headline figures ($107 base, ~$25 headline,
$149.82 ceiling) are superseded and must not be quoted.

WHAT IS MEASURED AND WHAT IS ASSUMED
------------------------------------
Everything in MEASURED below came off disk or off a real run. Everything in
ASSUMED is a named parameter with a stated basis, and the sensitivity table at
the bottom shows what happens when the shaky ones move. The point of this file
is a forecast you can argue with, not a number.

MEASURED
    fragment text                132 chars mean, 125 median (pilot_reference)
    one-shot J prompt            139 chars/fragment (8 pools, N=3/5/7, on disk)
    candidate edges, dedup       union-kNN collapses reciprocal choices, so the
                                 count is ~0.66 x n x k, NOT n x k. Measured at
                                 N=3,5,7 x k=3,4,5,8,10 and flat in N:
                                     k=3  2.04 edges/frag     k=8   5.10
                                     k=4  2.64                k=10  6.34
                                     k=5  3.26
                                 At N=7, k=5 that is 608 pairs per pool. The
                                 plan's n x k guess for k=10 was 1,780; the
                                 measured figure is 1,164, 35% lower.
    pair-batch prompt            82 tok/pair at 15 pairs/call (chars/4, before
                                 the tokenizer correction)
    pair-batch output            250 fixed + 70/pair, measured while fixing the
                                 empty-batch bug. The bare answer JSON is only
                                 12 tok/pair, so ~5.8x of this is reasoning.
    one-shot answer output       sonnet-5, batch, SAME output shape J emits
                                 (list of lists of aliases):
                                     179 frags, 5 groups ->  8,958 tok
                                     132 frags, 7 groups -> 14,144 tok
                                     178 frags, 7 groups -> 21,234 tok
                                 Group count drives this harder than fragment
                                 count. 154 tok/frag at 7 groups.
    sampling frame               71 pools of 7 documents; 25 pools per grid cell
    grid                         12 cells (13 rows, 1 skipped)

ASSUMED — these are where the forecast can be wrong
    J_OVER_L        1.15   The output anchors are GAME L. J asks for membership
                           AND order in one answer, so it cannot be cheaper,
                           and the answer JSON is identical in length. 1.15
                           prices the extra reasoning. NOT measured on sonnet.
                           G4 measures it; until then this is the single
                           largest source of error in the total.
    MEDOID_K        3      One-shot J only. [R4] forbids it on the hierarchical
                           attacker, where 3 pipelines would mean ~130 extra
                           calls per pool.
    RETRY_RATE      0.15   Fraction of units needing one repair round.
    PAIR_MODEL_TAX  1.0    The pair-output figure was measured on
                           gpt-oss-120b, not sonnet. 1.0 assumes they match.
    PRICES          $1/$5 per M in/out — sonnet-5 introductory WITH the 50%
                           batch discount already folded in. Verify at purchase.

Run:  python analysis/cost_model_v2.py
      python analysis/cost_model_v2.py --sensitivity
"""

import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

JSON_BEGIN = "===COST_MODEL_JSON_BEGIN==="
JSON_END = "===COST_MODEL_JSON_END==="

# ── prices (sonnet-5 introductory, batch discount folded in) ─────────────────
IN_PER_M, OUT_PER_M = 1.0, 5.0

# ── measured constants ───────────────────────────────────────────────────────
CHARS_PER_FRAG_PROMPT = 139.0      # one-shot J prompt, per fragment
CAL_IN = 1.541 * 0.913             # chars/4 -> tokens, calibrated on this corpus
PAIR_IN_TOK = 82.0 * CAL_IN        # per pair, 15 pairs/call
PAIR_OUT_FIXED = 250.0             # per call
PAIR_OUT_PER_PAIR = 70.0
PAIRS_PER_CALL = 15

EDGES_PER_FRAG = {3: 2.04, 4: 2.64, 5: 3.26, 8: 5.10, 10: 6.34}
BRIDGE_UPLIFT = 1.03               # bridge rounds added ~3% more pairs

# one-shot answer output, tokens, from sonnet-5 measurements
ONESHOT_OUT = {5: (179, 8958), 7: (132, 14144)}
OUT_TOK_PER_FRAG_7 = (21234 - 14144) / (178 - 132)      # 154.1
OUT_INTERCEPT_7 = 21234 - OUT_TOK_PER_FRAG_7 * 178

# ── the sampling frame and the grid ──────────────────────────────────────────
N_POOLS_HEADLINE = 71
N_POOLS_PER_CELL = 25
POOL_SIZE = 7
FRAGS_PER_POOL_FULL = 184          # 7 docs, full length, measured
FRAGS_PER_POOL_CAP = 132           # 7 docs, capped at 30 frags/doc, measured

# Fragment-count multipliers by granularity, relative to sentence.
#
# clause was 1.81 here and in analysis/cost_grid.py. RUN_PLAN measured 1.31 on
# the promoted corpus with the shared spaCy base and flagged the row as
# overpriced; the old model never picked the correction up, and CUT_ORDER still
# offers "drop the clause row" as a $31 saving computed at the wrong ratio. At
# 1.31 the clause row costs materially less and is a worse thing to cut.
# token-window's 1.617 is inherited and NOT independently verified.
GRANULARITY_MULT = {"sentence": 1.0, "clause": 1.31,
                    "token-window": 1.617, "llm-decides": 0.65}
GRID_CELLS = [("sentence", 4), ("clause", 4),
              ("token-window", 3), ("llm-decides", 1)]

# ── assumptions ──────────────────────────────────────────────────────────────
DEFAULTS = dict(j_over_l=1.15, medoid_k=3, retry_rate=0.15,
                pair_model_tax=1.0, k=5, hier_pools=25)


def oneshot_out_tokens(n_frags, n_groups=7):
    """Answer output tokens for a one-shot reconstruction of n_frags."""
    if n_groups >= 7:
        return max(500.0, OUT_TOK_PER_FRAG_7 * n_frags + OUT_INTERCEPT_7)
    ref_frags, ref_tok = ONESHOT_OUT.get(n_groups, ONESHOT_OUT[5])
    return ref_tok * (n_frags / ref_frags)


def oneshot_cost(n_frags, n_groups, a):
    """One generation of one-shot J over a pool of n_frags."""
    inp = (CHARS_PER_FRAG_PROMPT * n_frags / 4.0 + 200) * CAL_IN
    out = oneshot_out_tokens(n_frags, n_groups) * a["j_over_l"]
    return inp / 1e6 * IN_PER_M + out / 1e6 * OUT_PER_M


def oneshot_unit(n_frags, n_groups, a):
    """A scored pool: medoid-of-k generations, plus expected repair retries."""
    per_gen = oneshot_cost(n_frags, n_groups, a)
    return per_gen * a["medoid_k"] * (1.0 + a["retry_rate"])


def hierarchical_unit(n_frags, a):
    """One hierarchical attack over a pool. No medoid-of-k -- [R4]."""
    edges = EDGES_PER_FRAG[a["k"]] * n_frags * BRIDGE_UPLIFT
    calls = edges / PAIRS_PER_CALL
    inp = edges * PAIR_IN_TOK
    out = (calls * PAIR_OUT_FIXED + edges * PAIR_OUT_PER_PAIR) \
        * a["pair_model_tax"]
    return (inp / 1e6 * IN_PER_M + out / 1e6 * OUT_PER_M) \
        * (1.0 + a["retry_rate"])


def grid_cost(a):
    """12 cells x 25 pools, capped pools, one-shot J. Per granularity."""
    per_cell = {}
    for gran, _n in GRID_CELLS:
        frags = FRAGS_PER_POOL_CAP * GRANULARITY_MULT[gran]
        per_cell[gran] = N_POOLS_PER_CELL * oneshot_unit(frags, POOL_SIZE, a)
    total = sum(per_cell[g] * n for g, n in GRID_CELLS)
    return per_cell, total


def line_items(a):
    head_one = N_POOLS_HEADLINE * oneshot_unit(FRAGS_PER_POOL_FULL, POOL_SIZE, a)
    head_hier = a["hier_pools"] * hierarchical_unit(FRAGS_PER_POOL_FULL, a)
    per_cell, grid = grid_cost(a)

    # J-vs-N curve: N = 1, 3, 5 on the reference cell (N=7 is the grid itself)
    curve = 0.0
    for n_docs in (1, 3, 5):
        frags = FRAGS_PER_POOL_CAP * n_docs / POOL_SIZE
        curve += N_POOLS_PER_CELL * oneshot_unit(frags, n_docs, a)

    # G3 positive control: unmasked + masked arm on 2 pools each
    ctrl = 4 * oneshot_unit(FRAGS_PER_POOL_FULL, POOL_SIZE, a)
    # G4 nuisance sizing, development subset, excluded from the confirmatory grid
    g4 = 8 * oneshot_unit(FRAGS_PER_POOL_CAP, POOL_SIZE, a)
    # paired L-only non-inferiority on the grid pools of the reference cell
    l_only = N_POOLS_PER_CELL * oneshot_unit(FRAGS_PER_POOL_CAP, POOL_SIZE, a) \
        / a["medoid_k"]
    # repeats: reference cell x2, the variance bound
    repeats = 2 * per_cell["sentence"]

    return [
        ("G3  positive control, unmasked + masked", ctrl),
        ("G4  nuisance sizing (development, excluded)", g4),
        ("1   Headline J, 71 pools, one-shot x medoid-3", head_one),
        (f"2   Headline J, hierarchical, {a['hier_pools']} pools", head_hier),
        ("3   Grid, 12 cells x 25 pools, capped", grid),
        ("4   J-vs-N curve, N = 1/3/5, reference cell", curve),
        ("5   L-only non-inferiority, paired, 25 pools", l_only),
        ("6   Repeats: reference cell x2", repeats),
        ("7   Memon joint attacker, every cell", 0.0),
    ], per_cell


def main():
    ap = argparse.ArgumentParser(description="Joint-run cost model. No API calls.")
    ap.add_argument("--sensitivity", action="store_true")
    ap.add_argument("--buffer", type=float, default=0.25,
                    help="fraction added for run-to-run variance")
    for key, val in DEFAULTS.items():
        ap.add_argument(f"--{key.replace('_', '-')}", type=type(val), default=val)
    args = ap.parse_args()
    a = {k: getattr(args, k) for k in DEFAULTS}

    print("UNIT COSTS (sonnet-5 intro + batch, $1/$5 per M)")
    print(f"  one-shot J, one generation, 184-frag pool   "
          f"${oneshot_cost(FRAGS_PER_POOL_FULL, 7, a):.4f}")
    print(f"  one-shot J, scored pool (medoid {a['medoid_k']} + retries)  "
          f"${oneshot_unit(FRAGS_PER_POOL_FULL, 7, a):.4f}")
    print(f"  hierarchical, one 184-frag pool at k={a['k']}       "
          f"${hierarchical_unit(FRAGS_PER_POOL_FULL, a):.4f}  "
          f"({EDGES_PER_FRAG[a['k']] * FRAGS_PER_POOL_FULL * BRIDGE_UPLIFT:.0f} pairs, "
          f"{EDGES_PER_FRAG[a['k']] * FRAGS_PER_POOL_FULL * BRIDGE_UPLIFT / PAIRS_PER_CALL:.0f} calls)")
    print(f"  memon joint, any pool                       $0.0000")
    print()

    rows, per_cell = line_items(a)
    total = 0.0
    for lbl, v in rows:
        total += v
        print(f"{lbl:48s} {v:8.2f}")
    print(f"{'    BASE':48s} {total:8.2f}")
    print(f"{f'    buffer {args.buffer:.0%}':48s} {total * args.buffer:8.2f}")
    grand = total * (1 + args.buffer)
    print(f"{'    TOTAL':48s} {grand:8.2f}")

    cap = 120.00
    verdict = "UNDER" if grand <= cap else "OVER"
    print(f"\n  tripwire ${cap:.2f}: {verdict} by ${abs(cap - grand):.2f}")
    print("  grid per cell: " +
          "  ".join(f"{g} ${per_cell[g]:.2f}" for g, _ in GRID_CELLS))

    print("\nSCENARIOS — the shape of the decision, not a recommendation")
    print(f"  {'configuration':<46}{'TOTAL':>9}{'cap':>8}")
    for label, over in (
            ("as planned: medoid-3 everywhere", {}),
            ("medoid-1 everywhere, repeats keep the variance bound",
             {"medoid_k": 1}),
            ("medoid-1, hierarchical on all 71 pools",
             {"medoid_k": 1, "hier_pools": 71}),
            ("medoid-1, no hierarchical arm",
             {"medoid_k": 1, "hier_pools": 0}),
            ("medoid-1, and J costs 1.8x L",
             {"medoid_k": 1, "j_over_l": 1.8}),
    ):
        b = dict(a); b.update(over)
        t = sum(x for _l, x in line_items(b)[0]) * (1 + args.buffer)
        print(f"  {label:<46}{t:>9.2f}{'ok' if t <= cap else 'OVER':>8}")

    if args.sensitivity:
        print("\nSENSITIVITY — the assumptions that can move the total")
        print(f"  {'parameter':<24}{'value':>8}{'TOTAL':>10}{'vs cap':>10}")
        for key, values in (("j_over_l", (1.0, 1.15, 1.4, 1.8)),
                            ("medoid_k", (1, 3, 5)),
                            ("retry_rate", (0.0, 0.15, 0.35)),
                            ("hier_pools", (0, 25, 71)),
                            ("pair_model_tax", (1.0, 1.5, 2.0)),
                            ("k", (3, 4, 5, 8))):
            for v in values:
                b = dict(a); b[key] = v
                t = sum(x for _l, x in line_items(b)[0]) * (1 + args.buffer)
                mark = "" if t <= cap else "  OVER"
                star = " *" if v == DEFAULTS[key] else "  "
                print(f"  {key:<24}{v:>8}{t:>10.2f}{mark:>10}{star}")

    payload = {
        "model": "joint",
        "measured": {
            "edges_per_frag": EDGES_PER_FRAG,
            "pair_out_fixed": PAIR_OUT_FIXED,
            "pair_out_per_pair": PAIR_OUT_PER_PAIR,
            "chars_per_frag_prompt": CHARS_PER_FRAG_PROMPT,
        },
        "assumed": a,
        "joint_per_cell": {g: round(per_cell[g], 4) for g, _ in GRID_CELLS},
        "unit_usd": {
            "oneshot_pool_full": round(oneshot_unit(FRAGS_PER_POOL_FULL, 7, a), 4),
            "hierarchical_pool_full": round(hierarchical_unit(FRAGS_PER_POOL_FULL, a), 4),
            "memon_pool": 0.0,
        },
        "totals": {"base_usd": round(total, 2),
                   "total_usd": round(grand, 2),
                   "cap_usd": cap,
                   "under_cap": grand <= cap},
    }
    print(JSON_BEGIN)
    print(json.dumps(payload, indent=2))
    print(JSON_END)


if __name__ == "__main__":
    main()
