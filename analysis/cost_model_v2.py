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
    J_OVER_L        1.9    The output anchors are GAME L. J asks for membership
                           AND order in one answer. Was an assumed 1.15;
                           MEASURED 1.9 on grid pool 1 over the 4 J pools that
                           finished, a LOWER BOUND because the 7 that ran into
                           their cap wanted more. Re-measure after the re-ask.
    O_OUT_MEASURED  1.6    Game O ran 1.6x its anchors on pool 1 (55 finished
                           documents), also a lower bound.
    MEDOID_K        3      One-shot J only. [R4] forbids it on the hierarchical
                           attacker, where 3 pipelines would mean ~130 extra
                           calls per pool.
    RETRY_RATE      0.15   Fraction of units needing one repair round.
    PAIR_MODEL_TAX  1.0    The pair-output figure was measured on
                           gpt-oss-120b, not sonnet. 1.0 assumes they match.
    PRICES          $1/$5 per M in/out: claude-sonnet-5 list $2/$10, halved by
                           the Batches API. Verify at purchase.

Run:  python analysis/cost_model_v2.py
      python analysis/cost_model_v2.py --sensitivity
"""

import argparse
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

JSON_BEGIN = "===COST_MODEL_JSON_BEGIN==="
JSON_END = "===COST_MODEL_JSON_END==="

# ── prices: claude-sonnet-5 lists at $2/$10 per M; batch is 50% -> $1/$5 ─────
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

# ── game O: ordering ONE document whose membership is given ──────────────────
#
# O is a SECOND THREAT MODEL, not a methodological convenience: the metadata
# layer is compromised, the attacker learns which fragments belong together, but
# content is still fragmented. It is also the only way to get a per-cell
# ordering number whose denominator does not move between cells -- q = C/K under
# J is measured on pairs the attacker itself grouped correctly, and that
# denominator shifts whenever a strategy makes grouping harder.
#
# Measured on sonnet-5, batch, ordering one document (the O+L model's anchors,
# still the best data for this shape):
#     13 frags ->    323 tok        31 frags ->  3,440 tok (mean of two runs)
#     22 frags ->    579 tok        76 frags -> 24,001 tok
# Not a power law: roughly linear below ~22 fragments, then reasoning switches on
# and it goes superlinear (log-log slope 1.88 above 31). The same document
# measured twice at 31 fragments came back 1.82x apart, which is why the buffer
# exists and why this arm is the most volatile line in the model.
ORD_ANCHORS = [(13, 323), (22, 579), (31, 3440), (76, 24001)]
O_DOCS_PER_CELL = 60          # enough to rank strategies unless effects are tiny


def ordering_out_tokens(k):
    """Output tokens to order a k-fragment document. Piecewise through anchors."""
    k = max(3, k)
    if k <= ORD_ANCHORS[0][0]:
        return ORD_ANCHORS[0][1] * (k / ORD_ANCHORS[0][0]) ** 1.11
    for (x1, y1), (x2, y2) in zip(ORD_ANCHORS, ORD_ANCHORS[1:]):
        if k <= x2:
            slope = math.log(y2 / y1) / math.log(x2 / x1)
            return y1 * (k / x1) ** slope
    return min(ORD_ANCHORS[-1][1] * (k / ORD_ANCHORS[-1][0]) ** 1.88, 64000)


def ordering_cost(k, a):
    """One game-O unit: one document, membership given, order it."""
    inp = (CHARS_PER_FRAG_PROMPT * k / 4.0 + 150) * CAL_IN
    out = ordering_out_tokens(k) * O_OUT_MEASURED
    return (inp / 1e6 * IN_PER_M + out / 1e6 * OUT_PER_M) * (1 + a["retry_rate"])


# ── max_tokens for the PAID path ─────────────────────────────────────────────
#
# claude-sonnet-5 runs ADAPTIVE THINKING BY DEFAULT, and thinking tokens are
# billed as output and count against max_tokens even though the thinking text
# comes back empty. So a cap sized to the bare JSON answer (~3 tok/fragment) is
# sized to the wrong thing. batch_submit's default was 4,096 and the control
# spec's 8,192, against measured sonnet output of ~14-21k for a 7-document pool:
# the paid run would have come back empty or cut off mid-JSON, and the
# completeness gate would then have refused it -- safe, and a waste of money.
#
# A generous cap costs nothing extra: batches bill ACTUAL usage. 128,000 is
# sonnet-5's output ceiling.
#
# RESIZED after grid pool 1 (batch msgbatch_018bZWoLWVBec9de8iR5wYYG). Sized at
# 2x the anchors, 30 of 88 answers ran into their cap and came back empty or
# cut off mid-JSON: 7 of 11 J pools and 23 of 77 O documents, five of them at
# the old 2,048 floor. The 58 that finished used 1.6x the O anchors and 1.9x the
# L anchors for J -- lower bounds, since the cut-off answers wanted more. So:
#   J / L   always the ceiling. The worst J seen was cut off at 69,753 and a
#           pool answer has no small case worth a tighter cap.
#   O       also the ceiling (D6). Sized at SIZING_MARGIN x the measured rate
#           with a 16k floor, 3 of 23 re-asked documents were cut off AGAIN at
#           16-21k; a tighter cap buys nothing but re-asks.
# A cap only truncates -- it never changes the tokens before the cut -- so an
# answer that finished under the old caps is the answer it would have been
# under these, and the 58 stay valid.
MODEL_MAX_OUTPUT = 128000
SIZING_MARGIN = 3.0
O_FLOOR = 16000
O_OUT_MEASURED = 1.6               # pool 1: mean actual / ORD_ANCHORS model


def expected_out_tokens(game, n_frags, n_groups=1):
    """Expected output tokens for one unit, at the rates measured on pool 1."""
    if game == "O" or n_groups <= 1:
        return ordering_out_tokens(n_frags) * O_OUT_MEASURED
    if game in ("J", "L"):
        need = oneshot_out_tokens(n_frags, n_groups)
        return need * DEFAULTS["j_over_l"] if game == "J" else need
    raise ValueError(f"unknown game {game!r}")


def max_tokens_for(game, n_frags, n_groups=1, margin=SIZING_MARGIN,
                   cap=MODEL_MAX_OUTPUT):
    """Per-request max_tokens for one game unit on the paid path."""
    if game not in ("O", "L", "J"):
        raise ValueError(f"unknown game {game!r}")
    # RUN_DECISIONS D6: every request gets the model's full ceiling and ONE
    # attempt. A cap below it only manufactures cut-offs -- pool 1's O documents
    # sized at 3x the measured rate were still cut off at 16-21k and re-asked --
    # and batches bill actual usage, so the ceiling costs nothing.
    return cap


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
# medoid_k = 1 is FORCED, not preferred. At k=3 the run is $238 against a $150
# hard limit: it does not fit at any other setting, so there was no trade to
# make. What k=1 gives up is variance reduction WITHIN a pool; the estimates
# rest on 71 pools (headline) and 25 per grid cell, and averaging across pools
# is what the error bars actually use. Line item 6 (repeats, reference cell x2)
# measures the run-to-run variance directly, so the thing medoid-of-k was
# insuring against gets reported rather than assumed away.
#
# repair.select_medoid stays in the tree and is a passthrough at k=1. This is a
# budget setting, not a deletion.
#
# The freed room goes to hier_pools=71: the hierarchical attacker across the
# WHOLE headline instead of a 25-pool subset. That buys a second attacker on
# every headline pool for $22, where medoid-3 would have bought tighter
# per-pool numbers for $166.
DEFAULTS = dict(j_over_l=1.9, medoid_k=1, retry_rate=0.15,
                pair_model_tax=1.0, k=5, hier_pools=71, o_arm=1)


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

    # Per-cell game O. FRAGMENTS PER DOCUMENT drives this, not pool size: O
    # asks about one document at a time.
    frags_per_doc_cap = FRAGS_PER_POOL_CAP / POOL_SIZE
    o_arm = 0.0
    if a["o_arm"]:
        for gran, n_cells in GRID_CELLS:
            k = frags_per_doc_cap * GRANULARITY_MULT[gran]
            o_arm += n_cells * O_DOCS_PER_CELL * ordering_cost(k, a)

    return [
        ("G3  positive control, unmasked + masked", ctrl),
        ("G4  nuisance sizing (development, excluded)", g4),
        (f"1   Headline J, 71 pools, one-shot x medoid-{a['medoid_k']}", head_one),
        (f"2   Headline J, hierarchical, {a['hier_pools']} pools", head_hier),
        ("3   Grid, 12 cells x 25 pools, capped", grid),
        ("4   J-vs-N curve, N = 1/3/5, reference cell", curve),
        ("5   L-only non-inferiority, paired, 25 pools", l_only),
        ("6   Repeats: reference cell x2", repeats),
        ("7   Memon joint attacker, every cell", 0.0),
        (f"8   Per-cell game O, {O_DOCS_PER_CELL} docs x 12 cells", o_arm),
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

    cap, wall = 120.00, 167.00
    verdict = "UNDER" if grand <= cap else "OVER"
    print(f"\n  tripwire ${cap:.2f}: {verdict} by ${abs(cap - grand):.2f}")
    print(f"  hard limit ${wall:.2f}: {'UNDER' if grand <= wall else 'OVER'} by ${abs(wall - grand):.2f}")
    print("  grid per cell: " +
          "  ".join(f"{g} ${per_cell[g]:.2f}" for g, _ in GRID_CELLS))

    print("\nSCENARIOS — the shape of the decision, not a recommendation")
    print(f"  {'configuration':<46}{'TOTAL':>9}{'vs $120/$150':>10}")
    for label, over in (
            ("SELECTED: medoid-1, hierarchical on all 71 pools", {}),
            ("...if J turns out to cost 2.2x L", {"j_over_l": 2.2}),
            ("...if J turns out to cost 2.6x L", {"j_over_l": 2.6}),
            ("...if repairs run hot (35% retry)", {"retry_rate": 0.35}),
            ("...and sonnet reasons 2x harder on pairs",
             {"pair_model_tax": 2.0}),
            ("without the per-cell O arm", {"o_arm": 0}),
            ("fallback: drop the hierarchical arm", {"hier_pools": 0}),
            ("the old plan: medoid-3 everywhere", {"medoid_k": 3}),
    ):
        b = dict(a); b.update(over)
        t = sum(x for _l, x in line_items(b)[0]) * (1 + args.buffer)
        flag = "ok" if t <= cap else ("tripwire" if t <= wall else "OVER")
        print(f"  {label:<46}{t:>9.2f}{flag:>10}")

    if args.sensitivity:
        print("\nSENSITIVITY — the assumptions that can move the total")
        print(f"  {'parameter':<24}{'value':>8}{'TOTAL':>10}{'vs cap':>10}")
        for key, values in (("j_over_l", (1.15, 1.9, 2.2, 2.6)),
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
