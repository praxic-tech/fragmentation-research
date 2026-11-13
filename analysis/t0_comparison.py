"""
t0_comparison.py — tier 0 next to the attackers already in the master results
(RUN_DECISIONS D19). Reads only; writes results/final_t0_ext/COMPARISON.md and
COMPARISON.json.

Same statistics as the paper (§ Statistical analysis): units are pools for
Game J and documents for Game O; percentile bootstrap, 10,000 resamples, 95%
CIs, paired resampling of the same unit across attackers. q is micro
(sum C / sum K), bootstrapped as a ratio over resampled units.

Gradient and single-token cells are not in MASTER_RESULTS.csv; for those the
one-shot model's cell values are quoted from results/final/*/REPORT.txt
(no CI), and the local attackers' from results/single_token_edge/local/.

    python analysis/t0_comparison.py
"""

import csv
import glob
import json
import os
import statistics

import numpy as np

sys_stdout_utf8 = __import__("sys").stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
OUT = os.path.join("results", "final_t0_ext")
B, SEED = 10_000, 42
FAMILY = {"headlineJ": "headline", "gridJ": "grid", "identifierJ": "identifier",
          "headlineO": "headline", "gridO": "grid"}
OTHERS_J = ["One-shot Sonnet", "Memon-inspired", "Embedding (post-hoc exploratory)", "Analytic one-bucket"]
OTHERS_O = ["One-shot Sonnet", "Jaccard-Greedy", "Jaccard-MST"]


def f(x):
    return float(x) if x not in ("", None) else None


def load_t0():
    J, O = {}, {}
    for p in glob.glob("results/final_t0/*/*.jsonl") + glob.glob("results/final_t0_ext/*/*.jsonl"):
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            if "doc" in r:
                fam = FAMILY[r["game"]]
                O[(r["attacker"], fam, "headline" if fam == "headline" else r["cell"], r["doc"])] = {"tau": r["tau"]}
            else:
                fam = FAMILY.get(r["game"], r["game"])
                cell = "headline" if fam == "headline" else r["cell"]
                J[(r["attacker"], fam, cell, r["pool"])] = {
                    "F1_J": r["joint_f1"], "F1_L": r["j_linkage_f1"], "C": r["C"], "K": r["K"],
                    "base": r["joint_baseline"]}
    return J, O


def load_master():
    J, O = {}, {}
    for r in csv.DictReader(open("results/final_analysis/MASTER_RESULTS.csv", encoding="utf-8")):
        cell = "headline" if r["family"] == "headline" else r["cell"]
        if r["game"] == "J" and r["attacker"] in OTHERS_J:
            J[(r["attacker"], r["family"], cell, r["unit_id"])] = {
                "F1_J": f(r["F1_J"]), "F1_L": f(r["F1_L"]), "C": f(r["C"]) or 0.0, "K": f(r["K"]) or 0.0}
        elif r["game"] == "O" and r["attacker"] in OTHERS_O:
            O[(r["attacker"], r["family"], cell, r["unit_id"])] = {"tau": f(r["tau"])}
    return J, O


def units(table, att, fam, cell=None):
    return {k[3]: v for k, v in table.items() if k[0] == att and k[1] == fam and (cell is None or k[2] == cell)} \
        if cell is not None else {(k[2], k[3]): v for k, v in table.items() if k[0] == att and k[1] == fam}


def boot_idx(n, rng):
    return rng.integers(0, n, size=(B, n))


def ci(a):
    return float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))


def summarise_j(a_rows, ids, idx):
    F = np.array([a_rows[i]["F1_J"] for i in ids])
    L = np.array([a_rows[i]["F1_L"] for i in ids])
    C = np.array([a_rows[i]["C"] for i in ids])
    K = np.array([a_rows[i]["K"] for i in ids])
    if K.sum() == 0:                       # analytic one-bucket: q is 1/2 by definition
        q, qci = 0.5, (0.5, 0.5)
    else:
        q, qci = float(C.sum() / K.sum()), ci(C[idx].sum(1) / K[idx].sum(1))
    return {"F1_J": float(F.mean()), "F1_J_ci": ci(F[idx].mean(1)),
            "F1_L": float(L.mean()), "F1_L_ci": ci(L[idx].mean(1)),
            "q": q, "q_ci": qci, "n": len(ids)}, F


