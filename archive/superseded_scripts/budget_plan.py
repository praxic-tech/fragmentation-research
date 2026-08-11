#!/usr/bin/env python3
"""
budget_plan.py — two-tier experiment plan for an undergrad-sized budget.
NO API CALLS.

The problem with the one-tier plan
----------------------------------
corpus_sizing.py asked "how big should THE corpus be?" and every answer traded
document count against money, because it priced all 12 grid cells at the same n.
That is the wrong shape for the constraint.

Reviewers judge n on the HEADLINE claim ("LLM reassembly recovers tau=0.97 on
500 real post-cutoff clinical documents"). They do not require every ablation
cell to run at the headline n — a 12-cell sweep on a stratified subset is
normal practice, provided one cell is run at BOTH sizes so the sweep is
anchored to the headline corpus.

So: two tiers.
  Tier 1  headline cell, all 500 documents, repeated (run-to-run variance).
  Tier 2  the 12-cell grid on a stratified subset, single run each.
          The sentence cell in tier 2 is the BRIDGE — same config as tier 1 —
          which is what licenses comparing tier-2 cells to the headline.

Cost model is imported from corpus_sizing.py so there is one source of truth.

Usage:
    python budget_plan.py
    python budget_plan.py --budget 60
    python budget_plan.py --think-cap 4000
"""

import argparse
import json
import math
import statistics as st
from pathlib import Path

import corpus_sizing as cs
from corpus_sizing import (
    GRID, CLAUSE_RATIO, TOKENS_PER_SENT, POOL_RECORDS,
    CAL_IN, CAL_O_OUT, CAL_L_THINK, CAL_L_NOTHINK, LABEL_CHARS,
    tau_sd, load_meta, build_corpus, cost_for,
)

HERE = Path(__file__).resolve().parent

# claude-sonnet-5 list price is $3 / $15 per MTok.  corpus_sizing.py hardcodes
# $2 / $10 — the INTRODUCTORY rate, which expires 2026-08-31.  Every figure this
# script prints by default is therefore an intro-rate figure with 4 weeks left
# on it.  --list-price re-prices at $3/$15; --batch applies the Message Batches
# API's flat 50% discount (this workload is offline, so batch is free money).
LIST_IN_PER_M, LIST_OUT_PER_M = 3.0, 15.0
INTRO_IN_PER_M, INTRO_OUT_PER_M = 2.0, 10.0


def set_prices(list_price: bool, batch: bool):
    """Rebind the price constants used by both this module and corpus_sizing."""
    scale = 0.5 if batch else 1.0
    if list_price:
        cs.IN_PER_M, cs.OUT_PER_M = LIST_IN_PER_M * scale, LIST_OUT_PER_M * scale
    else:
        cs.IN_PER_M, cs.OUT_PER_M = INTRO_IN_PER_M * scale, INTRO_OUT_PER_M * scale
    return cs.IN_PER_M, cs.OUT_PER_M

# Measured on the reasoning sweep, thinking=disabled run: the linkage ANSWER
# alone was 1,151 tokens against an estimate of 280*3=840.  Used only by the
# --think-cap model, which prices thinking per CALL rather than per fragment.
CAL_L_ANSWER = 1.37

# Stratified presets.  Band 5-15 holds only 48 documents in prose_v4, so any
# request above 48 there silently yields 48 — that is why "180 stratified"
# lands at 168 documents.
STRATA = {
    180: [(5, 15, 60), (16, 30, 60), (31, 60, 40), (61, 300, 20)],
    120: [(5, 15, 40), (16, 30, 40), (31, 60, 25), (61, 300, 15)],
    90:  [(5, 15, 30), (16, 30, 30), (31, 60, 20), (61, 300, 10)],
    60:  [(5, 15, 20), (16, 30, 20), (31, 60, 13), (61, 300, 7)],
}


def cost_for_capped(n_docs, chars, n_frags, cap, pool_records):
    """Cost with an explicit thinking budget instead of adaptive thinking.

    EXTRAPOLATED, not measured.  Thinking is billed per CALL (pools * cap),
    which is how a max-thinking-tokens cap actually behaves, rather than the
    per-fragment multiplier the adaptive runs were fit with.
    """
    o_in = (chars + n_frags * LABEL_CHARS) / 4 + 150 * n_docs
    o_out = n_frags * 15
    pools = math.ceil(n_docs / pool_records)
    l_in = (chars + n_frags * LABEL_CHARS) / 4 + 200 * pools
    l_out = n_frags * 3 * CAL_L_ANSWER + pools * cap
    usd = lambda i, o: i / 1e6 * cs.IN_PER_M + o / 1e6 * cs.OUT_PER_M
    return (usd(o_in * CAL_IN, o_out * CAL_O_OUT)
            + usd(l_in * CAL_IN, l_out))


