"""
cross_model_ladder.py — every attacker and every cross-model sweep model on the
46 headline Game J pools, on one footing. Reads only; no API calls.

Writes results/final_analysis/TABLES/table_B3_headline_ladder.csv and
results/final_analysis/HEADLINE_LADDER.json.

Rows
  prespecified attackers   Analytic one-bucket, Memon-inspired, One-shot Sonnet
                           (MASTER_RESULTS.csv); T0-classical, T0-PUP (D19
                           tier 0); T1-pythia160m, T2-pythia1.4b (D19 tiers 1
                           and 2); T3-crossenc (D19 tier 3)
  post hoc                 Embedding (D14), and the Sonnet-dependence sweep
                           models (experiments/cross_model_sandbox), each
                           scored here from its raw rows with the frozen
                           joint_game.score_row and the headline answer key

Same statistics as the paper: units are pools; means with 95% percentile
bootstrap CIs (10,000 resamples, seed 42), the same resample of pools for every
attacker (paired); q is micro (sum C / sum K); A_J = (F1_J - b_J) / (1 - b_J)
per pool. A sweep model's verdict is the one its sandbox SUMMARY.json records
under the preregistered rule; a refused model's numbers are over the units it
answered and are secondary. Diff = this attacker minus one-shot Sonnet, paired
over the pools both answered.

    python analysis/cross_model_ladder.py
"""

import csv
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))
sys.stdout.reconfigure(encoding="utf-8")

from joint_game import _no_model_answer, build_units, score_row   # noqa: E402

B, SEED = 10_000, 42
SPEC = os.path.join("runs", "final_headlineJ.json")
SB = os.path.join("experiments", "cross_model_sandbox", "results")
EPUB_2025_POOLS = {"pool_009", "pool_011", "pool_041", "pool_056", "pool_062"}
OUT_CSV = os.path.join("results", "final_analysis", "TABLES", "table_B3_headline_ladder.csv")
OUT_JSON = os.path.join("results", "final_analysis", "HEADLINE_LADDER.json")
SONNET = "One-shot Sonnet"

# label, lab, kind; order = table order
MASTER = [("Analytic one-bucket", "--", "baseline"),
          ("Memon-inspired", "--", "attacker"),
          ("Embedding (post-hoc exploratory)", "--", "attacker, post hoc"),
          (SONNET, "Anthropic", "attacker")]
LOCAL = [("T0-PUP", os.path.join("results", "final_t0", "headlineJ", "prose.T0-PUP.jsonl")),
         ("T0-classical", os.path.join("results", "final_t0", "headlineJ", "prose.T0-classical.jsonl")),
         ("T1-pythia160m", os.path.join("results", "final_t1", "headlineJ", "prose.T1-pythia160m.jsonl")),
         ("T2-pythia1.4b", os.path.join("results", "final_t2", "headlineJ", "prose.T2-pythia1.4b.jsonl")),
         ("T3-crossenc", os.path.join("results", "final_t3", "headlineJ", "prose.T3-crossenc.jsonl"))]
SWEEP = [("gpt-5.6-sol", "OpenAI"), ("deepseek-v3.2", "DeepSeek"), ("gpt-4.1", "OpenAI"),
         ("llama-4-maverick", "Meta"), ("gemma-4-12b", "Google"), ("gpt-oss-20b", "OpenAI")]


def fnum(x):
    return float(x) if x not in ("", None) else None


def load_master():
    out = {}
    for r in csv.DictReader(open(os.path.join("results", "final_analysis", "MASTER_RESULTS.csv"),
                                 encoding="utf-8")):
        if r["family"] != "headline" or r["game"] != "J" or r["completion"] != "completed":
            continue
        out.setdefault(r["attacker"], {})[r["unit_id"]] = {
            "F1_J": fnum(r["F1_J"]), "F1_L": fnum(r["F1_L"]), "C": fnum(r.get("C")) or 0.0,
            "K": fnum(r.get("K")) or 0.0, "b_J": fnum(r["b_J"]),
            "exact": fnum(r.get("exact_records")) or 0.0}
    return out


