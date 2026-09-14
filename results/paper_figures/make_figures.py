"""
make_figures.py — publication figures for the fragmentation paper, from the
frozen analysis artifacts only. No result is recomputed with a new method:
every mean and interval comes from results/final_analysis/TABLES/*.csv (D13
bootstrap), results/single_token_edge/analysis/{per_pool.csv,summary.json}
(D16 frozen analysis) and per-unit rows from MASTER_RESULTS.csv. The only
arithmetic done here is (a) the monotone transform (1 + tau) / 2 of a Kendall
tau interval, (b) the linear transform of the identifier F1_J interval into
A_J with the constant b_J = 0.10, and (c) reading per-unit token usage from the
provider result records for the post-hoc token arm.

Each figure writes: figN_<name>.pdf / .svg / .png and figN_<name>.csv (the
exact plotted values; nothing is typed by hand).

    python results/paper_figures/make_figures.py
"""

import json
import os
import sys

import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
from matplotlib.lines import Line2D      # noqa: E402
import numpy as np                       # noqa: E402
import pandas as pd                      # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
OUT = "results/paper_figures"
T = "results/final_analysis/TABLES"
MASTER = pd.read_csv("results/final_analysis/MASTER_RESULTS.csv")
ST = pd.read_csv("results/single_token_edge/analysis/per_pool.csv")
STS = json.load(open("results/single_token_edge/analysis/summary.json", encoding="utf-8"))

# ── house style ──────────────────────────────────────────────────────────────
mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
    "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8,
    "xtick.labelsize": 7.5, "ytick.labelsize": 7.5, "legend.fontsize": 7,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "xtick.major.size": 2.5, "ytick.major.size": 2.5,
    "lines.linewidth": 1.0, "lines.markersize": 4,
    "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    "savefig.dpi": 400, "legend.frameon": False,
    "axes.titlelocation": "left", "axes.titleweight": "bold",
})
# Okabe–Ito, colour-blind safe; markers differ too, so grayscale still separates them.
C = {"sonnet": "#0072B2", "memon": "#E69F00", "embed": "#009E73", "base": "#000000",
     "random": "#7F7F7F", "schema": "#CC79A7", "sentence": "#0072B2", "token": "#D55E00",
     "o": "#56B4E9"}
SINGLE, DOUBLE = 3.4, 7.0
ATT = {"sonnet": "One-shot Sonnet", "memon": "Memon-inspired",
       "embed": "Embedding (post-hoc exploratory)", "base": "Analytic one-bucket"}

CELL_ORDER = ["random / sentence", "random / clause", "random / token-window",
              "semantic / sentence", "semantic / clause",
              "coherence-sever / clause", "coherence-sever / token-window",
              "subject-verb / sentence", "subject-verb / clause"]
HEAD = "headline (full length)"
STRATEGY_OF = {c: c.split(" / ")[0] for c in CELL_ORDER}


def save(fig, name, df):
    for ext in ("pdf", "svg", "png"):
        fig.savefig(f"{OUT}/{name}.{ext}", bbox_inches="tight", pad_inches=0.02)
    df.to_csv(f"{OUT}/{name}.csv", index=False)
    plt.close(fig)
    print(f"  wrote {name}.{{pdf,svg,png,csv}}  ({len(df)} rows)")


def ci_h(ax, y, lo, hi, color, lw=1.0):
    ax.plot([lo, hi], [y, y], color=color, lw=lw, solid_capstyle="butt", zorder=3)


def strategy_bands(ax, rows, ypos):
    """Thin separators between strategy groups on a horizontal dot plot."""
    last = None
    for r, y in zip(rows, ypos):
        s = STRATEGY_OF.get(r, r)
        if last is not None and s != last:
            ax.axhline(y + 0.5, color="#BBBBBB", lw=0.5, zorder=0)
        last = s


def label_pool_points(ax, vals, y, color, jitter=0.12, seed=0, size=6, alpha=0.35):
    rng = np.random.default_rng(seed)
    ax.scatter(vals, y + rng.uniform(-jitter, jitter, len(vals)), s=size, color=color,
               alpha=alpha, linewidths=0, zorder=2)