def cost_for_ceiling(n_docs, chars, n_frags, max_tokens, pool_records):
    """Hard upper bound: every linkage call billed at the full output cap.

    This is the number to budget against.  The CAL_L_THINK=30.861 multiplier
    was fit on a single 280-fragment call that produced 25,210 thinking tokens
    (90 tokens/fragment).  Multiplying that rate by fragment count implies
    >32,000 output tokens for any call above ~355 fragments, which the API
    cannot emit — the sweep already hit max_tokens on that very pool at medium
    effort.  So adaptive-thinking cost SATURATES at the cap; it does not scale
    linearly with corpus size, and any estimate that says otherwise is pricing
    tokens the model is structurally unable to produce.
    """
    o_in = (chars + n_frags * LABEL_CHARS) / 4 + 150 * n_docs
    o_out = n_frags * 15
    pools = math.ceil(n_docs / pool_records)
    l_in = (chars + n_frags * LABEL_CHARS) / 4 + 200 * pools
    usd = lambda i, o: i / 1e6 * cs.IN_PER_M + o / 1e6 * cs.OUT_PER_M
    return (usd(o_in * CAL_IN, o_out * CAL_O_OUT)
            + usd(l_in * CAL_IN, pools * max_tokens))


def cell_cost(c, gran, window_k, think, window_k_arg, pool_records):
    """Cost of ONE grid cell at a given granularity."""
    if gran == "sentence":
        f = c["frags"]
    elif gran == "clause":
        f = round(c["frags"] * CLAUSE_RATIO)
    else:
        f = math.ceil(c["frags"] * TOKENS_PER_SENT / window_k_arg)
    if isinstance(think, tuple):
        kind, n_tok = think
        if kind == "ceiling":
            return cost_for_ceiling(c["n_docs"], c["chars"], f, n_tok, pool_records)
        return cost_for_capped(c["n_docs"], c["chars"], f, n_tok, pool_records)
    return cost_for(c["n_docs"], c["chars"], f, think)


def grid_once(c, window_k, think, pool_records):
    """All 12 cells, each run exactly once."""
    per = {g: cell_cost(c, g, window_k, think, window_k, pool_records)
           for g in ("sentence", "clause", "token-window")}
    return sum(per[g] * n for g, n in GRID), per


def power(c):
    """SE and MDE of the corpus-mean Kendall tau under the null."""
    sds = [tau_sd(k) for k in c["ks"] if k >= 2]
    se = st.mean(sds) / math.sqrt(len(sds))
    return se, 2.8 * se * math.sqrt(2)


