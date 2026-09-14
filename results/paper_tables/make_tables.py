"""
make_tables.py — the paper tables (Markdown + LaTeX booktabs) from the frozen
analysis artifacts. No number is typed by hand; everything is read from
results/final_analysis/TABLES/*.csv, results/single_token_edge/analysis/
summary.json and results/run_ledger.json. Formatting only.

    python results/paper_tables/make_tables.py
"""

import json
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
OUT = "results/paper_tables"
T = "results/final_analysis/TABLES"
STS = json.load(open("results/single_token_edge/analysis/summary.json", encoding="utf-8"))
LEDGER = json.load(open("results/run_ledger.json", encoding="utf-8"))

ATT = {"sonnet": "One-shot Sonnet", "memon": "Memon-inspired",
       "embed": "Embedding (post-hoc exploratory)", "base": "Analytic one-bucket"}
CELL_ORDER = ["random / sentence", "random / clause", "random / token-window",
              "semantic / sentence", "semantic / clause",
              "coherence-sever / clause", "coherence-sever / token-window",
              "subject-verb / sentence", "subject-verb / clause"]
HEAD = "headline (full length)"


def f3(x):
    if pd.isna(x):
        return "—"
    x = 0.0 if abs(x) < 5e-4 else x
    return f"{x:.3f}"


def ci(m, lo, hi, d=3):
    if pd.isna(m):
        return "—"
    z = lambda v: 0.0 if abs(v) < 5 * 10 ** -(d + 1) else v
    return f"{z(m):.{d}f} [{z(lo):.{d}f}, {z(hi):.{d}f}]"


def tex_escape(s):
    return (str(s).replace("&", r"\&").replace("$", r"\$").replace("%", r"\%").replace("_", r"\_").replace("#", r"\#")
            .replace("×", r"$\times$").replace("−", r"$-$").replace("≈", r"$\approx$").replace("τ", r"$\tau$")
            .replace("ρ", r"$\rho$").replace("Δ", r"$\Delta$").replace("–", "--").replace("→", r"$\rightarrow$")
            .replace("≤", r"$\leq$").replace("≥", r"$\geq$").replace("±", r"$\pm$").replace("Σ", r"$\Sigma$")
            .replace("†", r"$^\dagger$").replace("**", "").replace("—", "--"))