# ═════════════════════════════════════════════════════════════════════════════
def fig1_headline_attackers():
    tb = pd.read_csv(f"{T}/table_B_headline_J.csv")
    tb = tb[tb.attacker.isin(ATT.values())].set_index("attacker")
    order = [ATT["base"], ATT["memon"], ATT["embed"], ATT["sonnet"]]
    show = {ATT["base"]: "Analytic one-bucket\nbaseline", ATT["memon"]: "Memon-inspired",
            ATT["embed"]: "Embedding\n(post-hoc exploratory)", ATT["sonnet"]: "One-shot Sonnet"}
    style = {ATT["base"]: ("base", "x", False), ATT["memon"]: ("memon", "s", True),
             ATT["embed"]: ("embed", "D", False), ATT["sonnet"]: ("sonnet", "o", True)}
    pools = MASTER[(MASTER.family == "headline") & (MASTER.game == "J")]

    fig, axes = plt.subplots(1, 2, figsize=(DOUBLE, 2.1), sharey=True)
    rows = []
    for ax, metric, col, title in ((axes[0], "F1_L", "F1_L", "(a) Linkage component, $F1_L$"),
                                   (axes[1], "F1_J", "F1_J", "(b) Joint reconstruction, $F1_J$")):
        for i, a in enumerate(order):
            ck, mk, filled = style[a]
            m, lo, hi = tb.loc[a, f"{col}_mean"], tb.loc[a, f"{col}_lo"], tb.loc[a, f"{col}_hi"]
            pv = pools[pools.attacker == a][metric].dropna().values
            label_pool_points(ax, pv, i, C[ck], seed=i)
            ci_h(ax, i, lo, hi, C[ck], lw=1.2)
            ax.plot(m, i, marker=mk, color=C[ck], ms=5.5, mfc=C[ck] if filled else "white",
                    mew=1.0, zorder=4, ls="none")
            ax.annotate(f"{m:.3f}", (hi, i), xytext=(4, 0), textcoords="offset points",
                        va="center", ha="left", fontsize=7, color="#333333")
            rows.append({"panel": metric, "attacker": a, "mean": m, "ci95_lo": lo, "ci95_hi": hi,
                         "n_pools": int(tb.loc[a, "completed"]), "n_pool_points": len(pv)})
        ax.set_xlim(0, 1.0)
        ax.set_xticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
        ax.set_title(title)
        ax.set_xlabel({"F1_L": "$F1_L$ (46 headline pools)", "F1_J": "$F1_J$ (46 headline pools)"}[metric])
    axes[0].set_yticks(range(len(order)))
    axes[0].set_yticklabels([show[a] for a in order])
    axes[0].set_ylim(-0.6, len(order) - 0.4)
    save(fig, "fig1_headline_attackers", pd.DataFrame(rows))


# ═════════════════════════════════════════════════════════════════════════════
def _grid_rows_with_headline():
    tc = pd.read_csv(f"{T}/table_C_grid_J.csv")
    tb = pd.read_csv(f"{T}/table_B_headline_J.csv")
    tb = tb[tb.attacker.isin(ATT.values())].copy()
    tb["condition"] = HEAD
    cols = [c for c in tc.columns if c in tb.columns]
    return pd.concat([tb[cols], tc[cols]], ignore_index=True)


def fig2_grid():
    d = _grid_rows_with_headline()
    conds = [HEAD] + CELL_ORDER
    ypos = list(range(len(conds)))[::-1]
    fig, axes = plt.subplots(1, 2, figsize=(DOUBLE, 3.4), sharey=True,
                             gridspec_kw={"width_ratios": [1.35, 1]})
    rows = []
    ax = axes[0]
    for cnd, y in zip(conds, ypos):
        g = d[d.condition == cnd].set_index("attacker")
        s = g.loc[ATT["sonnet"]]
        ci_h(ax, y, s.F1_J_lo, s.F1_J_hi, C["sonnet"], lw=1.3)
        ax.plot(s.F1_J_mean, y, "o", color=C["sonnet"], ms=5, zorder=4)
        ax.plot(g.loc[ATT["memon"]].F1_J_mean, y, "s", color=C["memon"], ms=3.5, zorder=3)
        ax.plot(g.loc[ATT["embed"]].F1_J_mean, y, "D", color=C["embed"], mfc="white", ms=3.5, mew=0.9, zorder=3)
        ax.plot(g.loc[ATT["base"]].F1_J_mean, y, "x", color=C["base"], ms=4.5, mew=0.9, zorder=3)
        ax.annotate(f"{s.F1_J_mean:.3f}", (s.F1_J_hi, y), xytext=(3, 0), textcoords="offset points",
                    va="center", fontsize=6.5, color="#333333")
        rows.append({"condition": cnd, "n_pools_completed": int(s.completed), "rbnc": int(s.rbnc),
                     "sonnet_F1_J": s.F1_J_mean, "sonnet_F1_J_lo": s.F1_J_lo, "sonnet_F1_J_hi": s.F1_J_hi,
                     "memon_F1_J": g.loc[ATT["memon"]].F1_J_mean, "embedding_F1_J": g.loc[ATT["embed"]].F1_J_mean,
                     "analytic_b_J": g.loc[ATT["base"]].F1_J_mean,
                     "sonnet_A_J": s.A_J_mean, "sonnet_A_J_lo": s.A_J_lo, "sonnet_A_J_hi": s.A_J_hi})
    ax.set_xlim(0, 1); ax.set_xlabel("$F1_J$ (joint ordered-pair F1)")
    ax.set_title("(a) Joint reconstruction by condition")
    ax.axhline(ypos[0] - 0.5, color="#888888", lw=0.6, ls=(0, (3, 2)), zorder=0)
    strategy_bands(ax, conds[1:], ypos[1:])
    ax.set_yticks(ypos); ax.set_yticklabels(conds)
    ax.set_ylim(-0.6, len(conds) - 0.4)
    fig.legend(handles=[Line2D([], [], marker="o", color=C["sonnet"], ls="none", label="One-shot Sonnet (95% CI)"),
                        Line2D([], [], marker="s", color=C["memon"], ls="none", ms=3.5, label="Memon-inspired"),
                        Line2D([], [], marker="D", color=C["embed"], mfc="white", ls="none", ms=3.5,
                               label="Embedding (post-hoc exploratory)"),
                        Line2D([], [], marker="x", color=C["base"], ls="none", ms=4.5, label="Analytic one-bucket baseline $b_J$")],
               loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.09), handletextpad=0.4, columnspacing=1.2)
    ax = axes[1]
    for cnd, y in zip(conds, ypos):
        r = [x for x in rows if x["condition"] == cnd][0]
        ci_h(ax, y, r["sonnet_A_J_lo"], r["sonnet_A_J_hi"], C["sonnet"], lw=1.3)
        ax.plot(r["sonnet_A_J"], y, "o", color=C["sonnet"], ms=5, zorder=4)
    ax.axvline(0, color="#000000", lw=0.6, zorder=0)
    ax.set_xlim(0, 1); ax.set_xlabel("$A_J$ = ($F1_J$ − $b_J$) / (1 − $b_J$)")
    ax.set_title("(b) Normalized advantage, One-shot Sonnet")
    ax.axhline(ypos[0] - 0.5, color="#888888", lw=0.6, ls=(0, (3, 2)), zorder=0)
    strategy_bands(ax, conds[1:], ypos[1:])
    save(fig, "fig2_grid_reconstruction", pd.DataFrame(rows))


