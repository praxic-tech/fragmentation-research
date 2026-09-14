"""
audit_packet_numbers.py — cross-check the numbers quoted in
docs/PAPER_WRITING_PACKET.md against their source artifacts. Each check formats
a value read from a frozen artifact exactly as the packet quotes it and asserts
the string occurs in the packet. Prints every check; exits non-zero on a miss.

    python results/paper_tables/audit_packet_numbers.py
"""

import json
import os
import re
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(ROOT)
T = "results/final_analysis/TABLES"
P = re.sub(r"\s+", " ", open("docs/PAPER_WRITING_PACKET.md", encoding="utf-8").read().replace("−", "-"))
S = json.load(open("results/single_token_edge/analysis/summary.json", encoding="utf-8"))
L = json.load(open("results/run_ledger.json", encoding="utf-8"))
tb = pd.read_csv(f"{T}/table_B_headline_J.csv").set_index("attacker")
tb2 = pd.read_csv(f"{T}/table_B2_headline_paired.csv")
tc = pd.read_csv(f"{T}/table_C_grid_J.csv")
tc4 = pd.read_csv(f"{T}/table_C4_grid_attacker_paired.csv")
td = pd.read_csv(f"{T}/table_D_game_O.csv")
te = pd.read_csv(f"{T}/table_E_identifier_J.csv").set_index("attacker")
te2 = pd.read_csv(f"{T}/table_E2_identifier_rule.csv").set_index("attacker")
te3 = pd.read_csv(f"{T}/table_E3_identifier_membership.csv").set_index("attacker")
tg = pd.read_csv(f"{T}/table_G_resource.csv").set_index("experiment")
tr = pd.read_csv(f"{T}/table_R_relationships.csv")
th = pd.read_csv(f"{T}/table_H_headline_vs_grid.csv").set_index("metric")
M = pd.read_csv("results/final_analysis/MASTER_RESULTS.csv")
SON, MEM, EMB = "One-shot Sonnet", "Memon-inspired", "Embedding (post-hoc exploratory)"

fails = 0


def check(label, s):
    global fails
    s = s.replace("−", "-")
    ok = s in P
    fails += 0 if ok else 1
    print(f"  {'ok  ' if ok else 'MISS'} {label}: {s}")


def ci(r, m, lo, hi):
    return f"{r[m]:.3f} [{r[lo]:.3f}, {r[hi]:.3f}]"


print("headline")
for a, lab in ((SON, "sonnet"), (MEM, "memon"), (EMB, "embed")):
    r = tb.loc[a]
    check(f"{lab} F1_J", ci(r, "F1_J_mean", "F1_J_lo", "F1_J_hi"))
    check(f"{lab} F1_L", ci(r, "F1_L_mean", "F1_L_lo", "F1_L_hi"))
    check(f"{lab} A_J", ci(r, "A_J_mean", "A_J_lo", "A_J_hi"))
    check(f"{lab} q", ci(r, "q_micro", "q_micro_lo", "q_micro_hi"))
check("analytic F1_L", ci(tb.loc["Analytic one-bucket"], "F1_L_mean", "F1_L_lo", "F1_L_hi"))
check("analytic F1_J", ci(tb.loc["Analytic one-bucket"], "F1_J_mean", "F1_J_lo", "F1_J_hi"))
check("sonnet t-interval", f"[{tb.loc[SON].F1_J_t_lo:.3f}, {tb.loc[SON].F1_J_t_hi:.3f}]")
for m, a, b in (("F1_J", SON, MEM), ("F1_L", SON, MEM), ("q", SON, MEM), ("F1_L", EMB, MEM), ("F1_L", SON, EMB), ("F1_J", SON, "Analytic one-bucket"), ("F1_J", MEM, "Analytic one-bucket")):
    q = tb2[(tb2.metric == m) & (tb2.a == a) & (tb2.b == b)].iloc[0]
    check(f"paired {a}-{b} {m}", f"{q.mean_diff:.3f} [{q.mean_lo:.3f}, {q.mean_hi:.3f}]")

print("grid")
for c in tc.condition.unique():
    g = tc[tc.condition == c].set_index("attacker")
    s = g.loc[SON]
    check(f"{c} F1_J", ci(s, "F1_J_mean", "F1_J_lo", "F1_J_hi"))
    check(f"{c} A_J", ci(s, "A_J_mean", "A_J_lo", "A_J_hi"))
    check(f"{c} F1_L", ci(s, "F1_L_mean", "F1_L_lo", "F1_L_hi"))
    check(f"{c} q", ci(s, "q_micro", "q_micro_lo", "q_micro_hi"))
    check(f"{c} Memon/Embed F1_L", f"{g.loc[MEM].F1_L_mean:.3f} / {g.loc[EMB].F1_L_mean:.3f}")
    o = td[(td.condition == c) & (td.attacker == SON)].iloc[0]
    check(f"{c} O tau", ci(o, "tau_mean", "tau_lo", "tau_hi"))
