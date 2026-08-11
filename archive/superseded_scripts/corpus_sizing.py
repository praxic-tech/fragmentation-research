#!/usr/bin/env python3
"""
corpus_sizing.py — pick a corpus size that minimises spend while keeping the
paper's claims statistically sound. NO API CALLS.

The central point
-----------------
Cost scales with TOTAL FRAGMENTS (n_docs x fragments/doc).
Statistical power scales with N_DOCS (each document is one independent
Kendall-tau observation for Game O).

Those are different quantities, so the cheapest way to keep power is to keep the
document COUNT and cut the fragments PER DOCUMENT — not the other way round.

Power model (Game O, the per-document metric)
---------------------------------------------
Under the null (random ordering) Kendall's tau on a k-fragment document has
    Var(tau) = 2(2k+5) / (9k(k-1))
so longer documents give *lower*-variance per-document estimates. The SE of a
corpus mean is sd_doc / sqrt(n_docs), and the minimum detectable difference
between two grid cells (paired, same documents cut two ways) is ~2.8 * SE_diff
at 80% power / alpha 0.05.

Usage:
    python corpus_sizing.py
    python corpus_sizing.py --window-k 25
"""

import argparse
import json
import math
import statistics as st
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
IN_PER_M, OUT_PER_M = 2.0, 10.0
CAL_IN, CAL_O_OUT = 1.541, 1.976
CAL_L_THINK, CAL_L_NOTHINK = 30.861, 2.082
LABEL_CHARS = 11
POOL_RECORDS = 100
CLAUSE_RATIO = 1.81          # measured on prose_v4 with spaCy
TOKENS_PER_SENT = 19.4       # measured: 308,532 tokens / 15,914 sentences

# 12 grid cells; cost depends only on granularity (4 sentence, 4 clause, 3 window,
# + llm-cut priced at the clause midpoint).
GRID = [("sentence", 4), ("clause", 4), ("token-window", 3), ("clause", 1)]


def tau_sd(k):
    """SD of Kendall tau for a random ordering of a k-fragment document."""
    if k < 2:
        return float("nan")
    return math.sqrt(2 * (2 * k + 5) / (9 * k * (k - 1)))


def load_meta(data):
    p = Path(data) / "prose_meta.jsonl"
    return [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()]