# ═════════════════════════════════════════════════════════════════════════════
def fig3_decomposition():
    d = _grid_rows_with_headline()
    conds = [HEAD] + CELL_ORDER
    ypos = list(range(len(conds)))[::-1]
    fig, axes = plt.subplots(1, 2, figsize=(DOUBLE, 3.4), sharey=True)
    rows = []
    for cnd, y in zip(conds, ypos):
        g = d[d.condition == cnd].set_index("attacker")
        s = g.loc[ATT["sonnet"]]
        ax = axes[0]
        ci_h(ax, y, s.F1_L_lo, s.F1_L_hi, C["sonnet"], lw=1.3)
        ax.plot(s.F1_L_mean, y, "o", color=C["sonnet"], ms=5, zorder=4)
        ax.plot(g.loc[ATT["memon"]].F1_L_mean, y, "s", color=C["memon"], ms=3.5, zorder=3)
        ax.plot(g.loc[ATT["embed"]].F1_L_mean, y, "D", color=C["embed"], mfc="white", ms=3.5, mew=0.9, zorder=3)
        ax.plot(g.loc[ATT["base"]].F1_L_mean, y, "x", color=C["base"], ms=4.5, mew=0.9, zorder=3)
        ax = axes[1]
        ci_h(ax, y, s.q_micro_lo, s.q_micro_hi, C["sonnet"], lw=1.3)
        ax.plot(s.q_micro, y, "o", color=C["sonnet"], ms=5, zorder=4)
        ax.plot(g.loc[ATT["memon"]].q_micro, y, "s", color=C["memon"], ms=3.5, zorder=3)
        ax.plot(g.loc[ATT["embed"]].q_micro, y, "D", color=C["embed"], mfc="white", ms=3.5, mew=0.9, zorder=3)
        rows.append({"condition": cnd,
                     "sonnet_F1_L": s.F1_L_mean, "sonnet_F1_L_lo": s.F1_L_lo, "sonnet_F1_L_hi": s.F1_L_hi,
                     "memon_F1_L": g.loc[ATT["memon"]].F1_L_mean, "embedding_F1_L": g.loc[ATT["embed"]].F1_L_mean,
                     "analytic_b_L": g.loc[ATT["base"]].F1_L_mean,
                     "sonnet_q_micro": s.q_micro, "sonnet_q_lo": s.q_micro_lo, "sonnet_q_hi": s.q_micro_hi,
                     "memon_q_micro": g.loc[ATT["memon"]].q_micro, "embedding_q_micro": g.loc[ATT["embed"]].q_micro})
    axes[0].set_xlim(0, 1); axes[0].set_xlabel("$F1_L$ (source linkage, direction ignored)")
    axes[0].set_title("(a) Linkage component")
    axes[1].set_xlim(0, 1); axes[1].set_xlabel("$q$ = share of correctly linked pairs in the right direction")
    axes[1].set_title("(b) Ordering component (given the attacker's own links)")
    axes[1].axvline(0.5, color="#888888", lw=0.6, ls=":", zorder=0)
    axes[1].annotate("chance (0.5)", (0.5, ypos[0] + 0.55), fontsize=6.5, color="#666666", ha="center", va="bottom")
    for ax in axes:
        ax.axhline(ypos[0] - 0.5, color="#888888", lw=0.6, ls=(0, (3, 2)), zorder=0)
        strategy_bands(ax, conds[1:], ypos[1:])
    axes[0].set_yticks(ypos); axes[0].set_yticklabels(conds); axes[0].set_ylim(-0.6, len(conds) - 0.4)
    fig.legend(handles=[Line2D([], [], marker="o", color=C["sonnet"], ls="none", label="One-shot Sonnet (95% CI)"),
                        Line2D([], [], marker="s", color=C["memon"], ls="none", ms=3.5, label="Memon-inspired"),
                        Line2D([], [], marker="D", color=C["embed"], mfc="white", ls="none", ms=3.5,
                               label="Embedding (post-hoc exploratory)"),
                        Line2D([], [], marker="x", color=C["base"], ls="none", ms=4.5, label="Analytic one-bucket baseline")],
               loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.09), handletextpad=0.4, columnspacing=1.2)
    save(fig, "fig3_linkage_vs_ordering", pd.DataFrame(rows))


