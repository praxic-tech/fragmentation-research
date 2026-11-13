"""
t3_comparison.py — tier 3 (T3-crossenc) next to tier 0 and the attackers in
the master results (RUN_DECISIONS D19, main comparison). Reads only; writes
results/final_t3/COMPARISON.md and COMPARISON.json.

Same statistics as analysis/t0_comparison.py and the paper: units are pools
(Game J) and documents (Game O); percentile bootstrap, 10,000 resamples, seed
42, 95% CIs, the same unit resampled across attackers (paired). q is micro
(sum C / sum K), bootstrapped as a ratio. Diff = T3 minus that attacker. D6:
an attacker's resource-bounded non-completions are not scored; the pair is
then taken over the units it completed.

Gradient and single-token cells are not in MASTER_RESULTS.csv: the one-shot
model's cell values are quoted from results/final/*/REPORT.txt (no CI); T3 vs
T0-classical there is paired and bootstrapped like the rest.

    python analysis/t3_comparison.py
"""

import glob
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "analysis"))
import t0_comparison as C                                      # noqa: E402  (chdirs to ROOT)

OUT = os.path.join("results", "final_t3")
T3J, T3O = "T3-crossenc", "T3-crossenc-O"
LOCAL_J = ["T0-classical", "T0-PUP"]
LOCAL_O = ["T0-classical-O", "T0-PUP-O"]


def load_rows(paths):
    J, O = {}, {}
    for p in paths:
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            fam = C.FAMILY.get(r["game"], r["game"])
            cell = "headline" if fam == "headline" else r["cell"]
            if "doc" in r:
                O[(r["attacker"], fam, cell, r["doc"])] = {"tau": r["tau"]}
            else:
                J[(r["attacker"], fam, cell, r["pool"])] = {
                    "F1_J": r["joint_f1"], "F1_L": r["j_linkage_f1"], "C": r["C"], "K": r["K"],
                    "base": r["joint_baseline"], "exact": r["exact_records"], "n_docs": r["n_docs"]}
    return J, O


def arr(rows, ids, k):
    return np.array([rows[i][k] for i in ids], dtype=float)


def ratio_ci(stat, out, key):
    """q is undefined in a resample whose units hold no co-grouped true pair (K = 0).
    CI over the defined resamples; the count of undefined ones is reported."""
    bad = int(np.isnan(stat).sum())
    if bad:
        out[key] = (float(np.nanpercentile(stat, 2.5)), float(np.nanpercentile(stat, 97.5)))
        out[key + "_undefined_resamples"] = bad
    else:
        out[key] = C.ci(stat)


def summ(rows, ids, idx):
    with np.errstate(invalid="ignore", divide="ignore"):       # its q CI is replaced below
        s, _ = C.summarise_j(rows, ids, idx)
    Cs, Ks = arr(rows, ids, "C"), arr(rows, ids, "K")
    s["C"], s["K"] = int(Cs.sum()), int(Ks.sum())
    if Ks.sum() > 0:
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio_ci(Cs[idx].sum(1) / Ks[idx].sum(1), s, "q_ci")
    return s


def diff_j(a, o, ids, idx):
    """T3 minus other, paired over ids: F1_J, F1_L, q (ratio difference)."""
    out = {}
    for k in ("F1_J", "F1_L"):
        d = arr(a, ids, k) - arr(o, ids, k)
        out[f"diff_{k}"], out[f"diff_{k}_ci"] = float(d.mean()), C.ci(d[idx].mean(1))
    Ca, Ka, Co, Ko = (arr(r, ids, k) for r in (a, o) for k in ("C", "K"))
    if Ko.sum() > 0:
        out["diff_q"] = float(Ca.sum() / Ka.sum() - Co.sum() / Ko.sum())
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio_ci(Ca[idx].sum(1) / Ka[idx].sum(1) - Co[idx].sum(1) / Ko[idx].sum(1), out, "diff_q_ci")
    return out