def load_local(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        out[r["pool"]] = {"F1_J": r["joint_f1"], "F1_L": r["j_linkage_f1"], "C": r["C"], "K": r["K"],
                          "b_J": r["joint_baseline"], "exact": r["exact_records"]}
    return out


def headline_keys():
    b = json.load(open(SPEC, encoding="utf-8"))["build"]
    (cell_dir,) = b["cells"]
    keys = {}
    for pid, members in b["pools"]:
        _o, _u, key, truth = build_units(cell_dir, 0, len(members), SEED,
                                         pools=[(pid, members)], o_docs=[])
        keys[pid] = (key, truth)
    return keys


def load_sweep(slug, keys):
    d = os.path.join(SB, slug, "final_headlineJ", "prose")
    p = os.path.join(d, "J.jsonl")
    if not os.path.exists(p):
        return None, None
    rb = os.path.join(d, "J.rbnc.jsonl")
    rbnc = {json.loads(l)["unit"] for l in open(rb, encoding="utf-8") if l.strip()} \
        if os.path.exists(rb) else set()
    out = {}
    for line in open(p, encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        if r["unit"] in rbnc or _no_model_answer(r):
            continue
        key, truth = keys[r["unit"]]
        s = score_row(r, key, truth)
        out[r["unit"]] = {"F1_J": s["joint_f1"], "F1_L": s["j_linkage_f1"], "C": s["C"], "K": s["K"],
                          "b_J": s["joint_baseline"], "exact": s["exact_records"]}
    summ = json.load(open(os.path.join(SB, slug, "SUMMARY.json"), encoding="utf-8"))
    return out, summ


def ci(a):
    a = a[~np.isnan(a)]
    return [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))]


def summarise(rows, pools, all_pools, idx_all):
    """Means and CIs over `pools`, resampling the same pool draws as everyone else
    when `pools` is the full set (paired), otherwise with its own draws."""
    ids = sorted(pools)
    idx = idx_all if ids == all_pools else np.random.default_rng(SEED).integers(0, len(ids), (B, len(ids)))
    g = lambda k: np.array([rows[i][k] for i in ids], dtype=float)
    F, L, C, K, b = g("F1_J"), g("F1_L"), g("C"), g("K"), g("b_J")
    A = (F - b) / (1 - b)
    out = {"n": len(ids),
           "F1_J": float(F.mean()), "F1_J_ci": ci(F[idx].mean(1)),
           "F1_L": float(L.mean()), "F1_L_ci": ci(L[idx].mean(1)),
           "A_J": float(A.mean()), "A_J_ci": ci(A[idx].mean(1)),
           "exact": int(g("exact").sum())}
    if K.sum() > 0:
        with np.errstate(invalid="ignore", divide="ignore"):
            out["q"], out["q_ci"] = float(C.sum() / K.sum()), ci(C[idx].sum(1) / K[idx].sum(1))
    else:
        out["q"], out["q_ci"] = 0.5, [0.5, 0.5]
    return out


def diff_vs(rows, ref, pools):
    ids = sorted(set(pools) & set(ref))
    idx = np.random.default_rng(SEED).integers(0, len(ids), (B, len(ids)))
    out = {"n": len(ids)}
    for k in ("F1_J", "F1_L"):
        d = np.array([rows[i][k] - ref[i][k] for i in ids])
        out[k] = float(d.mean())
        out[k + "_ci"] = ci(d[idx].mean(1))
        out[k + "_higher"] = int((d > 0).sum())
    return out