def compare_j(t0J, mJ, fam, cell=None):
    t0 = units(t0J, "T0-classical", fam, cell)
    out = {"n": len(t0)}
    ids = sorted(t0)
    idx = boot_idx(len(ids), np.random.default_rng(SEED))
    out["T0-classical"], Ft0 = summarise_j(t0, ids, idx)
    pup = units(t0J, "T0-PUP", fam, cell)
    if pup:
        out["T0-PUP"], Fp = summarise_j(pup, ids, idx)
    for att in OTHERS_J:
        o = units(mJ, att, fam, cell)
        if not o:
            continue
        assert set(o) == set(ids), (att, fam, cell, len(o), len(ids))
        # D6: a resource-bounded non-completion is not scored (not F1 = 0);
        # pair on the units this attacker completed.
        keep = [i for i in ids if o[i]["F1_J"] is not None]
        if len(keep) < len(ids):
            sub = boot_idx(len(keep), np.random.default_rng(SEED))
            out[att], Fo = summarise_j(o, keep, sub)
            out[att]["unscored_rbnc"] = [i for i in ids if i not in keep]
            Ft0k = np.array([t0[i]["F1_J"] for i in keep])
        else:
            sub, Ft0k = idx, Ft0
            out[att], Fo = summarise_j(o, ids, idx)
        d = Ft0k - Fo
        idx_d = sub
        out[att]["diff_T0c_minus_this"] = float(d.mean())
        out[att]["diff_ci"] = ci(d[idx_d].mean(1))
    return out


def compare_o(t0O, mO, fam, cell=None):
    t0 = units(t0O, "T0-classical-O", fam, cell)
    ids = sorted(t0)
    idx = boot_idx(len(ids), np.random.default_rng(SEED))
    out = {"n": len(ids)}
    T = np.array([t0[i]["tau"] for i in ids])
    out["T0-classical-O"] = {"tau": float(T.mean()), "tau_ci": ci(T[idx].mean(1))}
    p = units(t0O, "T0-PUP-O", fam, cell)
    P = np.array([p[i]["tau"] for i in ids])
    out["T0-PUP-O"] = {"tau": float(P.mean()), "tau_ci": ci(P[idx].mean(1))}
    for att in OTHERS_O:
        o = units(mO, att, fam, cell)
        assert set(o) == set(ids), (att, fam, cell)
        X = np.array([o[i]["tau"] for i in ids])
        d = T - X
        out[att] = {"tau": float(X.mean()), "tau_ci": ci(X[idx].mean(1)),
                    "diff_T0c_minus_this": float(d.mean()), "diff_ci": ci(d[idx].mean(1))}
    return out


def edge_cells(t0J):
    """Gradient and single-token cells: T0 means; Sonnet / local attackers quoted."""
    out = {}
    for fam in ("gradientJ", "singleTokenEdgeJ"):
        for cell in sorted({k[2] for k in t0J if k[1] == fam}):
            row = {}
            for att in ("T0-classical", "T0-PUP"):
                u = units(t0J, att, fam, cell)
                C, K = sum(v["C"] for v in u.values()), sum(v["K"] for v in u.values())
                row[att] = {"F1_J": statistics.fmean(v["F1_J"] for v in u.values()),
                            "F1_L": statistics.fmean(v["F1_L"] for v in u.values()), "q": C / K,
                            "base": statistics.fmean(v["base"] for v in u.values()), "n": len(u)}
            rep = open(f"results/final/{fam}/REPORT.txt", encoding="utf-8").read()
            seg = rep.split(f" CELL {cell}\n", 1)[1].split(" CELL ", 1)[0]
            import re
            row["One-shot Sonnet"] = {
                "F1_J": float(re.search(r"JOINT ordered-pair F1\s+mean ([\d.]+)", seg).group(1)),
                "F1_L": float(re.search(r"linkage F1\s+mean ([\d.]+)", seg).group(1)),
                "q": float(re.search(r"q = C/K ([\d.]+)", seg).group(1)), "source": f"results/final/{fam}/REPORT.txt"}
            if fam == "singleTokenEdgeJ":
                for name, label in (("memon-inspired", "Memon-inspired"), ("embedding", "Embedding (post-hoc exploratory)")):
                    p = f"results/single_token_edge/local/{name}__{cell}.jsonl"
                    if os.path.exists(p):
                        rs = [json.loads(l) for l in open(p, encoding="utf-8")]
                        row[label] = {"F1_J": statistics.fmean(r["F1_J"] for r in rs),
                                      "F1_L": statistics.fmean(r["F1_L"] for r in rs), "source": p}
            out[f"{fam}/{cell}"] = row
    return out


def fmt_ci(v, c):
    return f"{v:.3f} [{c[0]:.3f}, {c[1]:.3f}]"