def compare_j(loc, mJ, fam, cell=None):
    a = C.units(loc, T3J, fam, cell)
    ids = sorted(a)
    idx = C.boot_idx(len(ids), np.random.default_rng(C.SEED))
    out = {"n": len(ids)}
    out[T3J] = summ(a, ids, idx)
    out[T3J]["base"] = float(arr(a, ids, "base").mean())
    out[T3J]["exact_records"] = f"{int(arr(a, ids, 'exact').sum())}/{int(arr(a, ids, 'n_docs').sum())}"
    for att, table in [(x, loc) for x in LOCAL_J] + [(x, mJ) for x in C.OTHERS_J]:
        o = C.units(table, att, fam, cell)
        if not o:
            continue
        assert set(o) == set(ids), (att, fam, cell, len(o), len(ids))
        keep = [i for i in ids if o[i]["F1_J"] is not None]
        sub = idx if len(keep) == len(ids) else C.boot_idx(len(keep), np.random.default_rng(C.SEED))
        out[att] = summ(o, keep, sub)
        if len(keep) < len(ids):
            out[att]["unscored_rbnc"] = [i for i in ids if i not in keep]
            out[att]["T3_on_completed_units"] = summ(a, keep, sub)
        out[att].update(diff_j(a, o, keep, sub))
    return out


def compare_o(loc, mO, fam, cell=None):
    a = C.units(loc, T3O, fam, cell)
    ids = sorted(a)
    idx = C.boot_idx(len(ids), np.random.default_rng(C.SEED))
    T = arr(a, ids, "tau")
    out = {"n": len(ids), T3O: {"tau": float(T.mean()), "tau_ci": C.ci(T[idx].mean(1))}}
    for att, table in [(x, loc) for x in LOCAL_O] + [(x, mO) for x in C.OTHERS_O]:
        o = C.units(table, att, fam, cell)
        assert set(o) == set(ids), (att, fam, cell)
        X = arr(o, ids, "tau")
        d = T - X
        out[att] = {"tau": float(X.mean()), "tau_ci": C.ci(X[idx].mean(1)),
                    "diff_tau": float(d.mean()), "diff_tau_ci": C.ci(d[idx].mean(1))}
    return out


def edge(loc, t0J):
    quoted = C.edge_cells(t0J)
    out = {}
    for fam in ("gradientJ", "singleTokenEdgeJ"):
        for cell in sorted({k[2] for k in loc if k[0] == T3J and k[1] == fam}):
            r = compare_j(loc, {}, fam, cell)
            r["One-shot Sonnet (quoted, no CI)"] = quoted[f"{fam}/{cell}"]["One-shot Sonnet"]
            out[f"{fam}/{cell}"] = r
    return out


def fc(v, c):
    return f"{v:.3f} [{c[0]:.3f}, {c[1]:.3f}]"