def build_corpus(meta, n_docs, bound, strata=None):
    """Select documents and apply a per-document fragment cap.
    strata: optional list of (lo, hi, count) on TRUE length, for stratified sampling."""
    rows = sorted(meta, key=lambda m: m.get("n_sentences_full", m["n_fragments"]))
    if strata:
        chosen = []
        for lo, hi, cnt in strata:
            band = [m for m in rows
                    if lo <= m.get("n_sentences_full", m["n_fragments"]) <= hi]
            if not band:
                continue
            step = max(1, len(band) // cnt)
            chosen += band[::step][:cnt]
        sel = chosen
    else:
        step = max(1, len(rows) // n_docs)
        sel = rows[::step][:n_docs]

    ks, chars = [], 0.0
    for m in sel:
        true_k = m.get("n_sentences_full", m["n_fragments"])
        k = min(true_k, bound)
        ks.append(k)
        # chars scale with the kept fraction of the document
        frac = k / true_k if true_k else 1.0
        chars += m["total_chars"] * frac
    return {"n_docs": len(ks), "ks": ks, "chars": chars, "frags": sum(ks)}


def cost_for(n_docs, chars, n_frags, l_factor):
    o_in = (chars + n_frags * LABEL_CHARS) / 4 + 150 * n_docs
    o_out = n_frags * 15
    pools = math.ceil(n_docs / POOL_RECORDS)
    l_in = (chars + n_frags * LABEL_CHARS) / 4 + 200 * pools
    l_out = n_frags * 3
    usd = lambda i, o: i / 1e6 * IN_PER_M + o / 1e6 * OUT_PER_M
    return (usd(o_in * CAL_IN, o_out * CAL_O_OUT)
            + usd(l_in * CAL_IN, l_out * l_factor))


def grid_total(c, window_k, l_factor, repeats):
    """Total for the 12-cell grid: repeats of semantic/sentence + 11 singles."""
    per_gran = {}
    for gran in ("sentence", "clause", "token-window"):
        if gran == "sentence":
            f = c["frags"]
        elif gran == "clause":
            f = round(c["frags"] * CLAUSE_RATIO)
        else:
            f = math.ceil(c["frags"] * TOKENS_PER_SENT / window_k)
        per_gran[gran] = cost_for(c["n_docs"], c["chars"], f, l_factor)
    cells = []
    for gran, count in GRID:
        cells += [per_gran[gran]] * count
    base = per_gran["sentence"]                      # the repeated cell
    return base * repeats + (sum(cells) - base), per_gran


def report(name, c, window_k, repeats, note=""):
    ks = c["ks"]
    sds = [tau_sd(k) for k in ks if k >= 2]
    sd_doc = st.mean(sds)
    se = sd_doc / math.sqrt(len(sds))
    mde = 2.8 * se * math.sqrt(2)      # unpaired two-cell difference; paired is tighter
    on, _ = grid_total(c, window_k, CAL_L_THINK, repeats)
    off, _ = grid_total(c, window_k, CAL_L_NOTHINK, repeats)
    hybrid, per = grid_total(c, window_k, CAL_L_NOTHINK, repeats)
    hybrid = hybrid - per["sentence"] * repeats + \
        cost_for(c["n_docs"], c["chars"], c["frags"], CAL_L_THINK) * repeats
    print(f"{name:26s} {c['n_docs']:5d} {c['frags']:8,d} "
          f"{st.mean(ks):6.1f} {min(ks):4d}-{max(ks):<4d} "
          f"{se:8.4f} {mde:7.3f} {on:9.2f} {hybrid:9.2f} {off:9.2f}  {note}")
    return {"name": name, "n_docs": c["n_docs"], "frags": c["frags"],
            "se": se, "mde": mde, "grid_on": on, "grid_hybrid": hybrid,
            "grid_off": off}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="./data/prose_v4")
    ap.add_argument("--window-k", type=int, default=25)
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()

    meta = load_meta(args.data)
    print("=" * 118)
    print(f" CORPUS SIZING — cost vs statistical power   "
          f"(token-window k={args.window_k}, semantic/sentence x{args.repeats})")
    print("=" * 118)
    print(f"{'config':26s} {'docs':>5s} {'frags':>8s} {'mean k':>6s} {'range':>9s} "
          f"{'SE(tau)':>8s} {'MDE':>7s} {'grid ON':>9s} {'hybrid':>9s} {'grid OFF':>9s}")
    print("-" * 118)

    out = []
    # current baseline
    out.append(report("A. 500 docs, bound 71",
                      build_corpus(meta, 500, 71), args.window_k, 5,
                      "current plan (x5)"))
    out.append(report("B. 500 docs, bound 30",
                      build_corpus(meta, 500, 30), args.window_k, args.repeats,
                      "cap length, keep n"))
    out.append(report("C. 250 docs, bound 30",
                      build_corpus(meta, 250, 30), args.window_k, args.repeats))
    out.append(report("D. 150 docs, bound 30",
                      build_corpus(meta, 150, 30), args.window_k, args.repeats))
    # stratified: keep length as a variable, few expensive long docs
    strat = [(5, 15, 60), (16, 30, 60), (31, 60, 40), (61, 300, 20)]
    out.append(report("E. 180 stratified",
                      build_corpus(meta, 180, 71, strata=strat), args.window_k,
                      args.repeats, "length kept as a variable"))
    strat2 = [(5, 15, 40), (16, 30, 40), (31, 60, 25), (61, 300, 15)]
    out.append(report("F. 120 stratified",
                      build_corpus(meta, 120, 71, strata=strat2), args.window_k,
                      args.repeats, "leanest defensible"))
    out.append(report("G. 500 short only",
                      build_corpus(meta, 500, 71, strata=[(5, 15, 500)]),
                      args.window_k, args.repeats, "NO length variance"))

    print("-" * 118)
    print("  SE(tau)  = standard error of the corpus-mean Kendall tau under the null")
    print("  MDE      = smallest tau difference between two grid cells detectable at")
    print("             80% power / alpha .05 (unpaired; paired across the same docs is tighter)")
    print("  hybrid   = thinking ON for the repeated cell, OFF for the 11 exploratory cells")
    print()
    print("  For scale: the effect you are measuring is LLM tau ~0.97 vs random ~0.00.")
    print("  Every config above resolves that by a factor of 20+ — n is not the")
    print("  binding constraint on the headline claim. MDE matters only for")
    print("  distinguishing CELLS from each other (e.g. does coherence-sever beat semantic).")

    (HERE / "corpus_sizing.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