# ═════════════════════════════════════════════════════════════════════════════
def fig4_O_vs_J():
    td = pd.read_csv(f"{T}/table_D_game_O.csv")
    td = td[td.attacker == ATT["sonnet"]].set_index("condition")
    d = _grid_rows_with_headline()
    d = d[d.attacker == ATT["sonnet"]].set_index("condition")
    conds = [HEAD] + CELL_ORDER
    ypos = list(range(len(conds)))[::-1]
    fig, ax = plt.subplots(figsize=(DOUBLE, 3.3))
    rows = []
    dy = 0.22
    for cnd, y in zip(conds, ypos):
        o, j = td.loc[cnd], d.loc[cnd]
        oc, olo, ohi = (1 + o.tau_mean) / 2, (1 + o.tau_lo) / 2, (1 + o.tau_hi) / 2
        ci_h(ax, y + dy, olo, ohi, C["o"], lw=1.3)
        ax.plot(oc, y + dy, "^", color=C["o"], ms=5, zorder=4)
        ci_h(ax, y, j.q_micro_lo, j.q_micro_hi, "#7F7F7F", lw=1.0)
        ax.plot(j.q_micro, y, "v", color="#7F7F7F", ms=4.5, zorder=4)
        ci_h(ax, y - dy, j.F1_J_lo, j.F1_J_hi, C["sonnet"], lw=1.3)
        ax.plot(j.F1_J_mean, y - dy, "o", color=C["sonnet"], ms=5, zorder=4)
        rows.append({"condition": cnd, "O_n_docs": int(o.docs), "O_tau": o.tau_mean, "O_tau_lo": o.tau_lo,
                     "O_tau_hi": o.tau_hi, "O_concordance": oc, "O_concordance_lo": olo, "O_concordance_hi": ohi,
                     "J_n_pools": int(j.completed), "J_F1_J": j.F1_J_mean, "J_F1_J_lo": j.F1_J_lo, "J_F1_J_hi": j.F1_J_hi,
                     "J_q_micro": j.q_micro, "J_q_lo": j.q_micro_lo, "J_q_hi": j.q_micro_hi})
    ax.set_xlim(0, 1)
    ax.set_xlabel("score (0–1); the three coincide when membership is perfect")
    ax.set_yticks(ypos); ax.set_yticklabels(conds); ax.set_ylim(-0.7, len(conds) - 0.3)
    ax.axhline(ypos[0] - 0.5, color="#888888", lw=0.6, ls=(0, (3, 2)), zorder=0)
    strategy_bands(ax, conds[1:], ypos[1:])
    ax.axvline(0.5, color="#888888", lw=0.6, ls=":", zorder=0)
    ax.legend(handles=[Line2D([], [], marker="^", color=C["o"], ls="none", label="Game O: (1 + τ)/2, membership given (documents)"),
                       Line2D([], [], marker="v", color="#7F7F7F", ls="none", ms=4.5, label="Game J: q, direction accuracy on the attacker's own links (pools)"),
                       Line2D([], [], marker="o", color=C["sonnet"], ls="none", label="Game J: $F1_J$, joint membership + order (pools)")],
              loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=1, handletextpad=0.4, borderaxespad=0.2)
    ax.set_title("Ordering with membership given (O) versus joint reconstruction (J), One-shot Sonnet")
    save(fig, "fig4_gameO_vs_gameJ", pd.DataFrame(rows))


