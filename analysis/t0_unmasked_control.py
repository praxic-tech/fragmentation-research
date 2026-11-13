"""
t0_unmasked_control.py — masked vs unmasked, with a positive control
(RUN_DECISIONS D19 leak checks). Reads the frozen pools; writes only
results/final_t0_ext/UNMASKED_CONTROL.json. Nothing here is a paper result.

Unmasked = the worst case D1 found: raw fragment ids (prose_0007_frag_012,
which spell out the true order), sorted, and the fragments presented in file
(true) order. An attacker that uses ids, input order or a tie rule over them
scores higher unmasked than masked. One that reads only the text scores the
same.

Positive control: the Jaccard orderers under the same two conditions. They are
known to exploit exactly this (D1: MST tau 0.70 as run vs -0.02 masked), so
they show the test can detect a leak.

    python analysis/t0_unmasked_control.py
"""

import json
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis", "runs"):
    sys.path.insert(0, os.path.join(ROOT, d))
sys.stdout.reconfigure(encoding="utf-8")

import harness as H                                            # noqa: E402
import classical_t0 as T0                                      # noqa: E402
from joint_game import score_row                               # noqa: E402
from orderers import greedy_nn_order, mst_order                # noqa: E402
import final_t0_attacker as F                                  # noqa: E402
import final_t0_extended as X                                  # noqa: E402
import t0_leak_audit as A                                      # noqa: E402


def tau_of(order, ids, key, rid):
    return score_row({"game": "O", "unit": rid, "alias_map": {i: i for i in ids},
                      "raw_response": order, "repair": {}}, key, {})["tau"]


def main():
    pos, k, c, _sha = F.load_classical()
    t0o = X.make_orderers(pos)["T0-classical-O"]
    attackers = {"T0-classical-O": t0o, "Jaccard-Greedy": greedy_nn_order, "Jaccard-MST": mst_order}
    res = {"gameO": {}, "gameJ_headline": {}}

    # Game O: 370 documents (headline 100 + grid 270)
    units = list(X.o_units())
    for name, fn in attackers.items():
        masked, unmasked, identical = [], [], 0
        for _g, _c, rid, frags, key in units:
            ids = [f["fragment_id"] for f in frags]
            text = {f["fragment_id"]: f["text"] for f in frags}
            om = H._masked_shuffled_order(fn, ids, text, H.DEFAULT_SEED)      # as reported
            ou = fn(sorted(ids), text)                                       # raw ids, true order
            masked.append(tau_of(om, ids, key, rid))
            unmasked.append(tau_of(ou, ids, key, rid))
            identical += om == ou
        res["gameO"][name] = {"docs": len(units), "tau_masked": statistics.fmean(masked),
                              "tau_unmasked": statistics.fmean(unmasked),
                              "difference": statistics.fmean(unmasked) - statistics.fmean(masked),
                              "orders_identical": identical}
        print(f"O {name:<16} masked {res['gameO'][name]['tau_masked']:+.4f}  "
              f"unmasked {res['gameO'][name]['tau_unmasked']:+.4f}  identical {identical}/{len(units)}", flush=True)

    # Game J headline: T0-classical, masked as reported vs raw ids in true order
    rows_m, rows_u = [], []
    for pid, frags, n_docs, key, truth in A.headline_j_units():
        rows_m.append(A.j_score(pid, frags, n_docs, key, truth, pos, k, c,
                                __import__("joint_game")._unit_seed(frags, 42, "order"),
                                __import__("joint_game")._unit_seed(frags, 42, "labels")))
        ids = sorted(f["fragment_id"] for f in frags)                        # true order
        text = {f["fragment_id"]: f["text"] for f in frags}
        groups, _ = T0.group_classical(ids, text, n_docs, k, c, seed=42)
        groups = [T0.order_by_position(g, text, pos) for g in groups]
        rows_u.append(score_row({"game": "J", "unit": pid, "alias_map": {i: i for i in ids},
                                 "raw_response": groups, "repair": {"policy_share": 0.0}}, key, truth))
    res["gameJ_headline"]["T0-classical"] = {"masked": A.summ_j(rows_m), "unmasked": A.summ_j(rows_u)}
    print("J T0-classical masked", A.summ_j(rows_m), "\n  unmasked", A.summ_j(rows_u), flush=True)
    json.dump(res, open(os.path.join(X.OUT, "UNMASKED_CONTROL.json"), "w", encoding="utf-8"), indent=2)


if __name__ == "__main__":
    main()