def main():
    t0J, t0O = load_t0()
    mJ, mO = load_master()
    res = {"headlineJ": compare_j(t0J, mJ, "headline", "headline"),
           "identifierJ": compare_j(t0J, mJ, "identifier", "identifier__field"),
           "gridJ_all": compare_j(t0J, mJ, "grid"),
           "gridJ": {c: compare_j(t0J, mJ, "grid", c) for c in sorted({k[2] for k in t0J if k[1] == "grid"})},
           "headlineO": compare_o(t0O, mO, "headline", "headline"),
           "gridO_all": compare_o(t0O, mO, "grid"),
           "gridO": {c: compare_o(t0O, mO, "grid", c) for c in sorted({k[2] for k in t0O if k[1] == "grid"})},
           "edge": edge_cells(t0J)}
    json.dump(res, open(os.path.join(OUT, "COMPARISON.json"), "w", encoding="utf-8"), indent=2)

    L = ["# Tier 0 next to the existing attackers", "",
         "Means with percentile-bootstrap 95% CIs (10,000 resamples, paired by unit). "
         "q is micro (ΣC/ΣK). Diff = T0-classical minus that attacker, paired.", ""]
    for key, title in (("headlineJ", "Game J headline (46 pools)"), ("gridJ_all", "Game J grid, all 9 cells pooled (216 pools)"),
                       ("identifierJ", "Game J identifier (20 pools)")):
        r = res[key]
        L += [f"## {title}", "", "| Attacker | F1_J | F1_L | q | Diff in F1_J |", "|---|---|---|---|---|"]
        for att in ["One-shot Sonnet", "T0-classical", "Embedding (post-hoc exploratory)", "Memon-inspired",
                    "T0-PUP", "Analytic one-bucket"]:
            if att in r:
                a = r[att]
                d = fmt_ci(a["diff_T0c_minus_this"], a["diff_ci"]) if "diff_ci" in a else ""
                L.append(f"| {att} | {fmt_ci(a['F1_J'], a['F1_J_ci'])} | {fmt_ci(a['F1_L'], a['F1_L_ci'])} | "
                         f"{fmt_ci(a['q'], a['q_ci'])} | {d} |")
        L.append("")
    L += ["## Game J grid by cell (F1_J; q)", "", "| Cell | Sonnet | T0-classical | Embedding | Memon-insp. | T0-PUP | base |",
          "|---|---|---|---|---|---|---|"]
    for c, r in res["gridJ"].items():
        L.append(f"| {c} | " + " | ".join(
            f"{r[a]['F1_J']:.3f}; {r[a]['q']:.3f}" for a in ["One-shot Sonnet", "T0-classical",
                                                            "Embedding (post-hoc exploratory)", "Memon-inspired", "T0-PUP"])
                 + f" | {r['Analytic one-bucket']['F1_J']:.3f} |")
    L.append("")
    for key, title in (("headlineO", "Game O headline (100 documents)"), ("gridO_all", "Game O grid, all 9 cells pooled (270 documents)")):
        r = res[key]
        L += [f"## {title} — Kendall τ (random = 0)", "", "| Attacker | τ | Diff (T0-classical-O minus this) |", "|---|---|---|"]
        for att in ["One-shot Sonnet", "T0-classical-O", "Jaccard-Greedy", "Jaccard-MST", "T0-PUP-O"]:
            a = r[att]
            d = fmt_ci(a["diff_T0c_minus_this"], a["diff_ci"]) if "diff_ci" in a else ""
            L.append(f"| {att} | {fmt_ci(a['tau'], a['tau_ci'])} | {d} |")
        L.append("")
    L += ["## Game O grid by cell (mean τ)", "", "| Cell | Sonnet | T0-classical-O | Jaccard-Greedy | Jaccard-MST | T0-PUP-O |",
          "|---|---|---|---|---|---|"]
    for c, r in res["gridO"].items():
        L.append(f"| {c} | " + " | ".join(f"{r[a]['tau']:.3f}" for a in
                                         ["One-shot Sonnet", "T0-classical-O", "Jaccard-Greedy", "Jaccard-MST", "T0-PUP-O"]) + " |")
    L += ["", "## Gradient and single-token cells (20 pools each; Sonnet quoted from its REPORT, no CI)", "",
          "| Cell | Sonnet F1_J; q | T0-classical F1_J; q | T0-PUP F1_J; q | base |", "|---|---|---|---|---|"]
    for c, r in res["edge"].items():
        s, t, p = r["One-shot Sonnet"], r["T0-classical"], r["T0-PUP"]
        L.append(f"| {c} | {s['F1_J']:.3f}; {s['q']:.3f} | {t['F1_J']:.3f}; {t['q']:.3f} | "
                 f"{p['F1_J']:.3f}; {p['q']:.3f} | {t['base']:.3f} |")
    open(os.path.join(OUT, "COMPARISON.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