# ═════════════════════════════════════════════════════════════════════════════
def fig5_identifiers():
    te = pd.read_csv(f"{T}/table_E_identifier_J.csv").set_index("attacker")
    tb = pd.read_csv(f"{T}/table_B_headline_J.csv").set_index("attacker")
    order = ["Random", ATT["memon"], ATT["embed"], ATT["sonnet"]]
    show = {"Random": "Random partition", ATT["memon"]: "Memon-inspired",
            ATT["embed"]: "Embedding\n(post-hoc exploratory)", ATT["sonnet"]: "One-shot Sonnet"}
    style = {"Random": ("random", "v", True), ATT["memon"]: ("memon", "s", True),
             ATT["embed"]: ("embed", "D", False), ATT["sonnet"]: ("sonnet", "o", True)}
    fig, axes = plt.subplots(1, 3, figsize=(DOUBLE, 2.2), sharey=True, gridspec_kw={"width_ratios": [1, 1, 1]})
    rows = []
    panels = [("F1_L", "F1_L_mean", "F1_L_lo", "F1_L_hi", "(a) Linkage, $F1_L$"),
              ("F1_J", "F1_J_mean", "F1_J_lo", "F1_J_hi", "(b) Joint, $F1_J$"),
              ("L_precision", "L_precision_mean", "L_precision_lo", "L_precision_hi", "(c) Linkage precision")]
    for ax, (key, mc, lc, hc, title) in zip(axes, panels):
        for i, a in enumerate(order):
            ck, mk, filled = style[a]
            m, lo, hi = te.loc[a, mc], te.loc[a, lc], te.loc[a, hc]
            ci_h(ax, i, lo, hi, C[ck], lw=1.2)
            ax.plot(m, i, marker=mk, color=C[ck], ms=5, mfc=C[ck] if filled else "white", mew=1.0, ls="none", zorder=4)
            rows.append({"panel": key, "attacker": a, "mean": m, "ci95_lo": lo, "ci95_hi": hi, "n_pools": 20})
        ax.set_xlim(0, 1); ax.set_title(title)
    # reference lines, named in a small legend per panel (no overlapping annotations)
    h0 = axes[0].axvline(0.20, color=C["base"], lw=0.7, ls="--", zorder=0, label="analytic one-bucket baseline (0.20)")
    axes[0].legend(handles=[h0], loc="lower right", fontsize=6.2, handlelength=1.6)
    h1 = axes[1].axvline(0.10, color=C["base"], lw=0.7, ls="--", zorder=0, label="analytic baseline (0.10)")
    h2 = axes[1].axvline(0.20, color=C["schema"], lw=0.9, ls="-", zorder=0, label="schema-order baseline (0.20)")
    axes[1].legend(handles=[h1, h2], loc="lower right", fontsize=6.2, handlelength=1.6)
    h3 = axes[2].axvline(1 / 7, color=C["base"], lw=0.7, ls="--", zorder=0, label="template-respecting chance (1/7)")
    axes[2].legend(handles=[h3], loc="lower right", fontsize=6.2, handlelength=1.6)
    # prose reference (same attacker, headline prose) so the contrast is visible on a 0–1 axis
    for ax, col in ((axes[0], "F1_L_mean"), (axes[1], "F1_J_mean")):
        v = tb.loc[ATT["sonnet"], col]
        ax.plot(v, 3, marker="o", mfc="white", color=C["sonnet"], ms=5, mew=1.0, ls="none", zorder=3)
        ax.annotate("prose\nheadline", (v, 3), xytext=(0, 6), textcoords="offset points", ha="center", va="bottom",
                    fontsize=6.2, color=C["sonnet"])
        rows.append({"panel": col.replace("_mean", ""), "attacker": "One-shot Sonnet, prose headline (reference)",
                     "mean": v, "ci95_lo": tb.loc[ATT["sonnet"], col.replace("mean", "lo")],
                     "ci95_hi": tb.loc[ATT["sonnet"], col.replace("mean", "hi")], "n_pools": 46})
    axes[0].set_yticks(range(len(order))); axes[0].set_yticklabels([show[a] for a in order])
    for ax in axes: ax.set_ylim(-1.0, len(order) - 0.2)
    axes[0].set_xlabel("$F1_L$"); axes[1].set_xlabel("$F1_J$"); axes[2].set_xlabel("linkage precision")
    save(fig, "fig5_identifiers", pd.DataFrame(rows))