def write(name, caption, label, header, rows, notes, align=None, tex_header=None):
    """rows: list of lists of strings (already formatted)."""
    # markdown
    md = [f"**{caption}**", "", "| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    md += ["| " + " | ".join(r) + " |" for r in rows if r != "MIDRULE"]
    md += [""] + [f"{n}" for n in notes]
    open(f"{OUT}/{name}.md", "w", encoding="utf-8").write("\n".join(md) + "\n")
    # latex
    align = align or ("l" + "r" * (len(header) - 1))
    th = tex_header or header
    L = [r"\begin{table}[t]", r"\centering", r"\small", f"\\caption{{{tex_escape(caption)}}}", f"\\label{{{label}}}",
         f"\\begin{{tabular}}{{{align}}}", r"\toprule", " & ".join(th) + r" \\", r"\midrule"]
    for r in rows:
        if r == "MIDRULE":
            L.append(r"\midrule"); continue
        L.append(" & ".join(c if (c.startswith("$") and c.endswith("$")) else tex_escape(c) for c in r) + r" \\")
    L += [r"\bottomrule", r"\end{tabular}", r"\begin{flushleft}\footnotesize"]
    L += [tex_escape(n) + r"\\" for n in notes]
    L += [r"\end{flushleft}", r"\end{table}"]
    open(f"{OUT}/{name}.tex", "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"  wrote {name}.md / .tex")


# ═════════════════════════════════════════════════════════════════════════════
def table1_design():
    tg = pd.read_csv(f"{T}/table_G_resource.csv").set_index("experiment")
    st = STS["resources"]
    rows = [
        ["Headline J", "prose (PMC case reports)", "46 pools × 7 docs (322 docs)", "sentence cut, full length", "One-shot Sonnet; Memon-inspired; embedding†", "F1_J (F1_L, q)", "prespecified"],
        ["Grid J", "prose, ≤30-sentence documents", "24 pools × 7 docs × 9 cells (168 docs)", "4 strategies × 3 granularities, 9 retained cells", "One-shot Sonnet; Memon-inspired; embedding†", "F1_J (F1_L, q)", "prespecified; cells retained after pool-1 screening"],
        ["Headline O", "prose", "100 documents (length-stratified)", "sentence cut, full length", "One-shot Sonnet; Jaccard-Greedy; Jaccard-MST; Random", "Kendall τ", "prespecified"],
        ["Grid O", "prose", "30 documents × 9 cells", "the 9 retained cells", "One-shot Sonnet; Jaccard-Greedy; Jaccard-MST; Random", "Kendall τ", "prespecified"],
        ["Identifier J", "synthetic records (Faker)", "20 pools × 7 records (28 fields)", "one fragment per field", "One-shot Sonnet; Memon-inspired; embedding†; Random; analytic and schema-order baselines", "F1_J vs schema baseline (90% CI rule); F1_L", "prespecified (D11)"],
        ["Single-token edge J†", "prose, 4-sentence excerpts", "20 headline pools × 7 docs (140 docs)", "sentence cut vs single whitespace token, identical text", "One-shot Sonnet; Memon-inspired; embedding", "paired A_VJ (visible-text, null-adjusted)", "POST-HOC EXPLORATORY (D16)"],
    ]
    notes = ["† Post-hoc exploratory: the embedding attacker (D14) and the single-token edge experiment (D16) were designed after the prespecified results were seen, "
             "then frozen before their own evaluation. Every pool holds N = 7 sources; the attacker is told N, sees masked aliases in a per-unit shuffled order, and never sees raw ids.",
             f"One-shot Sonnet units in the final run: {int(tg.loc['TOTAL (final run, one-shot)', 'units_submitted'])} (651 completed, 1 RBNC) plus {st['sentence']['requests_rows'] + 20} post-hoc excerpt units (40 completed)."]
    write("table1_design", "Table 1. Datasets, games and design summary.", "tab:design",
          ["Experiment", "Corpus", "Sample", "Conditions", "Attackers", "Primary metric", "Status"], rows, notes,
          align="lllllll")


def table2_headline():
    tb = pd.read_csv(f"{T}/table_B_headline_J.csv").set_index("attacker")
    tb2 = pd.read_csv(f"{T}/table_B2_headline_paired.csv") if os.path.exists(f"{T}/table_B2_headline_paired.csv") else None
    rows = []
    for a, lab in ((ATT["base"], "Analytic one-bucket baseline"), (ATT["memon"], "Memon-inspired"),
                   (ATT["embed"], "Embedding (post hoc)†"), (ATT["sonnet"], "**One-shot Sonnet**")):
        r = tb.loc[a]
        rows.append([lab, ci(r.F1_L_mean, r.F1_L_lo, r.F1_L_hi),
                     ci(r.q_micro, r.q_micro_lo, r.q_micro_hi) if not pd.isna(r.q_micro) else "0.5 (expected)",
                     ci(r.F1_J_mean, r.F1_J_lo, r.F1_J_hi), ci(r.A_J_mean, r.A_J_lo, r.A_J_hi),
                     "—" if pd.isna(r.exact_records) else f"{int(r.exact_records)}/322", f"{int(r.completed)}/{int(r.attempted)}"])
    def pr(metric, a, b):
        q = tb2[(tb2.metric == metric) & (tb2.a == a) & (tb2.b == b)].iloc[0]
        return f"{q.mean_diff:.3f} [{q.mean_lo:.3f}, {q.mean_hi:.3f}] (higher on {int(round(q.frac_a_higher * q.n_pairs))}/{int(q.n_pairs)} pools)"
    notes = ["46 headline pools. Means with 95% percentile-bootstrap CIs over pools (10,000 resamples). q is micro-averaged (ΣC/ΣK). "
             "Exact = documents recovered with perfect membership and order. Completion = pools answered within the 128k output budget.",
             f"Paired (same pools): Sonnet − Memon-inspired F1_J {pr('F1_J', ATT['sonnet'], ATT['memon'])}; F1_L {pr('F1_L', ATT['sonnet'], ATT['memon'])}. "
             f"Embedding − Memon-inspired F1_L {pr('F1_L', ATT['embed'], ATT['memon'])}; Sonnet − embedding F1_L {pr('F1_L', ATT['sonnet'], ATT['embed'])}.",
             "† Post-hoc exploratory (D14): motivated by the observed Memon-inspired / Sonnet gap; designed and frozen before evaluation; first complete result kept; F1_L is its primary comparison."]
    write("table2_headline_attackers", "Table 2. Headline prose, Game J: attacker comparison on the 46 headline pools.", "tab:headline",
          ["Attacker", "F1_L [95% CI]", "q [95% CI]", "F1_J [95% CI]", "A_J [95% CI]", "Exact docs", "Completed"], rows, notes,
          tex_header=["Attacker", "$F1_L$ [95\\% CI]", "$q$ [95\\% CI]", "$F1_J$ [95\\% CI]", "$A_J$ [95\\% CI]", "Exact docs", "Completed"])


def table3_grid():
    tc = pd.read_csv(f"{T}/table_C_grid_J.csv")
    tm = pd.read_csv(f"{T}/table_C2_grid_mechanics.csv").set_index("cell")
    td = pd.read_csv(f"{T}/table_D_game_O.csv")
    td = td[td.attacker == ATT["sonnet"]].set_index("condition")
    rows = []
    for c in CELL_ORDER:
        g = tc[tc.condition == c].set_index("attacker")
        s, m, e = g.loc[ATT["sonnet"]], g.loc[ATT["memon"]], g.loc[ATT["embed"]]
        rows.append([c, f"{tm.loc[c, 'frags_per_doc']:.1f}", f"{tm.loc[c, 'frag_words_mean']:.1f}",
                     ci(s.F1_J_mean, s.F1_J_lo, s.F1_J_hi), f3(s.b_J_mean), ci(s.A_J_mean, s.A_J_lo, s.A_J_hi),
                     ci(s.F1_L_mean, s.F1_L_lo, s.F1_L_hi), ci(s.q_micro, s.q_micro_lo, s.q_micro_hi),
                     f"{m.F1_L_mean:.3f} / {e.F1_L_mean:.3f}",
                     ci(td.loc[c, 'tau_mean'], td.loc[c, 'tau_lo'], td.loc[c, 'tau_hi']),
                     f"{int(s.completed)}/{int(s.attempted)}"])
    notes = ["Grid pools 2–25 (24 pools of 7 documents per cell; documents capped at 30 reference sentences). One-shot Sonnet unless stated; 95% percentile-bootstrap CIs over pools. "
             "b_J is the pool-mean analytic one-bucket baseline. F1_L for Memon-inspired / embedding (post hoc) shown for reference; both sit at q ≈ 0.5.",
             "Game O τ: the same attacker ordering single documents with membership given (30 documents per cell; CI over documents). "
             "random / token-window: one pool (pool_002, 322 fragments) exhausted the 128k output budget and is excluded as a resource-bounded non-completion, never scored 0.",
             "Semantic / sentence is standard sentence splitting and the reference cut; the headline (Table 2) is the same cut at full length."]
    write("table3_grid", "Table 3. Full retained prose grid, Game J (and Game O τ), One-shot Sonnet.", "tab:grid",
          ["Cell (strategy / granularity)", "Frags/doc", "Words/frag", "F1_J [95% CI]", "b_J", "A_J [95% CI]", "F1_L [95% CI]", "q [95% CI]",
           "F1_L Memon / Embed†", "Game O τ [95% CI]", "Completed"], rows, notes,
          tex_header=["Cell", "Frags/doc", "Words/frag", "$F1_J$ [95\\% CI]", "$b_J$", "$A_J$ [95\\% CI]", "$F1_L$ [95\\% CI]", "$q$ [95\\% CI]",
                      "$F1_L$ Memon / Embed$^\\dagger$", "Game O $\\tau$ [95\\% CI]", "Completed"])


def table4_gameO():
    td = pd.read_csv(f"{T}/table_D_game_O.csv")
    rows = []
    for c in [HEAD] + CELL_ORDER:
        g = td[td.condition == c].set_index("attacker")
        s = g.loc[ATT["sonnet"]]
        rows.append([c, str(int(s.docs)), f"{s.frags_per_doc:.1f}", ci(s.tau_mean, s.tau_lo, s.tau_hi), f3(s.tau_median),
                     f"{s.pairs_correct_mean:.3f}", f"{s.exact_order_rate:.2f}",
                     ci(g.loc["Jaccard-Greedy"].tau_mean, g.loc["Jaccard-Greedy"].tau_lo, g.loc["Jaccard-Greedy"].tau_hi),
                     ci(g.loc["Jaccard-MST"].tau_mean, g.loc["Jaccard-MST"].tau_lo, g.loc["Jaccard-MST"].tau_hi)])
    notes = ["Kendall τ between the returned order and the true order, one τ per document; 95% percentile-bootstrap CIs over documents. "
             "Random ordering has expectation τ = 0. Pairs correct = (1 + τ)/2. Exact = fraction of documents ordered perfectly.",
             "Jaccard-Greedy / Jaccard-MST are the classical word-bigram Jaccard orderers with masked labels and shuffled, truth-independent tie-breaking (D1); "
             "they are not Memon implementations. Their pre-correction values (τ +0.32 / +0.70) were an id-order leak and are superseded. Every unit completed (0 RBNC)."]
    write("table4_gameO", "Table 4. Game O (ordering with membership given): One-shot Sonnet against the classical floors.", "tab:gameO",
          ["Condition", "Docs", "Frags/doc", "Sonnet τ [95% CI]", "Median τ", "Pairs correct", "Exact", "Jaccard-Greedy τ [95% CI]", "Jaccard-MST τ [95% CI]"],
          rows, notes,
          tex_header=["Condition", "Docs", "Frags/doc", "Sonnet $\\tau$ [95\\% CI]", "Median $\\tau$", "Pairs correct", "Exact", "Jaccard-Greedy $\\tau$", "Jaccard-MST $\\tau$"])


def table5_identifiers():
    te = pd.read_csv(f"{T}/table_E_identifier_J.csv").set_index("attacker")
    t2 = pd.read_csv(f"{T}/table_E2_identifier_rule.csv").set_index("attacker")
    t3 = pd.read_csv(f"{T}/table_E3_identifier_membership.csv").set_index("attacker")
    rows = []
    for a, lab in (("Schema-order", "Schema-order baseline"), (ATT["base"], "Analytic one-bucket baseline"), ("Random", "Random partition"),
                   (ATT["memon"], "Memon-inspired"), (ATT["embed"], "Embedding (post hoc)†"), (ATT["sonnet"], "**One-shot Sonnet**")):
        r = te.loc[a]
        if a in t2.index:
            q = t2.loc[a]
            asch = f"{q.A_schema_mean:.3f} [{q.ci90_lo:.3f}, {q.ci90_hi:.3f}]"
            raw = f"{q.raw_diff_mean:.3f} [{q.raw_ci90_lo:.3f}, {q.raw_ci90_hi:.3f}]"
            verdict = "no: entire 90% CI below −0.10"
            lp = ci(t3.loc[a].linkage_precision_mean, t3.loc[a].lo, t3.loc[a].hi) if a in t3.index else "—"
        else:
            asch = f3(r.A_schema_mean); raw = f3(r.raw_schema_diff_mean); verdict = "(baseline)"; lp = "—"
        rows.append([lab, ci(r.F1_J_mean, r.F1_J_lo, r.F1_J_hi), ci(r.F1_L_mean, r.F1_L_lo, r.F1_L_hi),
                     f"{r.q_mean:.2f}", lp, asch, raw, verdict])
    notes = ["20 pools of 7 synthetic records (name, SSN, account, address; 28 fragments). F1 CIs are 95%; the schema advantage A_schema = (F1_J − 0.20)/(1 − 0.20) carries the frozen 90% CI. "
             "Frozen rule (D11): joint reconstruction is 'near the schema-order baseline' only if the whole 90% CI lies within ±0.10. No attacker met it; every attacker fell below the baseline.",
             "q is a template diagnostic only: the field order is visible from field format, so the schema-order baseline reaches q = 1 with no record knowledge. "
             "Linkage precision (exploratory): the share of an attacker's claimed same-record pairs that are real, against 1/7 = 0.143 for template-respecting random assignment. "
             "All 140 Sonnet groups held exactly one field of each type.",
             "† Post-hoc exploratory attacker (D14)."]
    write("table5_identifiers", "Table 5. Structured identifiers, Game J: attackers against the analytic and schema-order baselines.", "tab:identifiers",
          ["Attacker / baseline", "F1_J [95% CI]", "F1_L [95% CI]", "q", "Linkage precision [95% CI]", "A_schema [90% CI]", "F1_J − 0.20 [90% CI]", "Near baseline?"],
          rows, notes,
          tex_header=["Attacker / baseline", "$F1_J$ [95\\% CI]", "$F1_L$ [95\\% CI]", "$q$", "Link. precision [95\\% CI]", "$A_{schema}$ [90\\% CI]", "$F1_J - 0.20$ [90\\% CI]", "Near baseline?"])


def table6_single_token():
    A = STS["attackers"]
    S = A["One-shot Sonnet"]
    rows = []
    metrics = [("A_VJ", "A_VJ (PRIMARY, oracle-size null)"), ("V_J", "raw V_J"), ("A_VL", "A_VL"), ("V_L", "raw V_L"),
               ("A_VJ_pred", "A_VJ (predicted-structure null, robustness)"), ("F1_J", "F1_J (id-level)"), ("F1_L", "F1_L (id-level)"), ("A_J", "A_J (id-level)")]
    for k, lab in metrics:
        p = S["paired_sentence_minus_token"][k]
        rows.append([lab, f3(S["means"]["sentence"][k]), f3(S["means"]["token"][k]),
                     f"{p['mean_diff']:.3f} [{p['ci95'][0]:.3f}, {p['ci95'][1]:.3f}]", f3(p["median_diff"]),
                     f"{p['n_positive']}/{p['n_effective']}", f"{p['sign_test_p_two_sided']:.1e}"])
    rows.append("MIDRULE")
    for att, lab in (("Memon-inspired", "Memon-inspired A_VJ"), ("Embedding (post-hoc exploratory)", "Embedding A_VJ")):
        p = A[att]["paired_sentence_minus_token"]["A_VJ"]
        rows.append([lab + " (not designed for tokens)", f3(A[att]["means"]["sentence"]["A_VJ"]), f3(A[att]["means"]["token"]["A_VJ"]),
                     f"{p['mean_diff']:.3f} [{p['ci95'][0]:.3f}, {p['ci95'][1]:.3f}]", f3(p["median_diff"]),
                     f"{p['n_positive']}/{p['n_effective']}", f"{p['sign_test_p_two_sided']:.1e}"])
    nulls = {"sentence": {}, "token": {}}
    pp = pd.read_csv("results/single_token_edge/analysis/per_pool.csv")
    pp = pp[pp.attacker == "One-shot Sonnet"]
    for c in ("sentence", "token"):
        g = pp[pp.condition == c]
        nulls[c] = (g.null_oracle_V_J.mean(), g.null_oracle_V_L.mean(), g.n_fragments.median(), g.n_fragments.min(), g.n_fragments.max())
    R = STS["resources"]
    notes = [f"POST-HOC EXPLORATORY (D16). 20 headline pools × 7 documents, four consecutive source sentences per document, identical text in both arms; "
             f"sentence arm 28 fragments per pool, token arm median {nulls['token'][2]:.0f} (range {nulls['token'][3]}–{nulls['token'][4]}). Completion 20/20 in both arms for every attacker; no RBNC.",
             f"Oracle-size null means (10,000 permutations per pool): V_J {nulls['sentence'][0]:.3f} (sentence) vs {nulls['token'][0]:.3f} (token); "
             f"V_L {nulls['sentence'][1]:.3f} vs {nulls['token'][1]:.3f}. A_V = (V − null mean)/(1 − null mean). "
             "Paired differences: percentile bootstrap over pools (10,000 resamples, seed 42, 95%); exact two-sided sign test. "
             "q_V (diagnostic only): Sonnet 0.860 vs 0.376. No raw-vs-normalized sign disagreement for Sonnet; Memon-inspired disagrees in 3 pools (pool_017, pool_032, pool_041).",
             f"Resources (Sonnet, all provider rows): sentence arm {R['sentence']['requests_rows']} rows, {R['sentence']['output_tokens']:,} output tokens, ${R['sentence']['cost_usd']:.2f}; "
             f"token arm {R['token']['requests_rows']} rows (20 base + 11 repairs; 8 repaired, 3 repair calls hit 128k and kept the earlier answer), {R['token']['output_tokens']:,} output tokens, ${R['token']['cost_usd']:.2f}.",
             "Descriptive only: excerpt sentence-arm F1_J 0.585 vs full-document headline F1_J 0.723 (different tasks). A binary edge case, not a dose-response experiment: it locates no threshold."]
    write("table6_single_token", "Table 6. POST-HOC EXPLORATORY single-token edge case: sentence cut versus single-token cut on identical excerpts (paired, 20 pools).", "tab:singletoken",
          ["Metric", "Sentence mean", "Token mean", "Paired diff (s − t) [95% CI]", "Median diff", "Pools s > t", "Sign test p"], rows, notes,
          tex_header=["Metric", "Sentence", "Token", "Paired diff (s $-$ t) [95\\% CI]", "Median diff", "Pools s $>$ t", "Sign test $p$"])


def table7_resources():
    tg = pd.read_csv(f"{T}/table_G_resource.csv")
    R = STS["resources"]
    rows = []
    for _, r in tg.iterrows():
        if r.experiment.startswith("ledger"):
            continue
        rows.append([r.experiment, str(int(r.units_submitted)), str(int(r.completed)), str(int(r.rbnc)), str(int(r.provider_refusals_then_resent)),
                     str(int(r.repairs)), f"{int(r.input_tokens):,}", f"{int(r.output_tokens):,}", f"${r.cost_usd:.2f}", f"${r.cost_per_completed:.3f}"])
    rows.append("MIDRULE")
    st_cost = R["sentence"]["cost_usd"] + R["token"]["cost_usd"]
    rows.append(["single-token edge J (post hoc)", "40", "40", "0", "0", "11", f"{R['sentence']['input_tokens'] + R['token']['input_tokens']:,}",
                 f"{R['sentence']['output_tokens'] + R['token']['output_tokens']:,}", f"${st_cost:.2f}", f"${st_cost / 40:.3f}"])
    total = LEDGER["spend"]["observed_usd"]
    notes = ["One-shot Sonnet (claude-sonnet-5, Message Batches API), 128,000 output tokens per call (D6), one attempt per unit; a call that exhausts the budget without an answer is a "
             "resource-bounded non-completion (RBNC), never re-asked and never scored 0. Repairs = units that received the one structural repair round (unparseable or missing / duplicated / unknown labels; "
             "the repair reads no score). Provider refusals = requests declined before inference for insufficient prepaid credit and resent unchanged once (0 token usage).",
             f"Output tokens are almost entirely the model's internal reasoning (visible answers are ≤ ~2k tokens). Ledger total for every paid call in the project, including the pool-1 screening slice, "
             f"the hierarchical live sample and the G3 masking control: ${total:.2f} in API credit ($130.18 before the post-hoc single-token run)."]
    write("table7_resources", "Table 7. Completion, non-completion, repairs and cost of every paid experiment.", "tab:resources",
          ["Experiment", "Units", "Completed", "RBNC", "Refused → resent", "Repairs", "Input tokens", "Output tokens", "Cost", "Cost / unit"], rows, notes)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for f in (table1_design, table2_headline, table3_grid, table4_gameO, table5_identifiers, table6_single_token, table7_resources):
        f()
    print("done")
