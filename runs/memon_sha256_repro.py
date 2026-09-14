"""
memon_sha256_repro.py — before/after report for the SHA-256 seed fix in
order_from_sim (RUN_DECISIONS D13). No API calls.

  before  results/audit/memon_joint_pre_sha256/   (run 2026-09-13 with hash())
  after   results/final_free/                     (SHA-256 seed; canonical)

The pre-fix run stored scores and telemetry but not the predicted
reconstructions, so "reconstruction changed" is judged from every stored
count and score; the post-fix runs store reconstructions and are compared
output for output across two Python hash seeds.

    python runs/memon_sha256_repro.py [<second post-fix run dir>]
"""

import glob
import json
import os
import statistics as st
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
BEFORE, AFTER = "results/audit/memon_joint_pre_sha256", "results/final_free"
OUT = "results/audit/memon_sha256_reproducibility"
COUNTS = ("C", "K", "pairs_guessed", "pairs_true", "exact_records", "n_groups_guessed", "largest_group",
          "singletons", "zero_weight_pairs", "score_pair_calls", "arbitrary_pairs", "n_dropped")
SCORES = ("joint_f1", "joint_p", "joint_r", "j_linkage_f1", "l_precision", "l_recall", "q",
          "joint_advantage", "context_coverage")


def load(root):
    rows = {}
    for p in glob.glob(os.path.join(root, "*", "*.memon_joint.jsonl")):
        for l in open(p, encoding="utf-8"):
            if l.strip():
                r = json.loads(l)
                rows[(r["game"], r["cell"], r["pool"])] = r
    return rows


def agg(rows):
    out = {}
    for key in sorted({(g, c) for g, c, _p in rows}):
        rs = [r for k, r in rows.items() if k[:2] == key]
        out[f"{key[0]}/{key[1]}"] = {
            "pools": len(rs), "F1_J_mean": st.fmean(r["joint_f1"] for r in rs),
            "F1_L_mean": st.fmean(r["j_linkage_f1"] for r in rs),
            "q_micro": sum(r["C"] for r in rs) / sum(r["K"] for r in rs),
            "A_J_mean": st.fmean(r["joint_advantage"] for r in rs)}
    return out


def main():
    b, a = load(BEFORE), load(AFTER)
    assert set(b) == set(a) and len(a) == 282, (len(b), len(a))
    changed = {k: [f for f in COUNTS + SCORES if b[k].get(f) != a[k].get(f)] for k in a}
    n_any = sum(bool(v) for v in changed.values())
    n_f = {f: sum(f in v for v in changed.values()) for f in ("joint_f1", "j_linkage_f1", "q")}
    max_diff = max((abs((a[k][f] or 0) - (b[k][f] or 0)) for k in a for f in SCORES
                    if a[k].get(f) is not None or b[k].get(f) is not None), default=0.0)
    cross = None
    if len(sys.argv) > 1:
        c = load(sys.argv[1])
        strip = lambda r: {k: v for k, v in r.items() if k != "seconds"}
        cross = {"pools": len(c), "differ": sum(strip(c[k]) != strip(a[k]) for k in a)}
    rep = {"what": "before/after the SHA-256 seed fix in order_from_sim (RUN_DECISIONS D13)",
           "before": BEFORE, "after": AFTER, "pools": len(a),
           "pools_with_any_changed_count_or_score": n_any,
           "pools_F1_J_changed": n_f["joint_f1"], "pools_F1_L_changed": n_f["j_linkage_f1"],
           "pools_q_changed": n_f["q"], "max_abs_score_difference": max_diff,
           "reconstruction_changed": ("not directly observable for the pre-fix run (it stored no "
                                      "reconstructions); judged from every stored count and score: "
                                      f"{n_any} of {len(a)} pools differ in any of them"),
           "cross_process_after_fix": cross,
           "aggregates_before": agg(b), "aggregates_after": agg(a),
           "canonical": ("post-fix run (identical to pre-fix)" if n_any == 0 else
                         "post-fix run; the pre-fix run is kept only in the audit trail and the numerical "
                         "effect is reported")}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(rep, open(OUT + ".json", "w", encoding="utf-8"), indent=2)
    lines = ["# Memon-inspired: before / after the SHA-256 seed fix (RUN_DECISIONS D13)", "",
             f"- pools compared: {len(a)} (46 headline, 216 grid, 20 identifier)",
             f"- pools whose predicted reconstruction changed: {rep['reconstruction_changed']}",
             f"- pools whose F1_J changed: {n_f['joint_f1']}",
             f"- pools whose F1_L changed: {n_f['j_linkage_f1']}",
             f"- pools whose q changed: {n_f['q']}",
             f"- maximum absolute score difference: {max_diff:.3g}"]
    if cross:
        lines.append(f"- post-fix runs under PYTHONHASHSEED 0 vs 987: {cross['differ']} of {cross['pools']} pools "
                     "differ (reconstructions and every score compared)")
    lines += ["", "| condition | pools | F1_J before | F1_J after | F1_L before | F1_L after | "
                  "q_micro before | q_micro after |", "|---|---|---|---|---|---|---|---|"]
    for k in rep["aggregates_after"]:
        x, y = rep["aggregates_before"][k], rep["aggregates_after"][k]
        lines.append(f"| {k} | {y['pools']} | {x['F1_J_mean']:.6f} | {y['F1_J_mean']:.6f} | "
                     f"{x['F1_L_mean']:.6f} | {y['F1_L_mean']:.6f} | {x['q_micro']:.6f} | {y['q_micro']:.6f} |")
    lines += ["", f"Canonical result: {rep['canonical']}."]
    open(OUT + ".md", "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines[:9]))


if __name__ == "__main__":
    main()
