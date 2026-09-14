"""
analyze.py — every table, comparison and relationship docs/results_plan.md
requires, from MASTER_RESULTS.csv (and the raw reconstructions, for the §19
error taxonomy). No API calls.

Uncertainty (RUN_DECISIONS D13): percentile bootstrap over the independent
units (pools for J, documents for O), 10,000 resamples, seed 42 (a fresh
generator per interval, so every interval is reproducible on its own). Paired
comparisons resample a unit once and carry both conditions. Spearman rho is
bootstrapped over unit rows; pooled across cells, over pool (or document) IDs
carrying all their rows. 95% CIs; 90% for the identifier rule; t-intervals as
sensitivity only. No multiplicity adjustment (the plan specifies none).

Writes TABLES/ (csv full precision + md + tex), figure_data/, KEY_NUMBERS.json.

    python results/final_analysis/scripts/analyze.py
"""

import csv
import json
import math
import os
import statistics as st
import sys
from collections import Counter, defaultdict

import numpy as np
from scipy import stats as sps

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(PKG))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

B, SEED = 10_000, 42
TAB, FD = os.path.join(PKG, "TABLES"), os.path.join(PKG, "figure_data")
GRID = ["random__sentence", "semantic__sentence", "subject-verb__sentence",
        "random__clause", "semantic__clause", "coherence-sever__clause", "subject-verb__clause",
        "random__token-window", "coherence-sever__token-window"]
REF = "semantic__sentence"
LABEL = {c: c.replace("__", " / ") for c in GRID}
LABEL.update({"semantic__sentence (full length)": "headline (full length)", "identifier__field": "identifier"})
WITHIN_GRAN = {"sentence": ["random__sentence", "semantic__sentence", "subject-verb__sentence"],
               "clause": ["random__clause", "semantic__clause", "coherence-sever__clause", "subject-verb__clause"],
               "token-window": ["random__token-window", "coherence-sever__token-window"]}
WITHIN_STRAT = {"random": ["random__sentence", "random__clause", "random__token-window"],
                "semantic": ["semantic__sentence", "semantic__clause"],
                "coherence-sever": ["coherence-sever__clause", "coherence-sever__token-window"],
                "subject-verb": ["subject-verb__sentence", "subject-verb__clause"]}
KEY = {}


# ── loading ──────────────────────────────────────────────────────────────────
def conv(v):
    if v == "":
        return None
    if v in ("True", "False"):
        return v == "True"
    try:
        return float(v)
    except ValueError:
        return v


R = [{k: conv(v) for k, v in r.items()} for r in
     csv.DictReader(open(os.path.join(PKG, "MASTER_RESULTS.csv"), encoding="utf-8"))]


def sel(game, family=None, attacker=None, cell=None, completed=True):
    return [r for r in R if r["game"] == game and (family is None or r["family"] == family)
            and (attacker is None or r["attacker"] == attacker) and (cell is None or r["cell"] == cell)
            and (not completed or r["completion"] == "completed")]


# ── statistics ───────────────────────────────────────────────────────────────
def _idx(n):
    return np.random.default_rng(SEED).integers(0, n, size=(B, n))


def ci_mean(x, level=0.95):
    x = np.asarray([v for v in x if v is not None], float)
    if len(x) == 0:
        return (math.nan,) * 3
    if len(x) == 1 or np.all(x == x[0]):
        return float(x.mean()), float(x.mean()), float(x.mean())
    bs = x[_idx(len(x))].mean(1)
    a = (1 - level) / 2
    return float(x.mean()), float(np.quantile(bs, a)), float(np.quantile(bs, 1 - a))


def ci_median(x, level=0.95):
    x = np.asarray([v for v in x if v is not None], float)
    if len(x) < 2:
        return (float(np.median(x)) if len(x) else math.nan,) * 3
    bs = np.median(x[_idx(len(x))], axis=1)
    a = (1 - level) / 2
    return float(np.median(x)), float(np.quantile(bs, a)), float(np.quantile(bs, 1 - a))


def ci_ratio(num, den, level=0.95):
    num, den = np.asarray(num, float), np.asarray(den, float)
    if len(num) == 0 or den.sum() == 0:
        return (math.nan,) * 3
    i = _idx(len(num))
    bs = num[i].sum(1) / den[i].sum(1)
    a = (1 - level) / 2
    return float(num.sum() / den.sum()), float(np.quantile(bs, a)), float(np.quantile(bs, 1 - a))


def t_ci(x, level=0.95):
    x = np.asarray([v for v in x if v is not None], float)
    if len(x) < 2:
        return (math.nan,) * 2
    h = sps.t.ppf(1 - (1 - level) / 2, len(x) - 1) * x.std(ddof=1) / math.sqrt(len(x))
    return float(x.mean() - h), float(x.mean() + h)


def paired(a, b, level=0.95):
    """a, b: dicts unit -> value. Resample the unit ONCE, carry both values."""
    units = sorted(u for u in a if u in b and a[u] is not None and b[u] is not None)
    if not units:
        return {"n_pairs": 0}
    A, Bv = np.array([a[u] for u in units]), np.array([b[u] for u in units])
    i = _idx(len(units))
    mean_bs = A[i].mean(1) - Bv[i].mean(1)            # both conditions carried together
    med_bs = np.median(A[i] - Bv[i], axis=1)
    q = (1 - level) / 2
    d = A - Bv
    lo_t, hi_t = t_ci(d, level)
    return {"n_pairs": len(units), "mean_diff": float(d.mean()),
            "mean_lo": float(np.quantile(mean_bs, q)), "mean_hi": float(np.quantile(mean_bs, 1 - q)),
            "median_diff": float(np.median(d)), "median_lo": float(np.quantile(med_bs, q)),
            "median_hi": float(np.quantile(med_bs, 1 - q)), "t_lo": lo_t, "t_hi": hi_t,
            "frac_a_higher": float((d > 0).mean())}


def _rank_rows(M):
    return sps.rankdata(M, axis=1)


