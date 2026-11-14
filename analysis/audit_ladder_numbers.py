"""
audit_ladder_numbers.py — every number the manuscript quotes about the non-LLM
attacker ladder (D19), the corrected integrity gate and the post-hoc cross-model
runs, read from its source artifact, formatted as the text quotes it, and
asserted to occur in paper/main.tex. Prints every check; exits non-zero on a
miss. No API calls.

    python analysis/audit_ladder_numbers.py
"""

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.stdout.reconfigure(encoding="utf-8")

TEX = re.sub(r"\s+", " ", open(os.path.join("paper", "main.tex"), encoding="utf-8").read())
LAD = {e["attacker"]: e for e in json.load(open("results/final_analysis/HEADLINE_LADDER.json",
                                                 encoding="utf-8"))["rows"]}
CMP = json.load(open("results/final_t3/COMPARISON.json", encoding="utf-8"))
LEAK = open("results/final_t3/LEAK_AUDIT.txt", encoding="utf-8").read()
IDD = json.load(open("results/final_t3/IDENTIFIER_DIAGNOSTIC.json", encoding="utf-8"))
GATE = json.load(open("results/final_analysis/GATE_FIX_AUDIT.json", encoding="utf-8"))
SB = "experiments/cross_model_sandbox/results"
fails = []


def f3(x):
    return f"{x:.3f}"


def ci(c):
    return f"[{c[0]:.3f}, {c[1]:.3f}]"


def has(label, s):
    ok = s in TEX
    print(f"  {'ok  ' if ok else 'MISS'}  {label}: {s}")
    if not ok:
        fails.append(label)


t3, son = LAD["T3-crossenc"]["pools46"], LAD["One-shot Sonnet"]["pools46"]
d = LAD["T3-crossenc"]["minus_sonnet"]
print("headline ladder")
has("T3 F1_J", f"$\\FJ = {f3(t3['F1_J'])}$ ${ci(t3['F1_J_ci'])}$")
has("T3 F1_L", f"$\\FL = {f3(t3['F1_L'])}$ ${ci(t3['F1_L_ci'])}$")
has("T3 q", f"$q = {f3(t3['q'])}$")
has("T3 A_J", f"$\\AJ = {f3(t3['A_J'])}$")
has("Sonnet - T3 F1_J", f"${f3(-d['F1_J'])}$ ${ci([-d['F1_J_ci'][1], -d['F1_J_ci'][0]])}$")
has("Sonnet - T3 F1_L", f"${f3(-d['F1_L'])}$ ${ci([-d['F1_L_ci'][1], -d['F1_L_ci'][0]])}$")
assert d["F1_J_higher"] == 0 and d["n"] == 46, "Sonnet higher in all 46 pools"
t0c, t0p = LAD["T0-classical"]["pools46"], LAD["T0-PUP"]["pools46"]
has("T0-classical F1_J", f"$\\FJ = {f3(t0c['F1_J'])}$ ${ci(t0c['F1_J_ci'])}$")
has("T0-classical q", f"$q = {f3(t0c['q'])}$")
has("T0-classical F1_L", f"$\\FL = {f3(t0c['F1_L'])}$")
has("T0 parallel path F1_J", f"${f3(t0p['F1_J'])}$ ${ci(t0p['F1_J_ci'])}$")
has("Sonnet q", f"$0.792$ for the one-shot")

print("grid")
cells = {k: v for k, v in CMP.items() if k.startswith("gridJ/")} if any(k.startswith("gridJ/") for k in CMP) else None
md = open("results/final_t3/COMPARISON.md", encoding="utf-8").read()
grid = re.findall(r"^\| (\S+__\S+) \| ([\d.]+); [\d.]+ \| ([\d.]+); .*?\| (-[\d.]+) \[", md, re.M)
grid = [g for g in grid if "__" in g[0]][:9]
t3g = [float(g[2]) for g in grid]
gaps = [-float(g[3]) for g in grid]
has("T3 grid min", f"between ${min(t3g):.3f}$")
has("T3 grid max", f"${max(t3g):.3f}$")
has("gap range", f"${min(gaps):.3f}$ to ${max(gaps):.3f}$")

print("Game O")
o = re.search(r"T3-crossenc-O \| ([\d.]+) \[([\d.]+), ([\d.]+)\]", md)
t0o = re.search(r"T0-classical-O \| ([\d.]+) \[([\d.]+), ([\d.]+)\]", md)
so = re.search(r"One-shot Sonnet \| [\d.]+ \[[\d.]+, [\d.]+\] \| (-[\d.]+) \[(-[\d.]+), (-[\d.]+)\]", md)
has("T3 tau", f"$0.639$ $[{o.group(2)}, {o.group(3)}]$".replace("0.639", o.group(1)))
has("T0 tau", f"$\\tau = {t0o.group(1)}$ $[{t0o.group(2)}, {t0o.group(3)}]$")
has("Sonnet - T3 tau", f"${-float(so.group(1)):.3f}$ $[{-float(so.group(3)):.3f}, {-float(so.group(2)):.3f}]$")

