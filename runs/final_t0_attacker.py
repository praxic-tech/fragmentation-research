"""
final_t0_attacker.py — tier 0 attackers on the final J pools (RUN_DECISIONS D19).
Main comparisons. No API calls.

Exactly the pools, fragment files, truth, per-unit shown order and masking
seeds that the one-shot model, Memon-inspired and the embedding attacker use
(runs/final_free_attackers.py, runs/final_embedding_attacker.py), scored by
joint_game.score_row.

    T0-PUP        all 282 pools (headline, grid, identifier), no training
    T0-classical  the 46 headline pools, with the values chosen in
                  results/final_t0/dev_tuning.json (disjoint data only) and the
                  position model whose SHA-256 is recorded there

The first complete result is kept. Resumable: rows are appended per pool and a
restart skips pools already written (the attackers are deterministic).

    python runs/final_t0_attacker.py
"""

import json
import os
import pickle
import random
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

import classical_t0 as T0                                      # noqa: E402
from joint_game import _unit_seed, build_units, score_row      # noqa: E402

SEED = 42
OUT = os.path.join("results", "final_t0")
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
                    for att in ("T0-PUP", "T0-classical"):
                        if att == "T0-classical" and game != "headlineJ":
                            continue
                        yield att, game, cell, pid, members


def load_classical():
    tun = json.load(open(os.path.join(OUT, "dev_tuning.json"), encoding="utf-8"))
    mp = os.path.join(OUT, "position_model.pkl")
    sha = T0.file_sha256(mp)
    if sha != tun["position_model_sha256"]:
        raise SystemExit(f"position model SHA-256 {sha} does not match dev_tuning.json")
    blob = pickle.load(open(mp, "rb"))
    pos = T0.PositionModel(blob["alpha"])
    pos.vec, pos.reg = blob["vec"], blob["reg"]
    return pos, tun["chosen"]["k"], tun["chosen"]["c"], sha


def run_pool(job, cls):
    att, game, cell, pid, members = job
    _o, units, key, truth = build_units(cell, 0, len(members), SEED, pools=[(pid, members)], o_docs=[])
    (_pid, frags, n_docs), = units
    shown = [{"fragment_id": f["fragment_id"], "text": f["text"]} for f in frags]
    random.Random(_unit_seed(frags, SEED, "order")).shuffle(shown)
    ms = _unit_seed(frags, SEED, "labels")
    t0 = time.perf_counter()
    if att == "T0-PUP":
        groups, tel = T0.attack_pup(shown, n_docs, seed=SEED, mask_seed=ms)
    else:
        pos, k, c, _sha = cls
        groups, tel = T0.attack_classical(shown, n_docs, pos, k, c, seed=SEED, mask_seed=ms)
    secs = time.perf_counter() - t0
    r = score_row({"game": "J", "unit": pid, "alias_map": {f["fragment_id"]: f["fragment_id"] for f in frags},
                   "raw_response": groups, "repair": {"policy_share": 0.0}}, key, truth)
    return {"game": game, "cell": os.path.basename(os.path.normpath(cell)), "pool": pid, "attacker": att,
            "n_fragments": len(frags), "n_docs": n_docs, **{k: r.get(k) for k in KEEP},
            "telemetry": tel, "seconds": round(secs, 2), "reconstruction": groups}


def path_for(att, game, cell):
    return os.path.join(OUT, game, f"{os.path.basename(os.path.normpath(cell))}.{att}.jsonl")


def main():
    cls = load_classical()
    todo = list(jobs())
    done = set()
    for att, game, cell, _p, _m in todo:
        p = path_for(att, game, cell)
        if os.path.exists(p):
            done |= {(att, game, json.loads(l)["cell"], json.loads(l)["pool"])
                     for l in open(p, encoding="utf-8") if l.strip()}
    print(f"{len(todo)} attacker-pools; {len(done)} already written; "
          f"T0-classical k={cls[1]} c={cls[2]} alpha={cls[0].alpha} model {cls[3][:12]}", flush=True)
    t0, n = time.time(), 0
    for job in todo:
        att, game, cell, pid, _m = job
        if (att, game, os.path.basename(os.path.normpath(cell)), pid) in done:
            continue
        row = run_pool(job, cls)
        os.makedirs(os.path.dirname(path_for(att, game, cell)), exist_ok=True)
        with open(path_for(att, game, cell), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        n += 1
        if n % 20 == 0:
            print(f"  {n} done, {(time.time() - t0) / 60:.1f} min", flush=True)

    files = sorted({path_for(a, g, c) for a, g, c, _p, _m in todo})
    rows = [json.loads(l) for p in files for l in open(p, encoding="utf-8") if l.strip()]
    assert len(rows) == len(todo) == 282 + 46, len(rows)

    same = True
    for att in ("T0-PUP", "T0-classical"):
        for game, _paths in GAMES:
            j = next((t for t in todo if t[0] == att and t[1] == game), None)
            if j is None:
                continue
            first = next(r for r in rows if (r["attacker"], r["game"], r["pool"], r["cell"]) ==
                         (att, game, j[3], os.path.basename(os.path.normpath(j[2]))))
            again = run_pool(j, cls)
            same &= ({k: v for k, v in again.items() if k != "seconds"} ==
                     {k: v for k, v in first.items() if k != "seconds"})

    lines = ["TIER 0 ATTACKERS (RUN_DECISIONS D19) -- main comparisons; first complete result, kept as is",
             f"T0-classical: k={cls[1]} c={cls[2]} alpha={cls[0].alpha}, position model SHA-256 {cls[3]}", "",
             f"{'attacker':<14}{'game':<12}{'cell':<31}{'pools':>6}{'F1_J':>8}{'base':>8}"
             f"{'F1_L':>8}{'q_mic':>8}{'exact':>8}"]
    cells = {}
    for r in rows:
        cells.setdefault((r["attacker"], r["game"], r["cell"]), []).append(r)
    for (a, g, c), rs in sorted(cells.items()):
        C, K = sum(r["C"] for r in rs), sum(r["K"] for r in rs)
        lines.append(f"{a:<14}{g:<12}{c:<31}{len(rs):>6}"
                     f"{statistics.fmean(r['joint_f1'] for r in rs):>8.4f}"
                     f"{statistics.fmean(r['joint_baseline'] for r in rs):>8.4f}"
                     f"{statistics.fmean(r['j_linkage_f1'] for r in rs):>8.4f}"
                     f"{(C / K if K else float('nan')):>8.4f}"
                     f"{sum(r['exact_records'] for r in rs):>4}/{sum(r['n_docs'] for r in rs)}")
    lines += ["", f"deterministic on re-run (first pool of each attacker x game): {same}",
              f"total attack seconds {sum(r['seconds'] for r in rows):.0f}"]
    open(os.path.join(OUT, "REPORT.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    if not same:
        sys.exit(1)


if __name__ == "__main__":
    main()
