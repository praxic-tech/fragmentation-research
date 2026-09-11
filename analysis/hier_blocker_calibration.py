"""
hier_blocker_calibration.py — choose the hierarchical attacker's k from the
BLOCKER's coverage, never from reconstruction F1. Free: no API calls.

The hierarchical attacker only ever asks about candidate pairs: each fragment's
k most TF-IDF-similar neighbours (union-kNN). Whatever the candidates miss, the
model is never asked. So k is a coverage question with an answer key, and it is
answered here on DEVELOPMENT data only: the 25 grid pools at full length under
the reference cut (data/prose = semantic x sentence), which is the headline's
shape. 0 headline documents are read.

Fragments are masked with joint_game.present exactly as in the real run, so the
top-k tie-break (a seeded hash of the masked id) behaves as it will there.

THE RULE, FIXED BEFORE ANY NUMBER IS SEEN
-----------------------------------------
Choose the SMALLEST k in {5, 10, 20} such that, over the 25 development pools,
  (1) at least 90% of records have all their fragments connected by
      same-record candidate edges, and
  (2) adjacent-pair recall is at least 80%.
If no k meets both, choose the smallest k beyond which the next k gains fewer
than 5 percentage points on both measures, and report coverage as inadequate.

    python analysis/hier_blocker_calibration.py
"""

import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

from batch_game import headline_docs, load_frame                  # noqa: E402
from hierarchical import DEFAULT_PAIRS_PER_CALL, top_k_candidates  # noqa: E402
from joint_game import build_units, present                       # noqa: E402

KS = (5, 10, 20)
CONNECTED_MIN, ADJ_RECALL_MIN, GAIN_MIN = 0.90, 0.80, 0.05
# measured on the live sample (msgbatch_01NUXxhBgUzdLnz6fyYYeuRD): 467 pairs,
# 56,993 input and 89,580 output tokens
IN_TOK_PER_PAIR, OUT_TOK_PER_PAIR = 56993 / 467, 89580 / 467
USD_PER_PAIR = IN_TOK_PER_PAIR / 1e6 * 1.0 + OUT_TOK_PER_PAIR / 1e6 * 5.0


def components(nodes, edges):
    parent = {v: v for v in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in edges:
        parent[find(a)] = find(b)
    return len({find(v) for v in nodes})


def main():
    print(__doc__.split("THE RULE, FIXED BEFORE ANY NUMBER IS SEEN")[1].split("python ")[0].strip("-\n "))
    frame = load_frame("data/pools/pools.json", "data/pools/linkage_grid.json")
    assert not ({m for _p, ms in frame for m in ms} & headline_docs())
    agg = {k: defaultdict(float) for k in KS}
    for pid, members in frame:
        _o, units, _key, truth = build_units("data/prose", 0, 7, 42, pools=[(pid, members)], o_docs=[])
        items, id_map, _shown = present(units[0][1], 42)
        labels = [lab for lab, _t in items]
        text = dict(items)
        where = {fid: (rid, i) for rid, order in truth[pid].items() for i, fid in enumerate(order)}
        loc = {lab: where[id_map[lab]] for lab in labels}
        same = {(a, b) for a in labels for b in labels if a < b and loc[a][0] == loc[b][0]}
        adj = {(a, b) for (a, b) in same if abs(loc[a][1] - loc[b][1]) == 1}
        recs = defaultdict(list)
        for lab in labels:
            recs[loc[lab][0]].append(lab)
        for k in KS:
            cand, _info = top_k_candidates(labels, text, k=k)
            cset = set(cand)
            a = agg[k]
            a["pools"] += 1
            a["fragments"] += len(labels)
            a["pairs"] += len(cset)
            a["same"] += len(same)
            a["same_hit"] += len(cset & same)
            a["adj"] += len(adj)
            a["adj_hit"] += len(cset & adj)
            within = [e for e in cset if e in same]
            for rid, frs in recs.items():
                a["records"] += 1
                a["records_connected"] += components(frs, [e for e in within if e[0] in frs and e[1] in frs]) == 1
            a["graph_components"] += components(labels, cset)
            a["pools_need_bridges"] += components(labels, cset) > len(members)

    rows = {}
    print(f"\n{'k':>3}{'pairs/pool':>11}{'pairs/frag':>11}{'same-rec recall':>16}{'adjacent recall':>16}"
          f"{'records connected':>18}{'precision':>10}{'pools need bridges':>19}{'$/pool':>8}")
    for k in KS:
        a = agg[k]
        r = {"pairs_per_pool": a["pairs"] / a["pools"], "pairs_per_fragment": a["pairs"] / a["fragments"],
             "same_record_recall": a["same_hit"] / a["same"], "adjacent_recall": a["adj_hit"] / a["adj"],
             "records_connected": a["records_connected"] / a["records"],
             "candidate_precision": a["same_hit"] / a["pairs"],
             "pools_needing_bridges": int(a["pools_need_bridges"]),
             "usd_per_pool": a["pairs"] / a["pools"] * USD_PER_PAIR,
             "batches_per_pool": a["pairs"] / a["pools"] / DEFAULT_PAIRS_PER_CALL}
        rows[k] = r
        print(f"{k:>3}{r['pairs_per_pool']:>11.0f}{r['pairs_per_fragment']:>11.2f}{r['same_record_recall']:>16.1%}"
              f"{r['adjacent_recall']:>16.1%}{r['records_connected']:>18.1%}{r['candidate_precision']:>10.1%}"
              f"{r['pools_needing_bridges']:>11}/{int(agg[k]['pools'])}{r['usd_per_pool']:>8.2f}")

    ok = [k for k in KS if rows[k]["records_connected"] >= CONNECTED_MIN and rows[k]["adjacent_recall"] >= ADJ_RECALL_MIN]
    if ok:
        chosen, why = ok[0], (f"smallest k with >= {CONNECTED_MIN:.0%} of records connected and "
                              f">= {ADJ_RECALL_MIN:.0%} adjacent recall")
        adequate = True
    else:
        chosen = KS[-1]
        for k, nxt in zip(KS, KS[1:]):
            if (rows[nxt]["records_connected"] - rows[k]["records_connected"] < GAIN_MIN
                    and rows[nxt]["adjacent_recall"] - rows[k]["adjacent_recall"] < GAIN_MIN):
                chosen = k
                break
        why, adequate = "no k meets the thresholds; smallest k past which gains are < 5 points", False
    print(f"\nCHOSEN k = {chosen}: {why}" + ("" if adequate else "  -- COVERAGE INADEQUATE AT EVERY k"))
    out = {"rule": {"records_connected_min": CONNECTED_MIN, "adjacent_recall_min": ADJ_RECALL_MIN,
                    "fallback_gain_min": GAIN_MIN, "ks": list(KS)},
           "data": "25 development pools, data/prose (semantic x sentence, full length), masked as in the run",
           "cost_basis": {"in_tok_per_pair": IN_TOK_PER_PAIR, "out_tok_per_pair": OUT_TOK_PER_PAIR,
                          "source": "msgbatch_01NUXxhBgUzdLnz6fyYYeuRD"},
           "results": {str(k): v for k, v in rows.items()}, "chosen_k": chosen, "adequate": adequate,
           "why": why, "not_used": "reconstruction F1 (never computed here)"}
    os.makedirs("results/audit", exist_ok=True)
    with open("results/audit/hier_blocker_calibration.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print("wrote results/audit/hier_blocker_calibration.json")


if __name__ == "__main__":
    main()