def spearman(x, y, clusters=None, level=0.95):
    pts = [(a, b, c) for a, b, c in zip(x, y, clusters or [None] * len(x)) if a is not None and b is not None]
    if len(pts) < 4:
        return {"n": len(pts), "rho": math.nan, "lo": math.nan, "hi": math.nan}
    X = np.array([p[0] for p in pts], float)
    Y = np.array([p[1] for p in pts], float)
    if np.all(X == X[0]) or np.all(Y == Y[0]):
        return {"n": len(pts), "rho": math.nan, "lo": math.nan, "hi": math.nan}
    rho = float(sps.spearmanr(X, Y).statistic)
    q = (1 - level) / 2
    if clusters is None:
        i = _idx(len(X))
        rx, ry = _rank_rows(X[i]), _rank_rows(Y[i])
        rx -= rx.mean(1, keepdims=True)
        ry -= ry.mean(1, keepdims=True)
        den = np.sqrt((rx ** 2).sum(1) * (ry ** 2).sum(1))
        bs = np.where(den > 0, (rx * ry).sum(1) / np.where(den > 0, den, 1), np.nan)
    else:
        C = [p[2] for p in pts]
        ids = sorted(set(C))
        rows_of = {c: [k for k, cc in enumerate(C) if cc == c] for c in ids}
        ci = np.random.default_rng(SEED).integers(0, len(ids), size=(B, len(ids)))
        bs = np.empty(B)
        for b in range(B):
            rr = [k for j in ci[b] for k in rows_of[ids[j]]]
            xs, ys = X[rr], Y[rr]
            bs[b] = sps.spearmanr(xs, ys).statistic if xs.std() > 0 and ys.std() > 0 else np.nan
    bs = bs[~np.isnan(bs)]
    return {"n": len(pts), "rho": rho, "lo": float(np.quantile(bs, q)), "hi": float(np.quantile(bs, 1 - q)),
            "clusters": len(set(clusters)) if clusters else len(pts)}


# ── output helpers ───────────────────────────────────────────────────────────
def fmt(v, d=4):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.{d}f}"
    return str(v)


def tex_escape(s):
    return (str(s).replace("\\", r"\textbackslash{}").replace("_", r"\_").replace("%", r"\%")
            .replace("&", r"\&").replace("#", r"\#").replace("×", r"$\times$").replace("≥", r"$\geq$")
            .replace("ρ", r"$\rho$").replace("τ", r"$\tau$").replace("—", "--").replace("±", r"$\pm$"))


