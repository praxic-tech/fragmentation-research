"""
final_o_floors.py — the free game-O floors on the frozen final O documents
(RUN_DECISIONS D12, D13; docs/adversaries.md). No API calls.

For every document of every frozen final O spec -- headline O (100) and grid O
(30 documents x 9 cells) -- from the SAME fragment files and answer keys the
one-shot model's O answers are scored against:
    Jaccard-Greedy   harness/orderers.greedy_nn_order
    Jaccard-MST      harness/orderers.mst_order
both on masked labels in the D1 seeded, shuffled presentation
(harness._masked_shuffled_order), and
    Random           the exact expectation of a uniformly random permutation:
                     tau 0, pairs in order 1/2, exact order 1/n!, mean absolute
                     displacement (n^2 - 1) / 3n. Closed form, so no draws.
The orderers' answers go through joint_game.score_row, the scorer the model's
answers go through.

Output: results/final_o_floors/<game>/<cell>.jsonl, one row per document,
including the predicted order.

    python runs/final_o_floors.py
"""

import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

import harness as H                                            # noqa: E402
from joint_game import build_units, score_row                  # noqa: E402
from orderers import greedy_nn_order, mst_order                # noqa: E402

OUT = os.path.join("results", "final_o_floors")
GAMES = [("headlineO", ["runs/final_headlineO.json"]),
         ("gridO", [f"runs/final_gridO_w{k}.json" for k in (1, 2, 3)])]
ORDERERS = [("Jaccard-Greedy", greedy_nn_order), ("Jaccard-MST", mst_order)]


def displacement(order, truth):
    pos = {f: i for i, f in enumerate(truth)}
    return [abs(i - pos[f]) for i, f in enumerate(order)]


def main():
    n_rows, same = 0, True
    for game, paths in GAMES:
        by_cell = {}
        for path in paths:
            b = json.load(open(path, encoding="utf-8"))["build"]
            for cell_dir in b["cells"]:
                o_units, _p, key, _t = build_units(cell_dir, 0, 7, 42, pools=[], o_docs=b["o_docs"])
                by_cell.setdefault(os.path.basename(os.path.normpath(cell_dir)), []).extend(
                    (rid, frags, key) for rid, frags, _n in o_units)
        for cell, units in by_cell.items():
            os.makedirs(os.path.join(OUT, game), exist_ok=True)
            with open(os.path.join(OUT, game, f"{cell}.jsonl"), "w", encoding="utf-8") as fh:
                for rid, frags, key in units:
                    ids = [f["fragment_id"] for f in frags]
                    text = {f["fragment_id"]: f["text"] for f in frags}
                    truth, n = key[rid], len(ids)
                    for name, fn in ORDERERS:
                        order = H._masked_shuffled_order(fn, ids, text, H.DEFAULT_SEED)
                        again = H._masked_shuffled_order(fn, ids, text, H.DEFAULT_SEED)
                        same &= order == again
                        r = score_row({"game": "O", "unit": rid, "alias_map": {i: i for i in ids},
                                       "raw_response": order, "repair": {}}, key, {})
                        disp = displacement(order, truth)
                        fh.write(json.dumps({
                            "game": game, "cell": cell, "doc": rid, "attacker": name, "n": n,
                            "tau": r["tau"], "pairs_correct": (1 + r["tau"]) / 2,
                            "exact_order": order == truth, "exact_fraction": r["exact_fraction"],
                            "mean_abs_disp": sum(disp) / n, "median_abs_disp": sorted(disp)[n // 2]
                            if n % 2 else (sorted(disp)[n // 2 - 1] + sorted(disp)[n // 2]) / 2,
                            "max_abs_disp": max(disp), "longest_run": r["longest_run"],
                            "run_fraction": r["run_fraction"], "reconstruction": order}) + "\n")
                        n_rows += 1
                    fh.write(json.dumps({
                        "game": game, "cell": cell, "doc": rid, "attacker": "Random", "n": n,
                        "tau": 0.0, "pairs_correct": 0.5, "exact_order": None,
                        "exact_probability": 1 / math.factorial(n), "exact_fraction": 1 / n,
                        "mean_abs_disp": (n * n - 1) / (3 * n), "median_abs_disp": None,
                        "max_abs_disp": None, "longest_run": None, "run_fraction": None,
                        "expectation": "closed form for a uniformly random permutation"}) + "\n")
                    n_rows += 1
    print(f"wrote {n_rows} rows under {OUT}/; orderers deterministic on repeat: {same}")
    if not same:
        sys.exit(1)


if __name__ == "__main__":
    main()