# ═════════════════════════════════════════════════════════════════════════════
def fig6_single_token():
    s = ST[ST.attacker == "One-shot Sonnet"].copy()
    piv = s.pivot(index="pool", columns="condition", values=["A_VJ", "V_J", "null_oracle_V_J", "A_VL", "V_L", "null_oracle_V_L"])
    pools = list(piv.index)
    P = STS["attackers"]["One-shot Sonnet"]["paired_sentence_minus_token"]["A_VJ"]
    means = STS["attackers"]["One-shot Sonnet"]["means"]
    fig, axes = plt.subplots(2, 2, figsize=(DOUBLE, 5.0))
    rows = []
    for p in pools:
        rows.append({"pool": p, **{f"{m}_{c}": piv.loc[p, (m, c)] for m in ("A_VJ", "V_J", "null_oracle_V_J", "A_VL", "V_L", "null_oracle_V_L")
                                   for c in ("sentence", "token")},
                     "A_VJ_diff_sentence_minus_token": piv.loc[p, ("A_VJ", "sentence")] - piv.loc[p, ("A_VJ", "token")]})
    rd = pd.DataFrame(rows)

    # (a) paired A_VJ
    ax = axes[0, 0]
    for _, r in rd.iterrows():
        ax.plot([0, 1], [r.A_VJ_sentence, r.A_VJ_token], color="#9DA5B4", lw=0.7, zorder=1)
        ax.plot(0, r.A_VJ_sentence, "o", color=C["sentence"], ms=3, zorder=2)
        ax.plot(1, r.A_VJ_token, "o", color=C["token"], ms=3, zorder=2)
    ax.plot([0, 1], [means["sentence"]["A_VJ"], means["token"]["A_VJ"]], color="black", lw=1.6, zorder=3)
    ax.plot(0, means["sentence"]["A_VJ"], "D", color="black", ms=5, zorder=4)
    ax.plot(1, means["token"]["A_VJ"], "D", color="black", ms=5, zorder=4)
    ax.annotate(f"mean {means['sentence']['A_VJ']:.3f}", (0, means["sentence"]["A_VJ"]), xytext=(-6, 0),
                textcoords="offset points", ha="right", va="center", fontsize=7)
    ax.annotate(f"mean {means['token']['A_VJ']:.3f}", (1, means["token"]["A_VJ"]), xytext=(6, 0),
                textcoords="offset points", ha="left", va="center", fontsize=7)
    ax.axhline(0, color="#888888", lw=0.6, ls=":", zorder=0)
    ax.annotate("0 = oracle-size random-shuffle null", (0.5, 0), xytext=(0, -7), textcoords="offset points",
                ha="center", va="top", fontsize=6.5, color="#666666")
    ax.set_xticks([0, 1]); ax.set_xticklabels(["sentence cut\n(28 / pool)", "single-token cut\n(438–669 / pool)"])
    ax.set_xlim(-0.75, 1.75); ax.set_ylim(-0.2, 1.0)
    ax.set_ylabel("$A_{VJ}$ (null-adjusted joint)")
    ax.set_title("(a) Same 20 pools, same text, two cuts")

    # (b) paired difference
    ax = axes[0, 1]
    rng = np.random.default_rng(1)
    ax.scatter(rd.A_VJ_diff_sentence_minus_token, rng.uniform(-0.18, 0.18, len(rd)), s=14, color="#4C4C4C", zorder=2)
    ax.plot([P["ci95"][0], P["ci95"][1]], [0.55, 0.55], color="black", lw=1.6, zorder=3)
    ax.plot(P["mean_diff"], 0.55, "D", color="black", ms=6, zorder=4)
    ax.annotate(f"mean {P['mean_diff']:.3f}  [{P['ci95'][0]:.3f}, {P['ci95'][1]:.3f}]", (P["mean_diff"], 0.55),
                xytext=(0, 8), textcoords="offset points", ha="center", va="bottom", fontsize=7)
    ax.axvline(0, color="#888888", lw=0.6, ls=":", zorder=0)
    ax.set_xlim(-0.1, 1.0); ax.set_ylim(-0.5, 1.15)
    ax.set_yticks([0, 0.55]); ax.set_yticklabels(["per pool", "mean,\n95% CI"])
    ax.set_xlabel("$A_{VJ}$(sentence) − $A_{VJ}$(single token)")
    ax.set_title("(b) Paired difference, sentence − single token")
    ax.annotate(f"{P['n_positive']}/{P['n_effective']} pools positive; exact sign test p = {P['sign_test_p_two_sided']:.1e}",
                (0.02, 0.96), xycoords="axes fraction", ha="left", va="top", fontsize=7)

    # (c) raw V_J vs oracle-size null
    ax = axes[1, 0]
    x = {"sentence": (0, 1), "token": (2.2, 3.2)}
    for cnd, (xo, xn) in x.items():
        for _, r in rd.iterrows():
            ax.plot([xo, xn], [r[f"V_J_{cnd}"], r[f"null_oracle_V_J_{cnd}"]], color="#9DA5B4", lw=0.6, zorder=1)
            ax.plot(xo, r[f"V_J_{cnd}"], "o", color=C[cnd], ms=3, zorder=2)
            ax.plot(xn, r[f"null_oracle_V_J_{cnd}"], "o", mfc="white", color=C[cnd], ms=3, mew=0.8, zorder=2)
        mo, mn = rd[f"V_J_{cnd}"].mean(), rd[f"null_oracle_V_J_{cnd}"].mean()
        ax.plot([xo, xn], [mo, mn], color="black", lw=1.6, zorder=3)
        ax.plot(xo, mo, "D", color="black", ms=5, zorder=4); ax.plot(xn, mn, "D", color="black", mfc="white", ms=5, zorder=4)
        ax.annotate(f"{mo:.3f}", (xo, mo), xytext=(-5, 0), textcoords="offset points", ha="right", va="center", fontsize=7)
        ax.annotate(f"{mn:.3f}", (xn, mn), xytext=(5, 0), textcoords="offset points", ha="left", va="center", fontsize=7)
    ax.set_xticks([0, 1, 2.2, 3.2]); ax.set_xticklabels(["observed", "null", "observed", "null"])
    ax.text(0.5, -0.24, "sentence", transform=ax.get_xaxis_transform(), ha="center", fontsize=7.5, color=C["sentence"])
    ax.text(2.7, -0.24, "single token", transform=ax.get_xaxis_transform(), ha="center", fontsize=7.5, color=C["token"])
    ax.set_xlim(-0.6, 3.8); ax.set_ylim(0, 1)
    ax.set_ylabel("raw $V_J$")
    ax.set_title("(c) Raw $V_J$ vs oracle-size null")

    # (d) A_VL paired
    ax = axes[1, 1]
    for _, r in rd.iterrows():
        ax.plot([0, 1], [r.A_VL_sentence, r.A_VL_token], color="#9DA5B4", lw=0.7, zorder=1)
        ax.plot(0, r.A_VL_sentence, "o", color=C["sentence"], ms=3, zorder=2)
        ax.plot(1, r.A_VL_token, "o", color=C["token"], ms=3, zorder=2)
    ax.plot([0, 1], [means["sentence"]["A_VL"], means["token"]["A_VL"]], color="black", lw=1.6, zorder=3)
    ax.plot(0, means["sentence"]["A_VL"], "D", color="black", ms=5, zorder=4)
    ax.plot(1, means["token"]["A_VL"], "D", color="black", ms=5, zorder=4)
    ax.annotate(f"mean {means['sentence']['A_VL']:.3f}", (0, means["sentence"]["A_VL"]), xytext=(-6, 0),
                textcoords="offset points", ha="right", va="center", fontsize=7)
    ax.annotate(f"mean {means['token']['A_VL']:.3f}", (1, means["token"]["A_VL"]), xytext=(6, 0),
                textcoords="offset points", ha="left", va="center", fontsize=7)
    ax.axhline(0, color="#888888", lw=0.6, ls=":", zorder=0)
    ax.set_xticks([0, 1]); ax.set_xticklabels(["sentence", "single token"])
    ax.set_xlim(-0.75, 1.75); ax.set_ylim(-0.5, 1.05)
    ax.set_ylabel("$A_{VL}$ (null-adjusted linkage)")
    ax.set_title("(d) Linkage alone ($A_{VL}$)")
    fig.subplots_adjust(hspace=0.5, wspace=0.32)
    for ext in ("pdf", "svg", "png"):
        fig.savefig(f"{OUT}/fig6_single_token_edge.{ext}", bbox_inches="tight", pad_inches=0.02)
    rd["mean_diff_A_VJ"] = P["mean_diff"]; rd["ci95_lo_diff_A_VJ"] = P["ci95"][0]; rd["ci95_hi_diff_A_VJ"] = P["ci95"][1]
    rd["sign_test_p"] = P["sign_test_p_two_sided"]; rd["n_positive"] = P["n_positive"]
    rd.to_csv(f"{OUT}/fig6_single_token_edge.csv", index=False)
    plt.close(fig)
    print("  wrote fig6_single_token_edge.{pdf,svg,png,csv}")