mem = tc[tc.attacker == MEM]; emb = tc[tc.attacker == EMB]
check("memon grid F1_J range", f"{mem.F1_J_mean.min():.3f}–{mem.F1_J_mean.max():.3f}")
check("embed grid F1_J range", f"{emb.F1_J_mean.min():.3f}–{emb.F1_J_mean.max():.3f}")
sm = tc4[(tc4.metric == "F1_J") & (tc4.a == SON) & (tc4.b == MEM)]
check("sonnet-memon grid range", f"{sm.mean_diff.min():.3f} [{sm.loc[sm.mean_diff.idxmin()].mean_lo:.3f}, {sm.loc[sm.mean_diff.idxmin()].mean_hi:.3f}]")
check("sonnet-memon grid max", f"{sm.mean_diff.max():.3f} [{sm.loc[sm.mean_diff.idxmax()].mean_lo:.3f}, {sm.loc[sm.mean_diff.idxmax()].mean_hi:.3f}]")
em = tc4[(tc4.metric == "F1_L") & (tc4.a == EMB) & (tc4.b == MEM)]
check("embed-memon grid range", f"{em.mean_diff.min():.3f} to +{em.mean_diff.max():.3f}")
check("headline vs grid F1_J", f"{th.loc['F1_J']['diff']:.3f} [{th.loc['F1_J']['lo']:.3f}, {th.loc['F1_J']['hi']:.3f}]")

print("game O")
h = td[td.condition == "headline (full length)"].set_index("attacker")
check("O headline sonnet", ci(h.loc[SON], "tau_mean", "tau_lo", "tau_hi"))
check("O headline greedy", ci(h.loc["Jaccard-Greedy"], "tau_mean", "tau_lo", "tau_hi"))
check("O headline mst", ci(h.loc["Jaccard-MST"], "tau_mean", "tau_lo", "tau_hi"))
check("O headline median", f"{h.loc[SON].tau_median:.3f}")

print("identifiers")
for a, lab in ((SON, "sonnet"), (MEM, "memon"), (EMB, "embed")):
    r, q = te.loc[a], te2.loc[a]
    check(f"{lab} id F1_J", ci(r, "F1_J_mean", "F1_J_lo", "F1_J_hi"))
    check(f"{lab} id F1_L", ci(r, "F1_L_mean", "F1_L_lo", "F1_L_hi"))
    check(f"{lab} A_schema", f"{q.A_schema_mean:.3f} [{q.ci90_lo:.3f}, {q.ci90_hi:.3f}]")
    check(f"{lab} raw diff", f"{q.raw_diff_mean:.3f} [{q.raw_ci90_lo:.3f}, {q.raw_ci90_hi:.3f}]")
    check(f"{lab} link precision", ci(te3.loc[a], "linkage_precision_mean", "lo", "hi"))

print("single token")
A = S["attackers"][SON]
for k in ("A_VJ", "V_J", "V_L", "A_VL", "A_VJ_pred", "F1_J", "F1_L", "A_J"):
    p = A["paired_sentence_minus_token"][k]
    check(f"edge {k} means", f"{A['means']['sentence'][k]:.3f}")
    check(f"edge {k} token", f"{A['means']['token'][k]:.3f}")
    check(f"edge {k} diff", f"{p['mean_diff']:.3f} [{p['ci95'][0]:.3f}, {p['ci95'][1]:.3f}]")
for att in (MEM, EMB):
    p = S["attackers"][att]["paired_sentence_minus_token"]["A_VJ"]
    check(f"edge {att} A_VJ diff", f"{p['mean_diff']:.3f} [{p['ci95'][0]:.3f}, {p['ci95'][1]:.3f}]")
R = S["resources"]
check("edge cost sentence", f"${R['sentence']['cost_usd']:.2f}")
check("edge cost token", f"${R['token']['cost_usd']:.2f}")
check("edge cost total", f"${R['sentence']['cost_usd'] + R['token']['cost_usd']:.2f}")
pp = pd.read_csv("results/single_token_edge/analysis/per_pool.csv")
pp = pp[pp.attacker == SON]
for c in ("sentence", "token"):
    g = pp[pp.condition == c]
    check(f"null V_J {c}", f"{g.null_oracle_V_J.mean():.3f}")
    check(f"null V_L {c}", f"{g.null_oracle_V_L.mean():.3f}")
piv = pp.pivot(index="pool", columns="condition", values="A_VJ")
d = piv.sentence - piv.token
check("edge diff range", f"{d.min():.3f} to {d.max():.3f}")
check("token frag range", f"{int(pp[pp.condition == 'token'].n_fragments.min())}–{int(pp[pp.condition == 'token'].n_fragments.max())}")

print("resources")
tot = tg.loc["TOTAL (final run, one-shot)"]
check("final run cost", f"${tot.cost_usd:.2f}")
check("final run units", f"{int(tot.units_submitted)} one-shot units")
check("ledger total", f"${L['spend']['observed_usd']:.2f}")
rho = tr[(tr.game == "J") & (tr.x == "n_fragments") & (tr.y == "answer_call_output_tokens")].iloc[0]
check("rho frags output J", f"{rho.rho:.3f} [{rho.lo:.3f}, {rho.hi:.3f}]")
rho = tr[(tr.game == "J") & (tr.family == "grid (pooled; pool-clustered)") & (tr.attacker == SON) & (tr.x == "n_fragments") & (tr.y == "F1_J")].iloc[0]
check("rho frags F1_J pooled grid", f"{rho.rho:.3f} [{rho.lo:.3f}, {rho.hi:.3f}]")
u = M[(M.attacker == SON) & (M.game == "J") & (M.completion == "completed")]
check("largest completed", f"{int(u.n_fragments.max())} fragments")
hb = M[(M.family == "headline") & (M.attacker == "Analytic one-bucket")].b_J
check("headline b_J range", f"{hb.min():.3f}–{hb.max():.3f}")

print(f"\n{fails} miss(es)")
sys.exit(1 if fails else 0)
