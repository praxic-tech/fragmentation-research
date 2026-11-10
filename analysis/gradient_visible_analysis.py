"""
gradient_visible_analysis.py — the VISIBLE-TEXT metrics and permutation nulls for
the three D18 gradient arms (4, 3 and 2 words). NO API CALLS.

WHY THIS EXISTS
---------------
D16 froze the visible-text scorer as PRIMARY, because at fine granularity many
fragments share their surface text and swapping the hidden ids of two identical
tokens is invisible to any attacker yet penalised by an id-level scorer. The
D18 arms were scored only with the ordinary id-level J scorer, so the five-point
granularity series could not be drawn on the primary metric. This computes the
missing three arms.

Nothing here is new machinery: it uses harness/visible_metrics.py unchanged and
the SAME null namespace D16 froze ("single-token-edge-v1"), with the arm name as
the condition, so each arm draws its own seeded permutations under the frozen
rule. The two D16 arms are NOT recomputed -- they are read from the frozen
analysis, so this cannot perturb a frozen number.

    V_L   max over one-to-one assignments of summed multiset token overlap
    V_J   the same with token-level LCS in place of multiset overlap
    q_V   V_J / V_L, a DIAGNOSTIC RATIO ONLY -- the two are maximised over
          separate assignments, so this is not the visible analogue of q
    A_V   (V - mean null V) / (1 - mean null V)

    oracle-size null (PRIMARY)      labels permuted into the TRUE per-document
                                    fragment counts
    predicted-structure null        labels permuted into the attacker's own
                                    predicted group sizes (robustness)

    python analysis/gradient_visible_analysis.py [--perm N] [--workers N]
"""

import argparse
import csv
import json
import os
import statistics as st
import sys
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness"):
    sys.path.insert(0, os.path.join(ROOT, d))

from joint_game import _as_groups, build_units                      # noqa: E402
from visible_metrics import (PoolScorer, advantage, null_rng,       # noqa: E402
                             oracle_size_null, predicted_structure_null)

SEED = 42
N_PERM_DEFAULT = 10_000
POOLS_FILE = "data/pools/single_token_edge_pools.json"
OUT_DIR = os.path.join("results", "gradient", "visible_analysis")
ARMS = {"w4": ("results/gradient/edge__w4", "results/final/gradientJ/edge__w4"),
        "w3": ("results/gradient/edge__w3", "results/final/gradientJ/edge__w3"),
        "w2": ("results/gradient/edge__w2", "results/final/gradientJ/edge__w2")}


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def answers(pred_dir):
    return {r["unit"]: r for r in load_jsonl(os.path.join(pred_dir, "J.jsonl"))}


def one(task):
    """Everything for one (arm, pool). Runs in a worker process."""
    cond, cell_dir, pred_dir, pid, members, n_perm = task
    _o, units, _key, truth = build_units(cell_dir, 0, len(members), SEED,
                                         pools=[(pid, members)], o_docs=[])
    (_p, frags, _n), = units
    text_of = {f["fragment_id"]: f["text"] for f in frags}
    ps = PoolScorer(truth[pid], text_of)

    row = answers(pred_dir)[pid]
    amap = row["alias_map"]
    groups = [[amap[l] for l in g if l in amap] for g in _as_groups(row["raw_response"])]
    groups = [g for g in groups if g]

    v = ps.score(groups)
    o = oracle_size_null(ps, n_perm, null_rng(pid, cond, "oracle-size"))
    p = predicted_structure_null(ps, groups, n_perm, null_rng(pid, cond, "predicted-structure"))
    o_l, o_j = float(o[:, 0].mean()), float(o[:, 1].mean())
    p_l, p_j = float(p[:, 0].mean()), float(p[:, 1].mean())

    assert v["V_J"] <= v["V_L"] + 1e-12, (cond, pid, v)
    return {"condition": cond, "pool": pid, "n_fragments": len(frags),
            "V_L": v["V_L"], "V_J": v["V_J"], "q_V": v["q_V"],
            "null_oracle_V_L": o_l, "null_oracle_V_J": o_j,
            "A_VL": advantage(v["V_L"], o_l), "A_VJ": advantage(v["V_J"], o_j),
            "null_pred_V_L": p_l, "null_pred_V_J": p_j,
            "A_VL_pred": advantage(v["V_L"], p_l), "A_VJ_pred": advantage(v["V_J"], p_j)}


def main(n_perm, workers):
    pools = [(p["pool_id"], p["members"])
             for p in json.load(open(POOLS_FILE, encoding="utf-8"))["pools"]]
    assert len(pools) == 20, len(pools)

    tasks = [(cond, cell, pred, pid, m, n_perm)
             for cond, (cell, pred) in ARMS.items() for pid, m in pools]
    print(f"{len(tasks)} tasks ({len(ARMS)} arms x {len(pools)} pools), "
          f"{n_perm:,} permutations per null, {workers} workers")

    rows = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, r in enumerate(ex.map(one, tasks), 1):
            rows.append(r)
            print(f"  [{i:3d}/{len(tasks)}] {r['condition']} {r['pool']} "
                  f"V_J={r['V_J']:.4f} A_VJ={r['A_VJ']:+.4f}", flush=True)

    rows.sort(key=lambda r: (list(ARMS).index(r["condition"]), r["pool"]))
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "per_pool.csv"), "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    summary = {}
    for cond in ARMS:
        s = [r for r in rows if r["condition"] == cond]
        summary[cond] = {k: st.fmean([r[k] for r in s if r[k] is not None])
                         for k in ("V_L", "V_J", "q_V", "A_VL", "A_VJ",
                                   "null_oracle_V_L", "null_oracle_V_J",
                                   "A_VL_pred", "A_VJ_pred")}
        summary[cond]["n_pools"] = len(s)
        summary[cond]["n_fragments_mean"] = st.fmean([r["n_fragments"] for r in s])
    meta = {"what": "VISIBLE-TEXT metrics and permutation nulls for the D18 gradient arms",
            "permutations_per_pool_condition_null": n_perm,
            "null_namespace": "single-token-edge-v1 (inherited from D16, unchanged)",
            "d16_arms": "NOT recomputed; read from results/single_token_edge/analysis",
            "q_V_note": "diagnostic ratio only; V_J and V_L use separate assignments",
            "arms": summary}
    json.dump(meta, open(os.path.join(OUT_DIR, "summary.json"), "w", encoding="utf-8"), indent=1)

    print(f"\nwrote {OUT_DIR}/per_pool.csv and summary.json\n")
    print(f"{'arm':5s} {'frags':>7s} {'V_L':>7s} {'V_J':>7s} {'nullV_J':>8s} "
          f"{'A_VL':>8s} {'A_VJ':>8s}")
    for cond, s in summary.items():
        print(f"{cond:5s} {s['n_fragments_mean']:7.1f} {s['V_L']:7.4f} {s['V_J']:7.4f} "
              f"{s['null_oracle_V_J']:8.4f} {s['A_VL']:+8.4f} {s['A_VJ']:+8.4f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--perm", type=int, default=N_PERM_DEFAULT)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    main(a.perm, a.workers)