# ═════════════════════════════════════════════════════════════════════════════
def fig7_landscape():
    d = _grid_rows_with_headline()
    d = d[d.attacker == ATT["sonnet"]].set_index("condition")
    te = pd.read_csv(f"{T}/table_E_identifier_J.csv").set_index("attacker").loc[ATT["sonnet"]]
    units = MASTER[(MASTER.attacker == ATT["sonnet"]) & (MASTER.game == "J") & (MASTER.completion == "completed")]
    st = ST[ST.attacker == "One-shot Sonnet"]
    short = {"random / sentence": "R·s", "random / clause": "R·c", "random / token-window": "R·t",
             "semantic / sentence": "S·s", "semantic / clause": "S·c",
             "coherence-sever / clause": "C·c", "coherence-sever / token-window": "C·t",
             "subject-verb / sentence": "V·s", "subject-verb / clause": "V·c"}
    items = []
    x = 0
    for c in CELL_ORDER:
        r = d.loc[c]; cell = c.replace(" / ", "__")
        pts = units[(units.family == "grid") & (units.cell == cell)].A_J.values
        items.append(dict(x=x, label=short[c], full=c, group="prose grid (prespecified)", mean=r.A_J_mean, lo=r.A_J_lo, hi=r.A_J_hi,
                          pts=pts, posthoc=False, marker="o")); x += 1
    x += 0.8
    r = d.loc[HEAD]
    items.append(dict(x=x, label="headline", full="headline, full length", group="prose headline (prespecified)",
                      mean=r.A_J_mean, lo=r.A_J_lo, hi=r.A_J_hi,
                      pts=units[units.family == "headline"].A_J.values, posthoc=False, marker="s")); x += 1.8
    # identifiers: b_J = 0.10 for every pool (28 fragments, 7 × 4), so A_J = (F1_J − 0.10)/0.90 is exact per pool
    items.append(dict(x=x, label="identifiers", full="synthetic identifiers", group="identifiers (prespecified)",
                      mean=(te.F1_J_mean - 0.10) / 0.90, lo=(te.F1_J_lo - 0.10) / 0.90, hi=(te.F1_J_hi - 0.10) / 0.90,
                      pts=units[units.family == "identifier"].A_J.values, posthoc=False, marker="D")); x += 1.8
    for cnd, lab in (("sentence", "excerpt\nsentence"), ("token", "excerpt\ntoken")):
        g = st[st.condition == cnd]
        items.append(dict(x=x, label=lab, full=f"four-sentence excerpt, {cnd} cut", group="excerpt edge case (post hoc)",
                          mean=g.A_J.mean(), lo=np.nan, hi=np.nan, pts=g.A_J.values, posthoc=True, marker="o")); x += 1.4
    fig, ax = plt.subplots(figsize=(DOUBLE, 2.7))
    rows = []
    for it in items:
        rng = np.random.default_rng(int(it["x"] * 10))
        ax.scatter(it["x"] + rng.uniform(-0.16, 0.16, len(it["pts"])), it["pts"], s=5, color="#7F7F7F", alpha=0.3, linewidths=0, zorder=2)
        col = C["sonnet"]
        if not np.isnan(it["lo"]):
            ax.plot([it["x"], it["x"]], [it["lo"], it["hi"]], color=col, lw=1.2, zorder=3)
        ax.plot(it["x"], it["mean"], marker=it["marker"], color=col, mfc="white" if it["posthoc"] else col,
                ms=5.5, mew=1.1, ls="none", zorder=4)
        rows.append({"x": it["x"], "label": it["full"], "group": it["group"], "sonnet_A_J_mean": it["mean"],
                     "ci95_lo": it["lo"], "ci95_hi": it["hi"], "n_units": len(it["pts"]), "post_hoc": it["posthoc"]})
    # swap the per-point colour for the two post-hoc arms
    ax.axhline(0, color="black", lw=0.6, zorder=0)
    ax.set_xticks([it["x"] for it in items]); ax.set_xticklabels([it["label"] for it in items], fontsize=7)
    ax.set_ylim(-0.25, 1.0); ax.set_ylabel("$A_J$, One-shot Sonnet")
    for gx, name in ((4, "prose grid, 9 cells\n(24 pools each)"), (9.8, "headline\n(46 pools)"), (11.6, "identifiers\n(20 pools)"),
                     (14.1, "4-sentence excerpts,\n20 pools (POST HOC)")):
        ax.text(gx, 1.0, name, ha="center", va="bottom", fontsize=6.8, color="#333333")
    for sx in (9.0, 10.7, 12.5):
        ax.axvline(sx, color="#BBBBBB", lw=0.5, zorder=0)
    ax.set_xlim(-0.7, 15.5)
    ax.set_title("Tested landscape: normalized joint advantage by condition (points are not a continuum)", pad=22)
    save(fig, "fig7_landscape", pd.DataFrame(rows))


