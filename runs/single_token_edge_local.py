"""
single_token_edge_local.py — the already-authorised LOCAL attackers on the frozen
single-token edge-case cells (RUN_DECISIONS D16): frozen Memon-inspired J
(n = d = 2) and the frozen MPNet embedding J (all-mpnet-base-v2 @ e8c3b32e,
offline). Same pools, same per-unit shown order and masking seeds as every J
attacker; ordinary scorer (joint_game.score_row); reconstructions stored for the
visible-text scorer. No API calls.

Neither attacker was designed for isolated single tokens: a weak token-level
result from them is NOT evidence of security (D16).

    HF_HUB_OFFLINE=1 python runs/single_token_edge_local.py
"""

import json
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

import embedding_joint as EJ                                  # noqa: E402
import memon_joint as MJ                                      # noqa: E402
from joint_game import _unit_seed, build_units, score_row     # noqa: E402

FROZEN = json.load(open("results/single_token_edge/FROZEN_DESIGN.json", encoding="utf-8"))
POOLS = [(p["pool_id"], p["members"]) for p in json.load(open(FROZEN["pools_file"], encoding="utf-8"))["pools"]]
OUT = "results/single_token_edge/local"
SEED = 42


def main():
    model = EJ.load_model()
    os.makedirs(OUT, exist_ok=True)
    for cell in FROZEN["cells"]:
        base = os.path.basename(cell)
        for name in ("memon-inspired", "embedding"):
            path = os.path.join(OUT, f"{name}__{base}.jsonl")
            with open(path, "w", encoding="utf-8") as fh:
                for pid, members in POOLS:
                    _o, units, key, truth = build_units(cell, 0, 7, SEED, pools=[(pid, members)], o_docs=[])
                    frags = units[0][1]
                    shown = [{"fragment_id": f["fragment_id"], "text": f["text"]} for f in frags]
                    random.Random(_unit_seed(frags, SEED, "order")).shuffle(shown)
                    t0 = time.perf_counter()
                    if name == "memon-inspired":
                        groups, _tel = MJ.attack(shown, 7, n=2, d=2, seed=SEED,
                                                 mask_seed=_unit_seed(frags, SEED, "labels"))
                    else:
                        groups, _tel = EJ.attack(shown, 7, model, seed=SEED,
                                                 mask_seed=_unit_seed(frags, SEED, "labels"))
                    secs = time.perf_counter() - t0
                    r = score_row({"game": "J", "unit": pid, "alias_map": {f["fragment_id"]: f["fragment_id"] for f in frags},
                                   "raw_response": groups, "repair": {"policy_share": 0.0}}, key, truth)
                    fh.write(json.dumps({"attacker": name, "cell": base, "pool": pid, "n_fragments": len(frags),
                                         "F1_J": r["joint_f1"], "F1_L": r["j_linkage_f1"], "q": r["q"],
                                         "b_J": r["joint_baseline"], "A_J": r["joint_advantage"],
                                         "seconds": round(secs, 2), "reconstruction": groups}) + "\n")
            print(f"  {name} on {base}: {len(POOLS)} pools -> {path}", flush=True)


if __name__ == "__main__":
    main()