def plan(meta, name, n1, bound1, repeats, think1, n2, think2,
         window_k, pool_records, note=""):
    t1 = build_corpus(meta, n1, bound1)
    t2 = build_corpus(meta, n2, 71, strata=STRATA[n2])

    c1 = cell_cost(t1, "sentence", window_k, think1, window_k, pool_records) * repeats
    c2, _ = grid_once(t2, window_k, think2, pool_records)

    se1, mde1 = power(t1)
    se2, mde2 = power(t2)
    return {
        "name": name, "note": note,
        "t1_docs": t1["n_docs"], "t1_frags": t1["frags"], "t1_repeats": repeats,
        "t1_se": se1, "t1_ci95": 1.96 * se1, "t1_cost": c1,
        "t2_docs": t2["n_docs"], "t2_frags": t2["frags"],
        "t2_mde": mde2, "t2_mde_paired": mde2 / math.sqrt(2), "t2_cost": c2,
        "total": c1 + c2,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="./data/prose_v4")
    ap.add_argument("--window-k", type=int, default=25)
    ap.add_argument("--pool-records", type=int, default=POOL_RECORDS)
    ap.add_argument("--think-cap", type=int, default=0,
                    help="model an explicit thinking budget (tokens/call) "
                         "instead of adaptive thinking; EXTRAPOLATED")
    ap.add_argument("--ceiling", type=int, default=0, metavar="MAX_TOKENS",
                    help="hard upper bound: bill every linkage call at the "
                         "full output cap. This is the budgeting number.")
    ap.add_argument("--budget", type=float, default=0.0,
                    help="flag plans over this USD total")
    ap.add_argument("--list-price", action="store_true",
                    help="price at $3/$15 (list) instead of $2/$10 (intro, "
                         "expires 2026-08-31)")
    ap.add_argument("--batch", action="store_true",
                    help="apply the Message Batches API 50%% discount")
    args = ap.parse_args()

    in_rate, out_rate = set_prices(args.list_price, args.batch)
    price_label = (f"${in_rate:g}/${out_rate:g} per MTok"
                   f"{' (list)' if args.list_price else ' (intro, ends 2026-08-31)'}"
                   f"{' + batch 50%' if args.batch else ''}")

    meta = load_meta(args.data)
    if args.ceiling:
        ON = ("ceiling", args.ceiling)
        on_label = f"CEILING @ {args.ceiling} max_tokens"
    elif args.think_cap:
        ON = ("cap", args.think_cap)
        on_label = f"cap {args.think_cap}"
    else:
        ON = CAL_L_THINK
        on_label = "adaptive (unsaturated model — see cost_for_ceiling)"
    OFF = ("ceiling", args.ceiling) if args.ceiling else CAL_L_NOTHINK

    plans = [
        plan(meta, "1. 500 full x3 + 180 grid", 500, 71, 3, ON, 180, OFF,
             args.window_k, args.pool_records, "max defensibility"),
        plan(meta, "2. 500 full x3 + 120 grid", 500, 71, 3, ON, 120, OFF,
             args.window_k, args.pool_records),
        plan(meta, "3. 500 full x2 + 120 grid", 500, 71, 2, ON, 120, OFF,
             args.window_k, args.pool_records, "recommended"),
        plan(meta, "4. 500 cap40 x2 + 120 grid", 500, 40, 2, ON, 120, OFF,
             args.window_k, args.pool_records, "truncates 61+ band"),
        plan(meta, "5. 500 cap30 x2 + 120 grid", 500, 30, 2, ON, 120, OFF,
             args.window_k, args.pool_records, "truncates 31+ band"),
        plan(meta, "6. 500 full x2 + 90 grid", 500, 71, 2, ON, 90, OFF,
             args.window_k, args.pool_records, "leanest with n=500"),
        plan(meta, "7. 500 full x2 + 60 grid", 500, 71, 2, ON, 60, OFF,
             args.window_k, args.pool_records, "grid bands get thin"),
        plan(meta, "8. 500 full x1 + 90 grid", 500, 71, 1, ON, 90, OFF,
             args.window_k, args.pool_records, "no run-to-run variance"),
    ]

    print("=" * 112)
    print(f" TWO-TIER BUDGET PLAN   (window k={args.window_k}, "
          f"pools of {args.pool_records} docs, headline thinking: {on_label})")
    print(f" pricing: {price_label}")
    print("=" * 112)
    print(f"{'plan':28s} {'T1 docs':>7s} {'T1 frag':>8s} {'95% CI':>8s} "
          f"{'T1 $':>7s} | {'T2 docs':>7s} {'MDE(pr)':>8s} {'T2 $':>7s} | "
          f"{'TOTAL':>8s}")
    print("-" * 112)
    for p in plans:
        flag = "  <-- OVER" if args.budget and p["total"] > args.budget else ""
        print(f"{p['name']:28s} {p['t1_docs']:7d} {p['t1_frags']:8,d} "
              f"{p['t1_ci95']:8.4f} {p['t1_cost']:7.2f} | "
              f"{p['t2_docs']:7d} {p['t2_mde_paired']:8.3f} {p['t2_cost']:7.2f} | "
              f"{p['total']:8.2f}  {p['note']}{flag}")
    print("-" * 112)
    print("  T1 = headline cell (sentence granularity) on the full corpus, repeated.")
    print("  T2 = 12-cell ablation grid on a stratified subset, one run per cell.")
    print("       The sentence cell of T2 is the bridge back to T1.")
    print("  95% CI = half-width on the headline corpus-mean tau.")
    print("  MDE(pr) = smallest tau gap between two T2 cells detectable at 80%")
    print("            power / alpha .05, paired across the same documents,")
    print("            assuming cell-to-cell correlation rho=0.5.")

    (HERE / "budget_plan.json").write_text(json.dumps(plans, indent=2),
                                           encoding="utf-8")


if __name__ == "__main__":
    main()