# ═════════════════════════════════════════════════════════════════════════════
def fig8_resources():
    u = MASTER[(MASTER.attacker == ATT["sonnet"]) & (MASTER.game == "J")].copy()
    u = u[["family", "cell", "unit_id", "n_fragments", "answer_call_output_tokens", "completion", "rbnc"]]
    # post-hoc token arm: the answering call's usage from the provider result records
    tok = []
    for line in open("results/batches/single-token-edge-J.results.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if r["cell"] == "edge-token":
            tok.append({"unit": r["unit"], "output_tokens": r["usage"]["output_tokens"], "stop_reason": r["stop_reason"]})
    tok = pd.DataFrame(tok)
    nfr = ST[(ST.attacker == "One-shot Sonnet") & (ST.condition == "token")].set_index("pool").n_fragments
    tok["n_fragments"] = tok.unit.str.replace("-", "_").map(nfr)
    fig, ax = plt.subplots(figsize=(SINGLE, 2.7))
    mk = {"headline": ("o", C["sonnet"], "headline J (46)"), "grid": ("^", "#7F7F7F", "grid J (216)"),
          "identifier": ("s", C["schema"], "identifier J (20)")}
    rows = []
    for fam, (m, c, lab) in mk.items():
        g = u[u.family == fam]
        ax.scatter(g.n_fragments, g.answer_call_output_tokens / 1000, marker=m, s=11, color=c, alpha=0.75, linewidths=0, label=lab, zorder=2)
        for _, r in g.iterrows():
            rows.append({"set": fam, "unit": r.unit_id, "cell": r.cell, "n_fragments": r.n_fragments,
                         "answer_call_output_tokens": r.answer_call_output_tokens, "rbnc": bool(r.rbnc), "post_hoc": False})
    ax.scatter(tok.n_fragments, tok.output_tokens / 1000, marker="D", s=13, facecolors="white", edgecolors=C["token"],
               linewidths=0.8, label="single-token arm, post hoc (20)", zorder=3)
    for _, r in tok.iterrows():
        rows.append({"set": "single-token edge (post hoc)", "unit": r.unit, "cell": "edge__token", "n_fragments": r.n_fragments,
                     "answer_call_output_tokens": r.output_tokens, "rbnc": False, "post_hoc": True})
    rb = u[u.rbnc == True]  # noqa: E712
    ax.scatter(rb.n_fragments, rb.answer_call_output_tokens / 1000, s=70, facecolors="none", edgecolors=C["token"], linewidths=1.2, zorder=4)
    ax.annotate("RBNC: random / token-window\npool_002, 322 fragments", (float(rb.n_fragments.iloc[0]), 128),
                xytext=(30, 112), textcoords="data", ha="left", va="top", fontsize=6.3, color=C["token"],
                arrowprops=dict(arrowstyle="-", color=C["token"], lw=0.6))
    ax.axhline(128, color="black", lw=0.7, ls="--", zorder=1)
    ax.annotate("128k per-call output budget", (690, 128), xytext=(0, 3), textcoords="offset points", fontsize=6.5, va="bottom", ha="right")
    ax.set_xlabel("fragments in the unit (pool)"); ax.set_ylabel("output tokens of the answering call (k)")
    ax.set_xlim(0, 700); ax.set_ylim(0, 140)
    ax.legend(loc="lower right", fontsize=6.2, handletextpad=0.3, borderaxespad=0.2, markerscale=1.2)
    ax.set_title("Output tokens grow with fragment count, but do not fix completion")
    save(fig, "fig8_resource_scaling", pd.DataFrame(rows))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for f in (fig1_headline_attackers, fig2_grid, fig3_decomposition, fig4_O_vs_J, fig5_identifiers,
              fig6_single_token, fig7_landscape, fig8_resources):
        print(f.__name__)
        f()
    print("done")
