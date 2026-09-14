"""
final_embedding_attacker.py — the POST-HOC EXPLORATORY EMBEDDING ADVERSARY on
the 282 final J pools (RUN_DECISIONS D14 and its addenda). No API calls; the
pinned model is loaded offline.

Exactly the pools, fragment files, truth, per-unit shown order and masking
seeds that the one-shot model and Memon-inspired use (runs/final_free_attackers.py),
scored by joint_game.score_row. Frozen settings: all-mpnet-base-v2 @ e8c3b32e,
L2 / cosine, average linkage cut to exactly N, jitter 1e-6 / seed 42, ordering
n = d = 2 with the SHA-256-seeded order_cluster, batch 64, CPU.

The first complete result is kept whatever it shows (D14 addendum 2).
Resumable: rows are appended per pool, and a restart skips pools already
written, which is safe because the attacker is deterministic.

Output: results/final_embedding/<game>/<cell>.embedding_joint.jsonl, REPORT.txt.

    HF_HUB_OFFLINE=1 python runs/final_embedding_attacker.py
"""

import json
import os
import random
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

import embedding_joint as EJ                                   # noqa: E402
from joint_game import _unit_seed, build_units, score_row      # noqa: E402

SEED = 42
OUT = os.path.join("results", "final_embedding")
GAMES = [("headlineJ", ["runs/final_headlineJ.json"]),
         ("gridJ", [f"runs/final_gridJ_w{k}.json" for k in (1, 2, 3, 4)]),
         ("identifierJ", ["runs/final_identifierJ.json"])]
KEEP = ("joint_f1", "joint_p", "joint_r", "pairs_guessed", "pairs_true", "joint_baseline",
        "joint_advantage", "j_linkage_f1", "l_precision", "l_recall", "q", "C", "K",
        "a_order", "exact_records", "exact_rate", "n_groups_true", "n_groups_guessed",
        "partition_valid", "n_dropped")


def jobs():
    for game, paths in GAMES:
        for path in paths:
            b = json.load(open(path, encoding="utf-8"))["build"]
            for cell in b["cells"]:
                for pid, members in b["pools"]:
                    yield game, cell, pid, members


def run_pool(job, model):
    game, cell, pid, members = job
    _o, units, key, truth = build_units(cell, 0, len(members), SEED, pools=[(pid, members)], o_docs=[])
    (_pid, frags, n_docs), = units
    shown = [{"fragment_id": f["fragment_id"], "text": f["text"]} for f in frags]
    random.Random(_unit_seed(frags, SEED, "order")).shuffle(shown)
    lens = [len(model.tokenizer(f["text"], add_special_tokens=True)["input_ids"]) for f in frags]
    t0 = time.perf_counter()
    groups, tel = EJ.attack(shown, n_docs, model, seed=SEED, mask_seed=_unit_seed(frags, SEED, "labels"))
    secs = time.perf_counter() - t0
    r = score_row({"game": "J", "unit": pid, "alias_map": {f["fragment_id"]: f["fragment_id"] for f in frags},
                   "raw_response": groups, "repair": {"policy_share": 0.0}}, key, truth)
    return {"game": game, "cell": os.path.basename(os.path.normpath(cell)), "pool": pid,
            "attacker": "Embedding (post-hoc exploratory)", "model": EJ.MODEL_ID, "revision": EJ.REVISION,
            "n_fragments": len(frags), "n_docs": n_docs, **{k: r.get(k) for k in KEEP},
            "largest_group": tel["largest"], "singletons": tel["singletons"],
            "all_orderings_connected": tel["all_orderings_connected"],
            "max_wordpieces": max(lens), "n_over_wordpiece_limit": sum(l > model.max_seq_length for l in lens),
            "seconds": round(secs, 2), "reconstruction": groups}


def path_for(game, cell):
    return os.path.join(OUT, game, f"{os.path.basename(os.path.normpath(cell))}.embedding_joint.jsonl")


def main():
    model = EJ.load_model()
    todo = list(jobs())
    done = set()
    for game, cell, _p, _m in todo:
        p = path_for(game, cell)
        if os.path.exists(p):
            done |= {(game, json.loads(l)["cell"], json.loads(l)["pool"]) for l in open(p, encoding="utf-8") if l.strip()}
    print(f"{len(todo)} pools; {len(done)} already written; model {EJ.MODEL_ID} @ {EJ.REVISION[:8]}", flush=True)
    t0, k = time.time(), 0
    for job in todo:
        game, cell, pid, _m = job
        if (game, os.path.basename(os.path.normpath(cell)), pid) in done:
            continue
        row = run_pool(job, model)
        os.makedirs(os.path.dirname(path_for(game, cell)), exist_ok=True)
        with open(path_for(game, cell), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        k += 1
        if k % 10 == 0:
            el = time.time() - t0
            left = len(todo) - len(done) - k
            print(f"  {k} pools this run, {el / 60:.1f} min, ~{el / k * left / 60:.0f} min left", flush=True)

    rows = [json.loads(l) for game, cell, _p, _m in {(g, c, None, None) for g, c, _x, _y in todo}
            for l in open(path_for(game, cell), encoding="utf-8") if l.strip()]
    assert len(rows) == len(todo) == 282, len(rows)

    # determinism: the first pool of each game again, in this process
    same = True
    for game, _paths in GAMES:
        j = next(t for t in todo if t[0] == game)
        first = next(r for r in rows if (r["game"], r["pool"], r["cell"]) ==
                     (game, j[2], os.path.basename(os.path.normpath(j[1]))))
        again = run_pool(j, model)
        same &= {k: v for k, v in again.items() if k != "seconds"} == {k: v for k, v in first.items() if k != "seconds"}

    lines = ["POST-HOC EXPLORATORY EMBEDDING ADVERSARY (RUN_DECISIONS D14) -- first complete result, kept as is",
             f"model {EJ.MODEL_ID} @ {EJ.REVISION}; F1_L is the primary comparison", "",
             f"{'game':<12}{'cell':<31}{'pools':>6}{'F1_L':>8}{'F1_J':>8}{'base':>8}{'q_mic':>8}{'trunc':>7}"]
    cells = {}
    for r in rows:
        cells.setdefault((r["game"], r["cell"]), []).append(r)
    for (g, c), rs in cells.items():
        C, K = sum(r["C"] for r in rs), sum(r["K"] for r in rs)
        lines.append(f"{g:<12}{c:<31}{len(rs):>6}{statistics.fmean(r['j_linkage_f1'] for r in rs):>8.4f}"
                     f"{statistics.fmean(r['joint_f1'] for r in rs):>8.4f}"
                     f"{statistics.fmean(r['joint_baseline'] for r in rs):>8.4f}"
                     f"{(C / K if K else float('nan')):>8.4f}{sum(r['n_over_wordpiece_limit'] for r in rs):>7}")
    lines += ["", f"deterministic on re-run (first pool of each game): {same}",
              f"fragments over the word-piece limit: {sum(r['n_over_wordpiece_limit'] for r in rows)}; "
              f"max word pieces {max(r['max_wordpieces'] for r in rows)}",
              f"total attack seconds {sum(r['seconds'] for r in rows):.0f}"]
    open(os.path.join(OUT, "REPORT.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    if not same:
        sys.exit(1)


if __name__ == "__main__":
    main()