def main():
    t3J, t3O = load_rows(glob.glob(os.path.join(OUT, "*", "*.jsonl")))
    t0J, t0O = C.load_t0()
    loc_j, loc_o = {**t0J, **t3J}, {**t0O, **t3O}
    mJ, mO = C.load_master()
    res = {"headlineJ": compare_j(loc_j, mJ, "headline", "headline"),
           "identifierJ": compare_j(loc_j, mJ, "identifier", "identifier__field"),
           "gridJ_all": compare_j(loc_j, mJ, "grid"),
           "gridJ": {c: compare_j(loc_j, mJ, "grid", c) for c in sorted({k[2] for k in t3J if k[1] == "grid"})},
           "headlineO": compare_o(loc_o, mO, "headline", "headline"),
           "gridO_all": compare_o(loc_o, mO, "grid"),
           "gridO": {c: compare_o(loc_o, mO, "grid", c) for c in sorted({k[2] for k in t3O if k[1] == "grid"})},
           "edge": edge(loc_j, t0J)}
    json.dump(res, open(os.path.join(OUT, "COMPARISON.json"), "w", encoding="utf-8"), indent=2)

    order_j = ["One-shot Sonnet", T3J, "T0-classical", "Embedding (post-hoc exploratory)", "Memon-inspired",
               "T0-PUP", "Analytic one-bucket"]
    L = ["# Tier 3 next to tier 0 and the existing attackers", "",
         "Means with percentile-bootstrap 95% CIs (10,000 resamples, seed 42, paired by unit). "
         "q is micro (ΣC/ΣK). Diff = T3 minus that attacker, paired. "
         "Where an attacker has unscored resource-bounded non-completions (D6), its diff is over the units it completed.", ""]
    for key, title in (("headlineJ", "Game J headline (46 pools)"),
                       ("gridJ_all", "Game J grid, all 9 cells pooled (216 pools)"),
                       ("identifierJ", "Game J identifier (20 pools)")):
        r = res[key]
        L += [f"## {title}", "", f"T3 one-bucket base {r[T3J]['base']:.3f}; exact records {r[T3J]['exact_records']}", "",
              "| Attacker | F1_J | F1_L | q (C/K) | T3 − this, F1_J | T3 − this, q |", "|---|---|---|---|---|---|"]
        undef = []
        for att in order_j:
            if att in r:
                a = r[att]
                dj = fc(a["diff_F1_J"], a["diff_F1_J_ci"]) if "diff_F1_J" in a else ""
                dq = fc(a["diff_q"], a["diff_q_ci"]) if "diff_q" in a else ""
                note = f" ({len(a['unscored_rbnc'])} rbnc unscored)" if "unscored_rbnc" in a else ""
                ck = f" ({a['C']}/{a['K']})" if a.get("K") else ""
                L.append(f"| {att}{note} | {fc(a['F1_J'], a['F1_J_ci'])} | {fc(a['F1_L'], a['F1_L_ci'])} | "
                         f"{fc(a['q'], a['q_ci'])}{ck} | {dj} | {dq} |")
                undef += [f"{att} {k[:-len('_undefined_resamples')]}: {v:,}" for k, v in a.items()
                          if k.endswith("_undefined_resamples")]
        if undef:
            L += ["", "q undefined (K = 0) in some resamples; CI over the defined ones. Undefined resamples: "
                  + "; ".join(undef) + "."]
        L.append("")
    cols = ["One-shot Sonnet", T3J, "T0-classical", "Embedding (post-hoc exploratory)", "Memon-inspired", "T0-PUP"]
    L += ["## Game J grid by cell (F1_J; q)", "",
          "| Cell | Sonnet | T3 | T0-classical | Embedding | Memon-insp. | T0-PUP | base | T3 − Sonnet, F1_J |",
          "|---|---|---|---|---|---|---|---|---|"]
    for c, r in res["gridJ"].items():
        s = r["One-shot Sonnet"]
        L.append(f"| {c} | " + " | ".join(f"{r[a]['F1_J']:.3f}; {r[a]['q']:.3f}" for a in cols)
                 + f" | {r[T3J]['base']:.3f} | {fc(s['diff_F1_J'], s['diff_F1_J_ci'])} |")
    L.append("")
    order_o = ["One-shot Sonnet", T3O, "T0-classical-O", "Jaccard-Greedy", "Jaccard-MST", "T0-PUP-O"]
    for key, title in (("headlineO", "Game O headline (100 documents)"),
                       ("gridO_all", "Game O grid, all 9 cells pooled (270 documents)")):
        r = res[key]
        L += [f"## {title} — Kendall τ (random = 0)", "", "| Attacker | τ | T3 − this |", "|---|---|---|"]
        for att in order_o:
            a = r[att]
            d = fc(a["diff_tau"], a["diff_tau_ci"]) if "diff_tau" in a else ""
            L.append(f"| {att} | {fc(a['tau'], a['tau_ci'])} | {d} |")
        L.append("")
    L += ["## Game O grid by cell (mean τ)", "",
          "| Cell | Sonnet | T3 | T0-classical-O | Jaccard-Greedy | Jaccard-MST | T0-PUP-O | T3 − Sonnet |",
          "|---|---|---|---|---|---|---|---|"]
    for c, r in res["gridO"].items():
        s = r["One-shot Sonnet"]
        L.append(f"| {c} | " + " | ".join(f"{r[a]['tau']:.3f}" for a in order_o)
                 + f" | {fc(s['diff_tau'], s['diff_tau_ci'])} |")
    L += ["", "## Gradient and single-token cells (20 pools each; Sonnet quoted from its REPORT, no CI)", "",
          "| Cell | Sonnet F1_J; q | T3 F1_J; q | T0-classical F1_J; q | T0-PUP F1_J; q | base | T3 − T0-classical, F1_J |",
          "|---|---|---|---|---|---|---|"]
    for c, r in res["edge"].items():
        s, t, t0, p = r["One-shot Sonnet (quoted, no CI)"], r[T3J], r["T0-classical"], r["T0-PUP"]
        L.append(f"| {c} | {s['F1_J']:.3f}; {s['q']:.3f} | {t['F1_J']:.3f}; {t['q']:.3f} | "
                 f"{t0['F1_J']:.3f}; {t0['q']:.3f} | {p['F1_J']:.3f}; {p['q']:.3f} | {t['base']:.3f} | "
                 f"{fc(t0['diff_F1_J'], t0['diff_F1_J_ci'])} |")
    open(os.path.join(OUT, "COMPARISON.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
