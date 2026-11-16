"""
t12_comparison.py — tiers 1 and 2 (T1-pythia160m, T2-pythia1.4b) next to tier
0, tier 3 and the attackers in the master results, on the scope D19 fixed for
them: headline Game J (46 pools) and headline Game O (100 documents). Reads
only; writes results/final_t12/COMPARISON.md and COMPARISON.json.

The statistics are tier 3's comparison code (analysis/t3_comparison.py)
unchanged, pointed at each tier in turn: units are pools / documents;
percentile bootstrap, 10,000 resamples, seed 42, 95% CIs, the same unit
resampled across attackers (paired); q micro, bootstrapped as a ratio.
Diff = this tier minus that attacker. A tier whose results do not exist is
listed as not run.

    python analysis/t12_comparison.py
"""

import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "analysis"))
import t3_comparison as T                                      # noqa: E402  (chdirs to ROOT via t0_comparison)

C = T.C
OUT = os.path.join("results", "final_t12")
TIERS = [("T1-pythia160m", os.path.join("results", "final_t1")),
         ("T2-pythia1.4b", os.path.join("results", "final_t2"))]


def main():
    t0J, t0O = C.load_t0()
    t3J, t3O = T.load_rows(glob.glob(os.path.join("results", "final_t3", "headline*", "*.jsonl")))
    mJ, mO = C.load_master()
    res, not_run = {}, []
    for name, d in TIERS:
        paths = glob.glob(os.path.join(d, "headline*", "*.jsonl"))
        if not paths:
            not_run.append(name)
            continue
        tJ, tO = T.load_rows(paths)
        others = [x for x, _ in TIERS if x != name and x not in not_run]
        T.T3J, T.T3O = name, name + "-O"                        # t3_comparison reads these at call time
        T.LOCAL_J = ["T3-crossenc", "T0-classical", "T0-PUP"]
        T.LOCAL_O = ["T3-crossenc-O", "T0-classical-O", "T0-PUP-O"]
        loc_j, loc_o = {**t0J, **t3J, **tJ}, {**t0O, **t3O, **tO}
        res[name] = {"headlineJ": T.compare_j(loc_j, mJ, "headline", "headline"),
                     "headlineO": T.compare_o(loc_o, mO, "headline", "headline")}
    os.makedirs(OUT, exist_ok=True)
    json.dump({"not_run_by_freeze": not_run, **res}, open(os.path.join(OUT, "COMPARISON.json"), "w",
                                                          encoding="utf-8"), indent=2)

    L = ["# Tiers 1 and 2 against the other attackers (RUN_DECISIONS D19)", "",
         "Headline only (the scope fixed for tiers 1 and 2). Means with 95% paired bootstrap CIs "
         "(10,000 resamples, seed 42). Diff = tier minus attacker.", ""]
    if not_run:
        L += [f"Not run by the results freeze: {', '.join(not_run)}.", ""]
    for name, r in res.items():
        j, o = r["headlineJ"], r["headlineO"]
        s = j[name]
        L += [f"## {name}", "",
              f"Game J headline ({j['n']} pools): F1_J {T.fc(s['F1_J'], s['F1_J_ci'])}, "
              f"F1_L {T.fc(s['F1_L'], s['F1_L_ci'])}, q {s['q']:.3f}, base {s['base']:.3f}, "
              f"A_J {(s['F1_J'] - s['base']) / (1 - s['base']):.3f} (of the means), exact records {s['exact_records']}", "",
              "| Attacker | F1_J | tier − attacker, F1_J | tier − attacker, F1_L |", "|---|---|---|---|"]
        for att in T.LOCAL_J + C.OTHERS_J:
            if att in j:
                a = j[att]
                L.append(f"| {att} | {T.fc(a['F1_J'], a['F1_J_ci'])} | {T.fc(a['diff_F1_J'], a['diff_F1_J_ci'])} "
                         f"| {T.fc(a['diff_F1_L'], a['diff_F1_L_ci'])} |")
        L += ["", f"Game O headline ({o['n']} documents; random τ = 0): "
              f"τ {T.fc(o[name + '-O']['tau'], o[name + '-O']['tau_ci'])}", "",
              "| Attacker | τ | tier − attacker |", "|---|---|---|"]
        for att in T.LOCAL_O + C.OTHERS_O:
            if att in o:
                a = o[att]
                L.append(f"| {att} | {T.fc(a['tau'], a['tau_ci'])} | {T.fc(a['diff_tau'], a['diff_tau_ci'])} |")
        L.append("")
    open(os.path.join(OUT, "COMPARISON.md"), "w", encoding="utf-8").write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()