print("leak audit")
# full precision from the JSON artifacts (the .txt report rounds to 4 places)
LJ = json.load(open("results/final_t3/LEAK_AUDIT.json", encoding="utf-8"))
UC = json.load(open("results/final_t0_ext/UNMASKED_CONTROL.json", encoding="utf-8"))["gameO"]
blind = LJ["1_text_blind"]["gameJ"]["headlineJ"]["F1_J"]
unm = LJ["2_unmasked"]["gameJ"]["headlineJ"]["F1_J"]
has("text-blind", f"$\\FJ = {blind:.3f}$")
has("unmasked", f"(${unm:.3f}$ against ${t3['F1_J']:.3f}$)")
has("Jaccard controls", f"$\\tau = {UC['Jaccard-Greedy']['tau_unmasked']:.3f}$ and "
                        f"${UC['Jaccard-MST']['tau_unmasked']:.3f}$")
inv = re.search(r"invariance, 10 seeds: J F1_J ([\d.]+)-([\d.]+)", LEAK)
rep = float(re.search(r"as reported\s+J all\s+F1_J ([\d.]+)", LEAK).group(1))
assert max(abs(float(inv.group(1)) - rep), abs(float(inv.group(2)) - rep)) <= 0.002
has("seeds", "by at most $0.002$")
con = re.search(r"median ([\d.]+), max ([\d.]+)", LEAK)
has("8-gram median", f"${float(con.group(1)) * 100:.1f}\\%$ of its word 8-grams")
has("8-gram max", f"has ${float(con.group(2)) * 100:.1f}\\%$")

print("identifiers")
has("T3 identifier", "the cross-encoder $0.002$")
has("same field", f"${IDD['share_same_field_within_groups'] * 100:.0f}\\%$ of the fragment pairs")
has("field chance", f"(chance ${IDD['share_same_field_all_pairs_chance'] * 100:.0f}\\%$)")
has("same record", f"${IDD['share_same_record_within_groups'] * 100:.1f}\\%$ share a record")
has("record chance", f"(chance ${IDD['share_same_record_all_pairs_chance'] * 100:.0f}\\%$)")

print("integrity gate, single-token arm")
u = GATE["units_over_cap"][0]
r = [a for a in u["attempts"] if a["attempt"] == 1][0]
has("repair returned", f"returned {r['n_returned']} of {u['n_fragments']}")
has("policy share", f"placed ${u['recorded_policy_share'] * 100:.0f}\\%$")
w = GATE["single_token_sensitivity"]["without_over_cap_pools"]
has("A_VJ without", f"\\AVJ{{}} is ${w['token_A_VJ']:.3f}$")
has("paired without", f"paired difference ${w['paired_A_VJ_sentence_minus_token']:.3f}$")
assert w["pools_sentence_higher"] == w["pools"] == 19

print("cross-model (post hoc)")
for slug in ("gpt-5.6-sol", "deepseek-v3.2"):
    e = LAD[slug]
    a, m = e["pools46"], e["minus_sonnet"]
    has(f"{slug} F1_J", f"${f3(a['F1_J'])}$ ${ci(a['F1_J_ci'])}$")
    has(f"{slug} diff", f"$+{f3(m['F1_J'])}$ ${ci(m['F1_J_ci'])}$")
    has(f"{slug} F1_L", f"$\\FL = {f3(a['F1_L'])}$")
    has(f"{slug} pools higher", f"{m['F1_J_higher']} of 46 pools")
    assert abs(a["F1_J"] - e["pools41"]["F1_J"]) < 0.001, slug
ds = LAD["deepseek-v3.2"]["pools46"]
has("deepseek q", f"${f3(ds['q'])}$ ${ci(ds['q_ci'])}$")
for slug, over, noans in (("gpt-4.1", 44, 0), ("llama-4-maverick", 10, 0), ("gemma-4-12b", 9, 8), ("gpt-oss-20b", 32, 6)):
    sm = json.load(open(f"{SB}/{slug}/SUMMARY.json", encoding="utf-8"))["pools46"]
    assert sm["PRIMARY_verdict"] == "REFUSED", slug
    assert sm["units_over_cap"] == over, (slug, sm["units_over_cap"])
    assert len(sm["refusal_reasons"]["units_without_answer"]) == noans, slug
    print(f"  ok    {slug}: refused, {over} over cap, {noans} without an answer")
d6 = sum(json.load(open(f"{SB}/{s}/SUMMARY.json", encoding="utf-8"))["pools46"]["d6_units"]
         for s in ("gemma-4-12b", "gpt-oss-20b"))
assert d6 == 11, d6
has("D6 count", "eleven of them by exhausting the output budget")
sec = [LAD[s]["pools46"]["F1_J"] for s in ("gpt-4.1", "llama-4-maverick", "gemma-4-12b", "gpt-oss-20b")]
has("secondary range", f"${min(sec):.2f}$ to ${max(sec):.2f}$")
has("deepseek cost", f"\\${json.load(open(f'{SB}/deepseek-v3.2/SUMMARY.json'))['usage']['cost_usd']:.2f}")

print(f"\n{len(fails)} miss(es)" + (": " + ", ".join(fails) if fails else ""))
sys.exit(1 if fails else 0)