def write_table(name, rows, cols=None, title="", label="", note="", digits=4):
    os.makedirs(TAB, exist_ok=True)
    cols = cols or list(rows[0]) if rows else []
    with open(os.path.join(TAB, name + ".csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})
    md = [f"### {title}", "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    md += ["| " + " | ".join(fmt(r.get(k), digits) for k in cols) + " |" for r in rows]
    if note:
        md += ["", note]
    open(os.path.join(TAB, name + ".md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    tex = [r"% generated by results/final_analysis/scripts/analyze.py from TABLES/" + name + ".csv",
           r"\begin{table}[t]\centering\scriptsize", r"\caption{" + tex_escape(title) + "}",
           r"\label{" + (label or "tab:" + name) + "}", r"\resizebox{\linewidth}{!}{%",
           r"\begin{tabular}{" + "l" * len(cols) + "}", r"\toprule",
           " & ".join(tex_escape(c) for c in cols) + r" \\", r"\midrule"]
    tex += [" & ".join(tex_escape(fmt(r.get(k), digits)) for k in cols) + r" \\" for r in rows]
    tex += [r"\bottomrule", r"\end{tabular}}"]
    if note:
        tex.append(r"\par\smallskip\parbox{\linewidth}{\tiny " + tex_escape(note) + "}")
    tex.append(r"\end{table}")
    open(os.path.join(TAB, name + ".tex"), "w", encoding="utf-8").write("\n".join(tex) + "\n")


def write_fd(name, rows, cols=None):
    os.makedirs(FD, exist_ok=True)
    cols = cols or list(rows[0])
    with open(os.path.join(FD, name + ".csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("nan" if r.get(k) is None or (isinstance(r.get(k), float) and math.isnan(r.get(k)))
                            else r.get(k)) for k in cols})


# ── game J summaries ─────────────────────────────────────────────────────────
def j_summary(rows_all, level=0.95):
    done = [r for r in rows_all if r["completion"] == "completed"]
    out = {"attempted": len(rows_all), "completed": len(done),
           "rbnc": sum(1 for r in rows_all if r["completion"] == "rbnc")}
    out["completion_rate"] = out["completed"] / out["attempted"] if out["attempted"] else math.nan
    f1 = [r["F1_J"] for r in done]
    out["F1_J_mean"], out["F1_J_lo"], out["F1_J_hi"] = ci_mean(f1, level)
    out["F1_J_t_lo"], out["F1_J_t_hi"] = t_ci(f1, level)
    out["F1_J_median"], out["F1_J_med_lo"], out["F1_J_med_hi"] = ci_median(f1, level)
    out["F1_J_min"], out["F1_J_max"] = (min(f1), max(f1)) if f1 else (math.nan, math.nan)
    for k in ("precision_J", "recall_J", "b_J", "A_J", "F1_L", "L_precision", "L_recall"):
        vals = [r.get(k) for r in done if r.get(k) is not None]
        if vals:
            out[k + "_mean"], out[k + "_lo"], out[k + "_hi"] = ci_mean(vals, level)
    qd = [r["q"] for r in done if r.get("q") is not None and (r.get("K") is None or r["K"] > 0)]
    out["q_mean"], out["q_lo"], out["q_hi"] = ci_mean(qd, level)
    out["K0_pools"] = sum(1 for r in done if r.get("K") == 0)
    ck = [(r["C"], r["K"]) for r in done if r.get("C") is not None and r.get("K") is not None]
    if ck:
        out["q_micro"], out["q_micro_lo"], out["q_micro_hi"] = ci_ratio([c for c, _ in ck], [k for _, k in ck], level)
    ex = [r for r in done if r.get("exact_records") is not None]
    if ex:
        out["exact_records"] = sum(r["exact_records"] for r in ex)
        out["records"] = sum(r["n_docs"] for r in ex)
        out["exact_rate"] = out["exact_records"] / out["records"]
    for k in ("repaired", "transport_retry", "provider_refusal"):
        out[k] = sum(1 for r in rows_all if r.get(k) is True)
    costs = [r.get("cost_usd") for r in rows_all if r.get("cost_usd") is not None]
    out["cost_total"] = sum(costs) if costs else None
    out["cost_per_completed"] = (out["cost_total"] / out["completed"]) if costs and out["completed"] else None
    toks = [r.get("output_tokens") for r in rows_all if r.get("output_tokens")]
    out["output_tokens_mean"] = st.fmean(toks) if toks else None
    out["output_tokens_max"] = max(toks) if toks else None
    ins = [r.get("input_tokens") for r in rows_all if r.get("input_tokens")]
    out["input_tokens_mean"] = st.fmean(ins) if ins else None
    return out


def by_unit(rows, key):
    return {r["unit_id"]: r.get(key) for r in rows if r["completion"] == "completed"}


EMB = "Embedding (post-hoc exploratory)"   # D14: in the main tables, always marked; never prespecified
J_ATT = ["Analytic one-bucket", "Memon-inspired", EMB, "One-shot Sonnet"]


def label_of(*attackers):
    return "post-hoc exploratory" if EMB in attackers else "prespecified"
J_COLS = ["condition", "attacker", "attempted", "completed", "rbnc", "F1_J_mean", "F1_J_lo", "F1_J_hi",
          "F1_J_median", "precision_J_mean", "recall_J_mean", "b_J_mean", "A_J_mean", "A_J_lo", "A_J_hi",
          "F1_L_mean", "F1_L_lo", "F1_L_hi", "q_mean", "q_micro", "q_micro_lo", "q_micro_hi", "K0_pools",
          "exact_records", "records", "repaired", "transport_retry", "cost_per_completed", "output_tokens_mean"]


def headline():
    rows, dist = [], []
    for a in J_ATT:
        s = j_summary(sel("J", "headline", a, completed=False))
        rows.append({"condition": "headline (full length)", "attacker": a, **s})
        f1 = sorted(r["F1_J"] for r in sel("J", "headline", a))
        dist.append({"attacker": a, "n": len(f1), **{f"p{p}": float(np.percentile(f1, p))
                                                      for p in (0, 10, 25, 50, 75, 90, 100)}})
    rows.append({"condition": "headline (full length)", "attacker": "Hierarchical (decomposed) Sonnet",
                 "attempted": None, "completed": None, "note": "PENDING -- not run"})
    write_table("table_B_headline_J", rows, J_COLS + ["F1_J_t_lo", "F1_J_t_hi", "cost_total"],
                "Table B — Headline J (46 pools, full-length reference cut)", "tab:headline",
                "Means with 95% percentile-bootstrap CIs over pools (10,000 resamples, seed 42); t-interval "
                "columns are a sensitivity check. q_mean averages defined pools; q_micro = sum C / sum K. "
                "Hierarchical pending.")
    write_table("table_B3_headline_distribution", dist, None, "Headline J: pool-level F1_J distribution")
    S = {a: by_unit(sel("J", "headline", a), "F1_J") for a in J_ATT}
    pairs = []
    for m in ("F1_J", "F1_L", "q", "A_J"):
        for a, b in (("One-shot Sonnet", "Memon-inspired"), ("One-shot Sonnet", "Analytic one-bucket"),
                     ("Memon-inspired", "Analytic one-bucket"), (EMB, "Memon-inspired"),
                     ("One-shot Sonnet", EMB), (EMB, "Analytic one-bucket")):
            if m in ("q", "A_J", "F1_L") and "Analytic" in b:
                continue
            pa = paired(by_unit(sel("J", "headline", a), m), by_unit(sel("J", "headline", b), m))
            pairs.append({"family": "headline", "metric": m, "a": a, "b": b,
                          "analysis_label": label_of(a, b), **pa})
    write_table("table_B2_headline_paired", pairs, None, "Headline J: paired attacker comparisons (pools)",
                note="a - b per pool; percentile bootstrap resamples each pool once with both attackers' "
                     "scores; 95% CIs; t-interval as sensitivity.")
    KEY["headline"] = {r["attacker"]: r for r in rows}
    KEY["headline_pairs"] = pairs
    fig1 = []
    for i, a in enumerate(J_ATT):
        s = KEY["headline"][a]
        fig1.append({"idx": i, "attacker": a, "mean": s["F1_J_mean"], "lo": s["F1_J_lo"], "hi": s["F1_J_hi"],
                     "errlo": s["F1_J_mean"] - s["F1_J_lo"], "errhi": s["F1_J_hi"] - s["F1_J_mean"],
                     "completed": s["completed"], "attempted": s["attempted"]})
    write_fd("fig1_summary", fig1)
    pts = []
    for i, a in enumerate(J_ATT):
        rs = sorted(sel("J", "headline", a), key=lambda r: r["unit_id"])
        for k, r in enumerate(rs):
            pts.append({"idx": i, "x": i + (((k * 0.6180339887) % 1) - 0.5) * 0.36, "F1_J": r["F1_J"],
                        "pool": r["unit_id"]})
    write_fd("fig1_pools", pts)


def grid():
    rows, mech = [], []
    for c in GRID:
        for a in J_ATT:
            rows.append({"condition": LABEL[c], "cell": c, "attacker": a,
                         **j_summary(sel("J", "grid", a, c, completed=False))})
        base = sel("J", "grid", "Analytic one-bucket", c)
        mech.append({"cell": LABEL[c], "pools": len(base),
                     "doc_words_mean": st.fmean(r["doc_words_mean"] for r in base),
                     "frags_per_doc": st.fmean(r["frags_per_doc"] for r in base),
                     "frags_per_pool": st.fmean(r["n_fragments"] for r in base),
                     "frags_per_pool_min": min(r["n_fragments"] for r in base),
                     "frags_per_pool_max": max(r["n_fragments"] for r in base),
                     "frag_words_mean": st.fmean(r["frag_words_mean"] for r in base),
                     "frag_words_median": st.fmean(r["frag_words_median"] for r in base),
                     "frag_words_sd": st.fmean(r["frag_words_sd"] for r in base),
                     "frag_words_min": min(r["frag_words_min"] for r in base),
                     "frag_words_max": max(r["frag_words_max"] for r in base),
                     "frags_per_1000_words": st.fmean(r["frags_per_1000_words"] for r in base)})
    write_table("table_C_grid_J", rows, ["cell"] + J_COLS, "Table C — Grid J, all 9 retained cells (pools 2-25)",
                "tab:grid", "95% percentile-bootstrap CIs over pools. One-shot random / token-window: 23 of 24 "
                "completed (pool_002 RBNC, D6).")
    write_table("table_C2_grid_mechanics", mech, None, "Fragmentation mechanics per grid cell (§13; word counts)",
                note="Averaged over each cell's 24 pools; per-pool values in GRID_J.csv. frags_per_1000_words is "
                     "descriptive, not a causal decomposition.")
    KEY["grid"] = {(r["cell"], r["attacker"]): r for r in rows}
    KEY["mechanics"] = {m["cell"]: m for m in mech}
    # paired comparisons (§7-9), one-shot Sonnet, pools where both completed
    comps = []
    for fam, groups in (("within granularity", WITHIN_GRAN), ("within strategy", WITHIN_STRAT)):
        for gname, cells in groups.items():
            for i in range(len(cells)):
                for j in range(i + 1, len(cells)):
                    for m in ("F1_J", "F1_L", "q", "A_J"):
                        pa = paired(by_unit(sel("J", "grid", "One-shot Sonnet", cells[i]), m),
                                    by_unit(sel("J", "grid", "One-shot Sonnet", cells[j]), m))
                        comps.append({"family": fam, "group": gname, "metric": m, "a": LABEL[cells[i]],
                                      "b": LABEL[cells[j]], **pa})
    write_table("table_C3_grid_paired", comps, None, "Grid J: paired condition comparisons (one-shot Sonnet)",
                note="a - b per pool, over pools where both conditions completed; 95% percentile bootstrap "
                     "carrying both conditions per pool; unadjusted for multiplicity.")
    KEY["grid_pairs"] = comps
    vs = []
    for c in GRID:
        for a, b in (("One-shot Sonnet", "Memon-inspired"), (EMB, "Memon-inspired"), ("One-shot Sonnet", EMB)):
            for m in ("F1_L", "F1_J", "q"):
                vs.append({"cell": LABEL[c], "metric": m, "a": a, "b": b, "analysis_label": label_of(a, b),
                           **paired(by_unit(sel("J", "grid", a, c), m), by_unit(sel("J", "grid", b, c), m))})
    write_table("table_C4_grid_attacker_paired", vs, None, "Grid J: paired attacker comparisons per cell",
                note="a - b per pool over pools both completed; 95% percentile bootstrap carrying both attackers. "
                     "Rows involving the embedding attacker are POST-HOC EXPLORATORY (D14); for it, F1_L is the "
                     "primary comparison.")
    KEY["grid_vs_memon"] = [v for v in vs if v["a"] == "One-shot Sonnet" and v["b"] == "Memon-inspired"]
    KEY["grid_attacker_pairs"] = vs
    f2 = []
    for i, c in enumerate(GRID):
        s, m, e, b = (KEY["grid"][(c, a)] for a in ("One-shot Sonnet", "Memon-inspired", EMB, "Analytic one-bucket"))
        f2.append({"idx": i, "cell": LABEL[c], "granularity": c.split("__")[1],
                   "sonnet": s["F1_J_mean"], "sonnet_errlo": s["F1_J_mean"] - s["F1_J_lo"],
                   "sonnet_errhi": s["F1_J_hi"] - s["F1_J_mean"], "memon": m["F1_J_mean"],
                   "memon_errlo": m["F1_J_mean"] - m["F1_J_lo"], "memon_errhi": m["F1_J_hi"] - m["F1_J_mean"],
                   "emb": e["F1_J_mean"], "emb_errlo": e["F1_J_mean"] - e["F1_J_lo"],
                   "emb_errhi": e["F1_J_hi"] - e["F1_J_mean"],
                   "baseline": b["F1_J_mean"], "sonnet_completed": s["completed"]})
    write_fd("fig2_grid_J", f2)


def decomposition():
    pts = []
    conds = [("headline", "semantic__sentence (full length)")] + [("grid", c) for c in GRID] + \
            [("identifier", "identifier__field")]
    for fam, c in conds:
        for a in ("One-shot Sonnet", "Memon-inspired", EMB):
            rs = sel("J", fam, a, c)
            fl = ci_mean([r["F1_L"] for r in rs])
            qm = ci_ratio([r["C"] for r in rs], [r["K"] for r in rs])
            f1 = st.fmean(r["F1_J"] for r in rs)
            pts.append({"condition": LABEL.get(c, c), "family": fam, "attacker": a,
                        "analysis_label": label_of(a),
                        "series": {"One-shot Sonnet": "sonnet", "Memon-inspired": "memon", EMB: "embedding"}[a],
                        "sid": {"One-shot Sonnet": 0, "Memon-inspired": 1, EMB: 2}[a],
                        "short": {"semantic__sentence (full length)": "headline", "identifier__field": "identifier"}.get(
                            c, c.replace("random", "rnd").replace("semantic", "sem").replace("coherence-sever", "coh")
                            .replace("subject-verb", "sv").replace("__sentence", "-sent").replace("__clause", "-cl")
                            .replace("__token-window", "-tw")),
                        "F1_L": fl[0], "F1_L_errlo": fl[0] - fl[1], "F1_L_errhi": fl[2] - fl[0],
                        "q_micro": qm[0], "q_errlo": qm[0] - qm[1], "q_errhi": qm[2] - qm[0], "F1_J": f1})
    write_fd("fig3_decomposition", pts)
    write_table("table_C5_decomposition", pts, ["condition", "attacker", "F1_L", "q_micro", "F1_J"],
                "Linkage vs ordering decomposition (§14)",
                note="F1_L mean over pools; q_micro = sum C / sum K; F1_J = F1_L x q holds per pool "
                     "(max residual 2.2e-16). Diagnostic.")
    KEY["decomposition"] = pts


O_ATT = ["One-shot Sonnet", "Jaccard-Greedy", "Jaccard-MST", "Random"]


def o_summary(rows):
    out = {"docs": len(rows)}
    out["tau_mean"], out["tau_lo"], out["tau_hi"] = ci_mean([r["tau"] for r in rows])
    out["tau_t_lo"], out["tau_t_hi"] = t_ci([r["tau"] for r in rows])
    out["tau_median"] = float(np.median([r["tau"] for r in rows]))
    out["pairs_correct_mean"] = st.fmean(r["pairs_correct"] for r in rows)
    ex = [r["exact_order"] for r in rows if r.get("exact_order") is not None]
    out["exact_order_rate"] = (sum(ex) / len(ex)) if ex else st.fmean(r["exact_probability"] for r in rows)
    out["mean_abs_disp"] = st.fmean(r["mean_abs_disp"] for r in rows)
    md = [r["median_abs_disp"] for r in rows if r.get("median_abs_disp") is not None]
    out["median_abs_disp"] = st.fmean(md) if md else None
    mx = [r["max_abs_disp"] for r in rows if r.get("max_abs_disp") is not None]
    out["max_abs_disp_mean"] = st.fmean(mx) if mx else None
    rf = [r["run_fraction"] for r in rows if r.get("run_fraction") is not None]
    out["run_fraction_mean"] = st.fmean(rf) if rf else None
    out["frags_per_doc"] = st.fmean(r["n_fragments"] for r in rows)
    out["doc_words"] = st.fmean(r["doc_words_mean"] for r in rows)
    c = [r.get("cost_usd") for r in rows if r.get("cost_usd") is not None]
    out["cost_total"] = sum(c) if c else None
    return out


def game_o():
    rows, conds = [], [("headline", "semantic__sentence (full length)")] + [("grid", c) for c in GRID]
    for fam, c in conds:
        for a in O_ATT:
            rs = sel("O", fam, a, c)
            rows.append({"condition": LABEL.get(c, c), "family": fam, "cell": c, "attacker": a, **o_summary(rs)})
    cols = ["condition", "attacker", "docs", "tau_mean", "tau_lo", "tau_hi", "tau_median", "pairs_correct_mean",
            "exact_order_rate", "mean_abs_disp", "median_abs_disp", "max_abs_disp_mean", "run_fraction_mean",
            "frags_per_doc", "doc_words", "tau_t_lo", "tau_t_hi"]
    write_table("table_D_game_O", rows, cols, "Table D — Game O (membership given, order only)", "tab:gameO",
                "95% percentile-bootstrap CIs over documents. Random is the closed-form expectation for a uniformly "
                "random order (tau 0). Every document completed; no non-completions. O is the membership-oracle "
                "reference, not an upper bound on J.")
    KEY["o"] = {(r["cell"], r["attacker"]): r for r in rows}
    pf = []
    for fam, c in conds:
        for b in ("Jaccard-Greedy", "Jaccard-MST"):
            pa = paired({r["unit_id"]: r["tau"] for r in sel("O", fam, "One-shot Sonnet", c)},
                        {r["unit_id"]: r["tau"] for r in sel("O", fam, b, c)})
            pf.append({"condition": LABEL.get(c, c), "a": "One-shot Sonnet", "b": b, "metric": "tau", **pa})
    write_table("table_D2_O_sonnet_vs_floors", pf, None, "Game O: one-shot Sonnet minus the classical floors (paired)")
    comps = []
    for fam_name, groups in (("within granularity", WITHIN_GRAN), ("within strategy", WITHIN_STRAT)):
        for gname, cells in groups.items():
            for i in range(len(cells)):
                for j in range(i + 1, len(cells)):
                    pa = paired({r["unit_id"]: r["tau"] for r in sel("O", "grid", "One-shot Sonnet", cells[i])},
                                {r["unit_id"]: r["tau"] for r in sel("O", "grid", "One-shot Sonnet", cells[j])})
                    comps.append({"family": fam_name, "group": gname, "metric": "tau", "a": LABEL[cells[i]],
                                  "b": LABEL[cells[j]], **pa})
    write_table("table_D3_O_grid_paired", comps, None, "Game O: paired condition comparisons (same 30 documents)",
                note="a - b per document; 95% percentile bootstrap carrying both; unadjusted for multiplicity.")
    KEY["o_pairs"] = comps
    f4 = []
    for i, (fam, c) in enumerate(conds):
        d = {"idx": i, "condition": LABEL.get(c, c)}
        for a, k in (("One-shot Sonnet", "sonnet"), ("Jaccard-Greedy", "greedy"), ("Jaccard-MST", "mst")):
            s = KEY["o"][(c, a)]
            d.update({k: s["tau_mean"], k + "_errlo": s["tau_mean"] - s["tau_lo"], k + "_errhi": s["tau_hi"] - s["tau_mean"]})
        f4.append(d)
    write_fd("fig4_grid_O", f4)


def identifier():
    atts = ["Random", "Memon-inspired", EMB, "One-shot Sonnet", "Analytic one-bucket", "Schema-order"]
    rows, rule = [], []
    for a in atts:
        rs = sel("J", "identifier", a)
        s = j_summary(sel("J", "identifier", a, completed=False))
        a_sch = [(r["F1_J"] - 0.20) / 0.80 for r in rs]
        raw = [r["F1_J"] - 0.20 for r in rs]
        s["A_schema_mean"], s["A_schema_lo90"], s["A_schema_hi90"] = ci_mean(a_sch, 0.90)
        s["A_schema_t_lo90"], s["A_schema_t_hi90"] = t_ci(a_sch, 0.90)
        s["raw_schema_diff_mean"], s["raw_lo90"], s["raw_hi90"] = ci_mean(raw, 0.90)
        rows.append({"attacker": a, **s})
        if a in ("One-shot Sonnet", "Memon-inspired", "Random", EMB):
            inside = -0.10 <= s["A_schema_lo90"] and s["A_schema_hi90"] <= 0.10
            below = s["A_schema_hi90"] < -0.10
            rule.append({"attacker": a, "A_schema_mean": s["A_schema_mean"], "ci90_lo": s["A_schema_lo90"],
                         "ci90_hi": s["A_schema_hi90"], "raw_diff_mean": s["raw_schema_diff_mean"],
                         "raw_ci90_lo": s["raw_lo90"], "raw_ci90_hi": s["raw_hi90"],
                         "t90_lo": s["A_schema_t_lo90"], "t90_hi": s["A_schema_t_hi90"],
                         "near_schema_baseline": inside,
                         "verdict": ("near the schema-aware baseline (entire 90% CI inside ±0.10)" if inside else
                                     "NOT near: entire 90% CI below -0.10 (below the schema-aware baseline)"
                                     if below else "NOT near: 90% CI not inside ±0.10")})
    cols = ["attacker", "completed", "F1_J_mean", "F1_J_lo", "F1_J_hi", "precision_J_mean", "recall_J_mean",
            "F1_L_mean", "F1_L_lo", "F1_L_hi", "q_mean", "q_micro", "A_J_mean", "A_schema_mean", "A_schema_lo90",
            "A_schema_hi90", "raw_schema_diff_mean", "L_precision_mean", "L_precision_lo", "L_precision_hi"]
    write_table("table_E_identifier_J", rows, cols, "Table E — Identifier J (20 frozen pools of 7 records)",
                "tab:identifier",
                "F1_J CIs 95%; A_schema = (F1_J - 0.20)/0.80 with 90% CI (the frozen rule); raw F1_J - 0.20 alongside. "
                "q is a template diagnostic. Random = D11/D13 random identifier baseline (10,000 draws per pool).")
    write_table("table_E2_identifier_rule", rule, None, "Identifier: frozen near-baseline decision (±0.10, 90% CI)",
                note="Primary criterion: the entire 90% percentile-bootstrap CI on the normalized schema advantage "
                     "inside [-0.10, +0.10]. Nonsignificance is never read as equivalence.")
    KEY["identifier"] = {r["attacker"]: r for r in rows}
    KEY["identifier_rule"] = rule
    # post-hoc membership diagnostic: same-record rate among within-group pairs vs template chance
    diag = []
    for a in ("One-shot Sonnet", "Memon-inspired", EMB, "Random"):
        rs = sel("J", "identifier", a)
        lp = ci_mean([r["L_precision"] for r in rs if r.get("L_precision") is not None])
        reading = ("n/a" if math.isnan(lp[0]) else "above template chance" if lp[1] > 1 / 7 else
                   "below template chance" if lp[2] < 1 / 7 else "consistent with template chance")
        diag.append({"attacker": a, "linkage_precision_mean": lp[0], "lo": lp[1], "hi": lp[2],
                     "template_chance": 1 / 7, "reading": reading})
    write_table("table_E3_identifier_membership", diag, None,
                "Identifier: membership beyond the schema (EXPLORATORY / post hoc)",
                note="Share of an attacker's within-group pairs that truly share a record. If groups respect the "
                     "one-field-per-type template but assign records at random, the expected share is 1/7. 95% CIs "
                     "over pools. Post hoc: defined after the answers were seen.")
    KEY["identifier_membership"] = diag
    f5a = []
    for i, a in enumerate(("Random", "Memon-inspired", EMB, "One-shot Sonnet")):
        s = KEY["identifier"][a]
        f5a.append({"idx": i, "attacker": a, "mean": s["F1_J_mean"], "errlo": s["F1_J_mean"] - s["F1_J_lo"],
                    "errhi": s["F1_J_hi"] - s["F1_J_mean"]})
    write_fd("fig5a_identifier", f5a)
    write_fd("fig5b_identifier_rule", [{"idx": i, "attacker": r["attacker"], "mean": r["A_schema_mean"],
                                        "errlo": r["A_schema_mean"] - r["ci90_lo"],
                                        "errhi": r["ci90_hi"] - r["A_schema_mean"]} for i, r in enumerate(rule)])


def relationships():
    out = []
    jcov = ["doc_words_mean", "doc_words_median", "pool_words_total", "n_fragments", "frags_per_doc",
            "frag_words_mean", "frag_words_median"]
    for fam in ("headline", "grid", "identifier"):
        for a in ("One-shot Sonnet", "Memon-inspired", EMB):
            rs = sel("J", fam, a)
            for x in jcov:
                for y in ("F1_J", "F1_L", "q", "A_J"):
                    cl = [r["unit_id"] for r in rs] if fam == "grid" else None
                    s = spearman([r[x] for r in rs], [r[y] for r in rs], cl)
                    out.append({"game": "J", "family": fam + (" (pooled; pool-clustered)" if fam == "grid" else ""),
                                "attacker": a, "x": x, "y": y, **s})
    for c in GRID:
        rs = sel("J", "grid", "One-shot Sonnet", c)
        for x in ("doc_words_mean", "n_fragments", "frag_words_mean"):
            for y in ("F1_J", "F1_L", "q"):
                out.append({"game": "J", "family": "grid cell " + LABEL[c], "attacker": "One-shot Sonnet",
                            "x": x, "y": y, **spearman([r[x] for r in rs], [r[y] for r in rs])})
    for fam in ("headline", "grid"):
        for a in ("One-shot Sonnet", "Jaccard-Greedy", "Jaccard-MST"):
            rs = sel("O", fam, a)
            for x in ("doc_words_mean", "n_fragments", "frag_words_mean", "frag_words_median"):
                for y in ("tau", "pairs_correct", "exact_order", "mean_abs_disp"):
                    cl = [r["unit_id"] for r in rs] if fam == "grid" else None
                    s = spearman([r[x] for r in rs], [float(r[y]) if r[y] is not None else None for r in rs], cl)
                    out.append({"game": "O", "family": fam + (" (pooled; document-clustered)" if fam == "grid" else ""),
                                "attacker": a, "x": x, "y": y, **s})
    son = [r for r in R if r["attacker"] == "One-shot Sonnet" and r.get("output_tokens")]
    for game in ("J", "O"):
        rs = [r for r in son if r["game"] == game]
        for x in ("n_fragments", "prompt_chars"):
            for y in ("answer_call_output_tokens", "output_tokens", "cost_usd"):
                out.append({"game": game, "family": "resource (all one-shot units)", "attacker": "One-shot Sonnet",
                            "x": x, "y": y, **spearman([r[x] for r in rs], [r[y] for r in rs])})
    write_table("table_R_relationships", out, None,
                "Spearman associations (§10-12, 17-18) with 95% percentile-bootstrap CIs",
                note="Association, not causation. Pooled grid rows resample pool (J) or document (O) IDs carrying all "
                     "their cells. Covariates in words. The specific covariates follow §10-12; they were chosen before "
                     "any association was computed. Unadjusted for multiplicity.")
    KEY["relationships"] = out
    # figure data 6-8, 10
    j = [r for r in sel("J") if r["attacker"] == "One-shot Sonnet" and r["family"] in ("headline", "grid")]
    write_fd("fig6a_length_J", [{"x": r["doc_words_mean"], "y": r["F1_J"],
                                 "cls": "headline" if r["family"] == "headline" else r["granularity"]} for r in j])
    o = [r for r in sel("O") if r["attacker"] == "One-shot Sonnet"]
    write_fd("fig6b_length_O", [{"x": r["doc_words_mean"], "y": r["tau"],
                                 "cls": "headline" if r["family"] == "headline" else r["granularity"]} for r in o])
    write_fd("fig7a_count_J", [{"x": r["n_fragments"], "y": r["F1_J"],
                                "cls": "headline" if r["family"] == "headline" else r["granularity"]} for r in j])
    write_fd("fig7b_count_O", [{"x": r["n_fragments"], "y": r["tau"],
                                "cls": "headline" if r["family"] == "headline" else r["granularity"]} for r in o])
    write_fd("fig8a_size_J", [{"x": r["frag_words_mean"], "y": r["F1_J"],
                               "cls": "headline" if r["family"] == "headline" else r["granularity"]} for r in j])
    write_fd("fig8b_size_O", [{"x": r["frag_words_mean"], "y": r["tau"],
                               "cls": "headline" if r["family"] == "headline" else r["granularity"]} for r in o])
    allj = [r for r in R if r["game"] == "J" and r["attacker"] == "One-shot Sonnet" and r.get("output_tokens")]
    write_fd("fig10_resource", [{"x": r["n_fragments"], "y": r["answer_call_output_tokens"],
                                 "cls": "rbnc" if r["completion"] == "rbnc" else
                                 ("identifier" if r["family"] == "identifier" else r["family"])} for r in allj])


def headline_vs_grid():
    h = sel("J", "headline", "One-shot Sonnet")
    g = sel("J", "grid", "One-shot Sonnet", REF)
    out = []
    for m in ("F1_J", "F1_L", "q", "A_J", "n_fragments", "doc_words_mean", "output_tokens", "cost_usd"):
        hv = np.array([r[m] for r in h if r.get(m) is not None], float)
        gv = np.array([r[m] for r in g if r.get(m) is not None], float)
        rng = np.random.default_rng(SEED)
        bs = np.array([rng.choice(hv, len(hv)).mean() - rng.choice(gv, len(gv)).mean() for _ in range(B)])
        out.append({"metric": m, "headline_mean": hv.mean(), "grid_reference_mean": gv.mean(),
                    "diff": hv.mean() - gv.mean(), "lo": float(np.quantile(bs, 0.025)),
                    "hi": float(np.quantile(bs, 0.975)), "n_headline": len(hv), "n_grid": len(gv)})
    out.append({"metric": "RBNC", "headline_mean": 0, "grid_reference_mean": 0, "diff": 0,
                "n_headline": 46, "n_grid": 24})
    write_table("table_H_headline_vs_grid", out, None,
                "Headline (full length) vs grid reference cell (semantic / sentence), one-shot Sonnet (§15)",
                note="Different pools, so UNPAIRED: each group resampled separately (95% percentile bootstrap). A "
                     "generalization check; headline and grid are never merged.")
    KEY["headline_vs_grid"] = out


def resource():
    import glob
    fam_rows = []
    for (game, fam) in (("J", "headline"), ("J", "grid"), ("J", "identifier"), ("O", "headline"), ("O", "grid")):
        rs = [r for r in R if r["game"] == game and r["family"] == fam and r["attacker"] == "One-shot Sonnet"]
        fam_rows.append({"experiment": f"{fam} {game}", "units_submitted": len(rs),
                         "completed": sum(r["completion"] == "completed" for r in rs),
                         "rbnc": sum(r["completion"] == "rbnc" for r in rs),
                         "provider_refusals_then_resent": sum(bool(r.get("provider_refusal")) for r in rs),
                         "transport_retries": sum(bool(r.get("transport_retry")) for r in rs),
                         "repairs": sum(bool(r.get("repaired")) for r in rs),
                         "input_tokens": sum(r.get("input_tokens") or 0 for r in rs),
                         "output_tokens": sum(r.get("output_tokens") or 0 for r in rs),
                         "cost_usd": sum(r.get("cost_usd") or 0 for r in rs)})
        f = fam_rows[-1]
        f["cost_per_completed"] = f["cost_usd"] / f["completed"] if f["completed"] else None
    tot = {k: sum(f[k] for f in fam_rows) for k in fam_rows[0] if k not in ("experiment", "cost_per_completed")}
    fam_rows.append({"experiment": "TOTAL (final run, one-shot)", **tot,
                     "cost_per_completed": tot["cost_usd"] / tot["completed"]})
    led = json.load(open("results/run_ledger.json", encoding="utf-8"))
    fam_rows.append({"experiment": "ledger: all spend to date (incl. pool 1, samples, G3)",
                     "cost_usd": led["spend"]["observed_usd"]})
    write_table("table_G_resource", fam_rows, None, "Table G — Resource and completion (one-shot Sonnet)",
                "tab:resource", "Tokens and cost summed over every provider result row for each unit (original, "
                "resend, repair), at the batch rate the ledger settles at. Refused-for-credit requests had zero usage.")
    comp = []
    for game, fam, cells in (("J", "headline", ["semantic__sentence (full length)"]), ("J", "grid", GRID),
                             ("J", "identifier", ["identifier__field"]),
                             ("O", "headline", ["semantic__sentence (full length)"]), ("O", "grid", GRID)):
        for c in cells:
            for a in (["One-shot Sonnet", "Memon-inspired"] if game == "J" else ["One-shot Sonnet"]):
                rs = [r for r in R if r["game"] == game and r["family"] == fam and r["cell"] == c and r["attacker"] == a]
                comp.append({"game": game, "condition": LABEL.get(c, c), "attacker": a, "attempted": len(rs),
                             "completed": sum(r["completion"] == "completed" for r in rs),
                             "rbnc": sum(r["completion"] == "rbnc" for r in rs),
                             "completion_rate": sum(r["completion"] == "completed" for r in rs) / len(rs)})
    write_table("table_G2_completion", comp, None, "Completion / RBNC by condition (replaces Figure 9, D13)",
                note="One resource-bounded non-completion in the study: grid random / token-window pool_002, one-shot "
                     "Sonnet (D6). Numerical comparisons use pools where both conditions completed.")
    KEY["resource"] = fam_rows
    rb = [r for r in R if r["completion"] == "rbnc"][0]
    cell_n = sorted(r["n_fragments"] for r in R if r["game"] == "J" and r["cell"] == rb["cell"]
                    and r["attacker"] == "Analytic one-bucket")
    all_n = sorted(r["n_fragments"] for r in R if r["game"] == "J" and r["attacker"] == "Analytic one-bucket")
    KEY["rbnc"] = {"cell": rb["cell"], "pool": rb["unit_id"], "n_fragments": rb["n_fragments"],
                   "output_tokens": rb["output_tokens"], "prompt_chars": None,
                   "rank_in_cell": sum(n <= rb["n_fragments"] for n in cell_n), "cell_pools": len(cell_n),
                   "rank_overall": sum(n <= rb["n_fragments"] for n in all_n), "all_pools": len(all_n),
                   "max_fragments_completed": max(r["n_fragments"] for r in R if r["game"] == "J"
                                                  and r["attacker"] == "One-shot Sonnet"
                                                  and r["completion"] == "completed")}
    batches = []
    for p in sorted(glob.glob("results/batches/final-*.results.jsonl")):
        tag = os.path.basename(p).replace(".results.jsonl", "")
        rows = [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
        batches.append({"batch": tag, "rows": len(rows),
                        "succeeded": sum(r.get("result_type") == "succeeded" for r in rows),
                        "refused_for_credit": sum("credit balance" in str(r.get("error")) for r in rows),
                        "at_128k": sum((r.get("usage") or {}).get("output_tokens", 0) >= 128000 for r in rows),
                        "input_tokens": sum((r.get("usage") or {}).get("input_tokens", 0) or 0 for r in rows),
                        "output_tokens": sum((r.get("usage") or {}).get("output_tokens", 0) or 0 for r in rows),
                        "ledger_actual_usd": (led["steps"].get(tag) or {}).get("actual_usd")})
    write_table("table_G3_batches", batches, None, "Every final-run batch (provider records and ledger)")


def hierarchical():
    fz = json.load(open("results/audit/hier_oracle_ceiling.json", encoding="utf-8"))
    post = json.load(open("results/audit/hier_oracle_ceiling_post_sha256.json", encoding="utf-8"))
    rows = [{"analysis": "A. RBNC rescue (headline)", "status": "PENDING -- no headline one-shot RBNC occurred "
             "(0 of 46), so the frozen rescue set is empty"},
            {"analysis": "B. random filler paired comparison (12 pools)", "status": "PENDING -- not run (D13)"}]
    for name, d in fz["datasets"].items():
        rows.append({"analysis": "DIAGNOSTIC CEILING -- NOT AN ATTACKER RESULT", "dataset": name,
                     "oracle_F1_L_median": d.get("oracle_linkage_f1_median"), "oracle_q_median": d.get("oracle_q_median"),
                     "oracle_F1_J_median": d.get("oracle_joint_f1_median"),
                     "post_fix_oracle_F1_J_median": post["datasets"][name].get("oracle_joint_f1_median"),
                     "status": "frozen D10 diagnostic (development data)"})
    write_table("table_F_hierarchical", rows, None, "Table F — Hierarchical (pending) and the oracle diagnostic",
                note="The oracle replaces Sonnet's pair judgements with the answer key on the pairs the frozen blocker "
                     "exposes; it shows the candidate graph does not impose a low ceiling. It is not an attacker result.")


def error_taxonomy():
    """§19: automated categories over every one-shot J pool; examples by a predefined quantile rule."""
    from joint_game import _as_groups, build_units
    specs = {"headline": ["runs/final_headlineJ.json"],
             "grid": [f"runs/final_gridJ_w{k}.json" for k in (1, 2, 3, 4)],
             "identifier": ["runs/final_identifierJ.json"]}
    rdir = {"headline": "headlineJ", "grid": "gridJ", "identifier": "identifierJ"}
    out = []
    for fam, paths in specs.items():
        for path in paths:
            b = json.load(open(path, encoding="utf-8"))["build"]
            for cell_dir in b["cells"]:
                base = os.path.basename(os.path.normpath(cell_dir))
                rows = {json.loads(l)["unit"]: json.loads(l) for l in
                        open(os.path.join("results", "final", rdir[fam], base, "J.jsonl"), encoding="utf-8") if l.strip()}
                for pid, members in b["pools"]:
                    if pid not in rows:
                        continue
                    _o, units, key, truth = build_units(cell_dir, 0, len(members), SEED, pools=[(pid, members)], o_docs=[])
                    rec = {f["fragment_id"]: f["record_id"] for f in units[0][1]}
                    r = rows[pid]
                    al = r["alias_map"]
                    groups = [[al[x] for x in g if x in al] for g in _as_groups(r["raw_response"])]
                    groups = [g for g in groups if g]
                    placed = {f for g in groups for f in g}
                    groups += [[f] for f in rec if f not in placed]
                    merged = sum(1 for g in groups if sum(1 for v in Counter(rec[f] for f in g).values()
                                                          if v >= 0.2 * len(g)) >= 2)
                    split = 0
                    exact = correct_members_wrong_order = 0
                    adj_swaps = big_disp = total = 0
                    for rid in members:
                        tr = key[rid]
                        share = Counter(next(i for i, g in enumerate(groups) if f in g) for f in tr)
                        split += sum(1 for v in share.values() if v >= 0.2 * len(tr)) >= 2
                        for g in groups:
                            if set(g) == set(tr):
                                if g == tr:
                                    exact += 1
                                else:
                                    correct_members_wrong_order += 1
                        gi = share.most_common(1)[0][0]
                        sub = [f for f in groups[gi] if rec[f] == rid]
                        pos = {f: i for i, f in enumerate([f for f in tr if f in set(sub)])}
                        for i, f in enumerate(sub):
                            d = abs(i - pos[f])
                            adj_swaps += d == 1
                            big_disp += d > 5
                            total += 1
                    f1 = next((x["F1_J"] for x in R if x["game"] == "J" and x["family"] == fam and x["unit_id"] == pid
                               and x["attacker"] == "One-shot Sonnet" and x["cell"].startswith(base.split("__")[0]
                               if fam != "headline" else "semantic") and (fam != "grid" or x["cell"] == base)), None)
                    bj = next((x["b_J"] for x in R if x["game"] == "J" and x["family"] == fam and x["unit_id"] == pid
                               and x["attacker"] == "Analytic one-bucket" and (fam != "grid" or x["cell"] == base)), None)
                    out.append({"family": fam, "cell": base, "pool": pid, "F1_J": f1, "b_J": bj,
                                "records": len(members), "exact_records": exact,
                                "correct_membership_wrong_order": correct_members_wrong_order,
                                "merged_clusters": merged, "split_records": split,
                                "singleton_clusters": sum(1 for g in groups if len(g) == 1),
                                "frac_fragments_off_by_one": adj_swaps / total if total else None,
                                "frac_fragments_displaced_gt5": big_disp / total if total else None,
                                "catastrophic_F1_le_baseline": (f1 is not None and bj is not None and f1 <= bj)})
    write_table("table_I_error_taxonomy", out, None, "Error taxonomy per one-shot J pool (§19, automated)",
                note="merged: a predicted cluster with >= 2 records each >= 20% of it; split: a record with >= 20% of its "
                     "fragments in >= 2 clusters; displacement measured within each record's majority cluster. "
                     "EXPLORATORY / illustrative.")
    ex = []
    for fam in ("headline", "grid", "identifier"):
        rs = sorted([o for o in out if o["family"] == fam and o["F1_J"] is not None], key=lambda o: o["F1_J"])
        for p in (0, 25, 50, 75, 100):
            o = rs[min(len(rs) - 1, max(0, math.ceil(p / 100 * len(rs)) - 1))]
            ex.append({"rule": f"{fam}: nearest-rank {p}th percentile of one-shot F1_J", **o})
    write_table("table_I2_error_examples", ex, None, "Error-taxonomy examples, selected by a predefined quantile rule",
                note="Selected by nearest-rank percentile (0, 25, 50, 75, 100) of one-shot F1_J within each family, "
                     "not by how they look. Illustrative, not inferential.")
    KEY["errors"] = {fam: {k: sum(o[k] for o in out if o["family"] == fam) for k in
                           ("records", "exact_records", "correct_membership_wrong_order", "merged_clusters",
                            "split_records", "singleton_clusters")} for fam in ("headline", "grid", "identifier")}


def design_table():
    rows = [
        {"family": "Headline J", "corpus": "prose (PMC case reports)", "game": "J", "sample": "46 pools",
         "pool_size": "7 documents", "condition": "semantic / sentence, full length (reference cut)",
         "attackers": "Analytic one-bucket; Memon-inspired; One-shot Sonnet; Hierarchical (pending)",
         "primary_metric": "raw F1_J"},
        {"family": "Grid J", "corpus": "prose", "game": "J", "sample": "24 pools (2-25) x 9 cells",
         "pool_size": "7 documents", "condition": "9 retained strategy x granularity cells (D5)",
         "attackers": "Analytic one-bucket; Memon-inspired; One-shot Sonnet", "primary_metric": "raw F1_J"},
        {"family": "Identifier J", "corpus": "synthetic identifier records", "game": "J", "sample": "20 pools",
         "pool_size": "7 records (28 fields)", "condition": "one fragment per field",
         "attackers": "Analytic 0.10; Schema-order 0.20; Random; Memon-inspired; One-shot Sonnet",
         "primary_metric": "F1_J; schema advantage with 90% CI (±0.10 rule)"},
        {"family": "Headline O", "corpus": "prose", "game": "O", "sample": "100 documents (length-stratified)",
         "pool_size": "1 document", "condition": "semantic / sentence, full length",
         "attackers": "Random; Jaccard-Greedy; Jaccard-MST; One-shot Sonnet", "primary_metric": "Kendall tau"},
        {"family": "Grid O", "corpus": "prose", "game": "O", "sample": "30 documents x 9 cells",
         "pool_size": "1 document", "condition": "9 retained cells",
         "attackers": "Random; Jaccard-Greedy; Jaccard-MST; One-shot Sonnet", "primary_metric": "Kendall tau"}]
    write_table("table_A_design", rows, None, "Table A — Corpus and design summary", "tab:design",
                "Pool 1 (screening) is excluded from every primary estimate (§24).")


def main():
    design_table()
    headline()
    grid()
    decomposition()
    game_o()
    identifier()
    relationships()
    headline_vs_grid()
    resource()
    hierarchical()
    error_taxonomy()

    def clean(o):
        if isinstance(o, dict):
            return {str(k if not isinstance(k, tuple) else "|".join(k)): clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [clean(v) for v in o]
        if isinstance(o, float) and math.isnan(o):
            return None
        if isinstance(o, (np.floating, np.integer)):
            return o.item()
        return o
    json.dump(clean(KEY), open(os.path.join(PKG, "KEY_NUMBERS.json"), "w", encoding="utf-8"), indent=1)
    print(f"tables: {len(os.listdir(TAB))} files in TABLES/; figure data: {len(os.listdir(FD))} CSVs; KEY_NUMBERS.json")


if __name__ == "__main__":
    main()