def main():
    master = load_master()
    keys = headline_keys()
    all_pools = sorted(keys)
    assert len(all_pools) == 46
    idx_all = np.random.default_rng(SEED).integers(0, 46, (B, 46))
    sonnet = master[SONNET]
    entries = []

    def add(label, lab, kind, rows, verdict=None, summ=None):
        e = {"attacker": label, "lab": lab, "kind": kind, "verdict": verdict,
             "answered": len(rows), "pools46": summarise(rows, sorted(rows), all_pools, idx_all)}
        p41 = sorted(set(rows) - EPUB_2025_POOLS)
        e["pools41"] = summarise(rows, p41, None, None)
        if label != SONNET and kind != "baseline":
            e["minus_sonnet"] = diff_vs(rows, sonnet, sorted(rows))
        if summ:
            u = summ.get("usage", {})
            e["cost_usd"] = u.get("cost_usd")
            e["verdict41"] = summ["pools41"]["PRIMARY_verdict"]
            for k in ("units_over_cap", "d6_units", "invalid_after_repair", "mean_policy_share"):
                e[k] = summ["pools46"].get(k)
            e["units_without_answer"] = len(summ["pools46"]["refusal_reasons"]["units_without_answer"])
        entries.append(e)

    for label, lab, kind in MASTER:
        add(label, lab, kind, master[label], verdict="PASS" if label == SONNET else None)
    for label, path in LOCAL:
        if not os.path.exists(path):              # a D19 tier not finished by the freeze
            print(f"NOT RUN: {label} ({path} missing)")
            continue
        add(label, "--", "attacker", load_local(path))
    missing = []
    for slug, lab in SWEEP:
        rows, summ = load_sweep(slug, keys)
        if rows is None:
            missing.append(slug)
            continue
        add(slug, lab, "sweep model, post hoc", rows, verdict=summ["pools46"]["PRIMARY_verdict"], summ=summ)

    # reproduction check: Sonnet's sweep reference scoring must match the master rows
    chk = json.load(open(os.path.join(SB, "claude-sonnet-5", "SUMMARY.json"), encoding="utf-8"))
    s46 = next(e for e in entries if e["attacker"] == SONNET)["pools46"]
    ref = chk["pools46"]["PRIMARY_means"]
    assert abs(ref["F1_J"] - s46["F1_J"]) < 1e-9 and abs(ref["F1_L"] - s46["F1_L"]) < 1e-9, (ref, s46)

    res = {"pools": 46, "bootstrap": {"resamples": B, "seed": SEED, "ci": "95% percentile"},
           "epub_2025_pools_dropped_in_41": sorted(EPUB_2025_POOLS),
           "sweep_models_not_found": missing, "rows": entries}
    json.dump(res, open(OUT_JSON, "w", encoding="utf-8"), indent=1)

    cols = ["attacker", "lab", "kind", "verdict", "answered"]
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols + ["F1_J", "F1_J_lo", "F1_J_hi", "F1_L", "F1_L_lo", "F1_L_hi", "q", "q_lo", "q_hi",
                           "A_J", "A_J_lo", "A_J_hi", "exact", "F1_J_41", "F1_L_41", "q_41", "verdict41",
                           "dF1_J_vs_sonnet", "dF1_J_lo", "dF1_J_hi", "cost_usd"])
        for e in entries:
            a, b = e["pools46"], e["pools41"]
            m = e.get("minus_sonnet", {})
            w.writerow([e[c] for c in cols] +
                       [a["F1_J"], *a["F1_J_ci"], a["F1_L"], *a["F1_L_ci"], a["q"], *a["q_ci"],
                        a["A_J"], *a["A_J_ci"], a["exact"], b["F1_J"], b["F1_L"], b["q"], e.get("verdict41"),
                        m.get("F1_J"), *(m.get("F1_J_ci") or [None, None]), e.get("cost_usd")])

    print(f"{'attacker':<34}{'verdict':>9}{'n':>4}{'F1_J':>8}{'95% CI':>17}{'F1_L':>8}{'q':>8}{'A_J':>8}"
          f"{'d vs Sonnet':>13}")
    for e in entries:
        a = e["pools46"]
        d = e.get("minus_sonnet", {}).get("F1_J")
        print(f"{e['attacker']:<34}{(e['verdict'] or ''):>9}{a['n']:>4}{a['F1_J']:>8.4f}"
              f"  [{a['F1_J_ci'][0]:.3f}, {a['F1_J_ci'][1]:.3f}]{a['F1_L']:>8.4f}{a['q']:>8.4f}"
              f"{a['A_J']:>8.4f}{'' if d is None else f'{d:+13.4f}'}")
    if missing:
        print("sweep rows not found (not yet pulled?):", ", ".join(missing))


if __name__ == "__main__":
    main()
