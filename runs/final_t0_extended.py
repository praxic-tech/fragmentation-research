"""
final_t0_extended.py — tier 0 on every condition the one-shot model ran
(RUN_DECISIONS D19 addendum "tier 0 extended"). No API calls.

Settings are the frozen ones from results/final_t0/dev_tuning.json; nothing is
re-tuned. results/final_t0/ (the headline run) is read, never written.

Game J  T0-classical: grid, identifier, gradient, single-token edge
        T0-PUP:       gradient, single-token edge
        Same pools / shown order / masking seeds as runs/final_t0_attacker.py.
Game O  T0-classical-O and T0-PUP-O on headline O and grid O, in the Jaccard
        floors' presentation (harness._masked_shuffled_order, seed 42).

Output: results/final_t0_ext/<game>/<cell>.<attacker>.jsonl and REPORT.txt.

    python runs/final_t0_extended.py
"""

import json
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

import harness as H                                            # noqa: E402
import classical_t0 as T0                                      # noqa: E402
from joint_game import build_units, score_row                  # noqa: E402
from memon import build_model, build_vocab                     # noqa: E402

import final_t0_attacker as F                                  # noqa: E402  (run_pool, load_classical)

OUT = os.path.join("results", "final_t0_ext")
J_GAMES = [("gridJ", [f"runs/final_gridJ_w{k}.json" for k in (1, 2, 3, 4)], ("T0-classical",)),
           ("identifierJ", ["runs/final_identifierJ.json"], ("T0-classical",)),
           ("gradientJ", ["runs/gradient_J.json"], ("T0-PUP", "T0-classical")),
           ("singleTokenEdgeJ", ["runs/single_token_edge_J.json"], ("T0-PUP", "T0-classical"))]
O_GAMES = [("headlineO", ["runs/final_headlineO.json"]),
           ("gridO", [f"runs/final_gridO_w{k}.json" for k in (1, 2, 3)])]
O_ATTACKERS = ("T0-classical-O", "T0-PUP-O")


def cell_name(cell):
    return os.path.basename(os.path.normpath(cell))


def j_jobs():
    for game, paths, atts in J_GAMES:
        for path in paths:
            b = json.load(open(path, encoding="utf-8"))["build"]
            for cell in b["cells"]:
                for pid, members in b["pools"]:
                    for att in atts:
                        yield att, game, cell, pid, members


def o_units():
    for game, paths in O_GAMES:
        for path in paths:
            b = json.load(open(path, encoding="utf-8"))["build"]
            for cell in b["cells"]:
                o, _p, key, _t = build_units(cell, 0, 7, 42, pools=[], o_docs=b["o_docs"])
                for rid, frags, _n in o:
                    yield game, cell, rid, frags, key


def make_orderers(pos):
    def classical_o(shown, ltext):
        return T0.order_by_position(shown, ltext, pos)
    classical_o.__name__ = "t0_classical_o"

    def pup_o(shown, ltext):
        ids = sorted(shown)                       # masked labels: neutral index order
        frs = [{"fragment_id": i, "text": ltext[i]} for i in ids]
        S = T0.boundary_matrix(ids, ltext, build_model(frs, T0.N_GRAM), build_vocab(frs))
        (path,) = T0.pup(S, 1)
        return [ids[i] for i in path]
    pup_o.__name__ = "t0_pup_o"
    return {"T0-classical-O": classical_o, "T0-PUP-O": pup_o}


def displacement(order, truth):
    pos = {f: i for i, f in enumerate(truth)}
    return [abs(i - pos[f]) for i, f in enumerate(order)]


def o_row(att, fn, game, cell, rid, frags, key):
    ids = [f["fragment_id"] for f in frags]
    text = {f["fragment_id"]: f["text"] for f in frags}
    t0 = time.perf_counter()
    order = H._masked_shuffled_order(fn, ids, text, H.DEFAULT_SEED)
    secs = time.perf_counter() - t0
    assert sorted(order) == sorted(ids), f"{att} dropped or duplicated ids in {rid}"
    r = score_row({"game": "O", "unit": rid, "alias_map": {i: i for i in ids},
                   "raw_response": order, "repair": {}}, key, {})
    truth, n = key[rid], len(ids)
    disp = sorted(displacement(order, truth))
    return {"game": game, "cell": cell_name(cell), "doc": rid, "attacker": att, "n": n,
            "tau": r["tau"], "pairs_correct": (1 + r["tau"]) / 2, "exact_order": order == truth,
            "exact_fraction": r["exact_fraction"], "mean_abs_disp": sum(disp) / n,
            "median_abs_disp": disp[n // 2] if n % 2 else (disp[n // 2 - 1] + disp[n // 2]) / 2,
            "max_abs_disp": disp[-1], "longest_run": r["longest_run"], "run_fraction": r["run_fraction"],
            "seconds": round(secs, 3), "reconstruction": order}


def write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def main():
    if os.path.exists(os.path.join(OUT, "REPORT.txt")):
        raise SystemExit(f"{OUT}/REPORT.txt exists: the first complete result is kept; nothing re-run.")
    cls = F.load_classical()
    pos = cls[0]
    print(f"frozen T0-classical k={cls[1]} c={cls[2]} alpha={pos.alpha} model {cls[3][:12]}", flush=True)
    t_start = time.time()

    jrows = {}
    jl = list(j_jobs())
    for i, job in enumerate(jl, 1):
        row = F.run_pool(job, cls)
        jrows.setdefault((row["attacker"], row["game"], row["cell"]), []).append(row)
        if i % 50 == 0:
            print(f"  J {i}/{len(jl)}  {(time.time() - t_start) / 60:.1f} min", flush=True)
    for (a, g, c), rs in jrows.items():
        write(os.path.join(OUT, g, f"{c}.{a}.jsonl"), rs)

    orderers = make_orderers(pos)
    orows = {}
    ou = list(o_units())
    for game, cell, rid, frags, key in ou:
        for att in O_ATTACKERS:
            row = o_row(att, orderers[att], game, cell, rid, frags, key)
            orows.setdefault((att, game, row["cell"]), []).append(row)
    for (a, g, c), rs in orows.items():
        write(os.path.join(OUT, g, f"{c}.{a}.jsonl"), rs)
    print(f"  O {len(ou)} documents x {len(O_ATTACKERS)} attackers done", flush=True)

    # determinism: first unit of each attacker x game, run again
    same = True
    for (a, g, c), rs in sorted(jrows.items()):
        if c != sorted(k[2] for k in jrows if k[:2] == (a, g))[0]:
            continue
        job = next(j for j in jl if j[0] == a and j[1] == g and cell_name(j[2]) == c and j[3] == rs[0]["pool"])
        again = F.run_pool(job, cls)
        same &= {k: v for k, v in again.items() if k != "seconds"} == {k: v for k, v in rs[0].items() if k != "seconds"}
    for game, cell, rid, frags, key in [next(u for u in ou if u[0] == g) for g, _ in O_GAMES]:
        for att in O_ATTACKERS:
            first = next(r for r in orows[(att, game, cell_name(cell))] if r["doc"] == rid)
            again = o_row(att, orderers[att], game, cell, rid, frags, key)
            same &= {k: v for k, v in again.items() if k != "seconds"} == {k: v for k, v in first.items() if k != "seconds"}

    n_j, n_o = sum(map(len, jrows.values())), sum(map(len, orows.values()))
    lines = ["TIER 0 EXTENDED (RUN_DECISIONS D19 addendum) -- first complete result, kept as is",
             f"frozen T0-classical: k={cls[1]} c={cls[2]} alpha={pos.alpha}, position model SHA-256 {cls[3]}",
             f"rows: Game J {n_j} pools, Game O {n_o} documents", "",
             "GAME J", f"{'attacker':<14}{'game':<18}{'cell':<31}{'pools':>6}{'F1_J':>8}{'base':>8}"
             f"{'F1_L':>8}{'q_mic':>8}{'exact':>9}"]
    for (a, g, c), rs in sorted(jrows.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0])):
        C, K = sum(r["C"] for r in rs), sum(r["K"] for r in rs)
        lines.append(f"{a:<14}{g:<18}{c:<31}{len(rs):>6}"
                     f"{statistics.fmean(r['joint_f1'] for r in rs):>8.4f}"
                     f"{statistics.fmean(r['joint_baseline'] for r in rs):>8.4f}"
                     f"{statistics.fmean(r['j_linkage_f1'] for r in rs):>8.4f}"
                     f"{(C / K if K else float('nan')):>8.4f}"
                     f"{sum(r['exact_records'] for r in rs):>5}/{sum(r['n_docs'] for r in rs)}")
    lines += ["", "GAME O (membership given; random tau = 0)",
              f"{'attacker':<16}{'game':<11}{'cell':<31}{'docs':>5}{'tau':>8}{'med':>8}{'exact':>7}{'disp':>7}"]
    for (a, g, c), rs in sorted(orows.items(), key=lambda kv: (kv[0][1], kv[0][2], kv[0][0])):
        taus = [r["tau"] for r in rs]
        lines.append(f"{a:<16}{g:<11}{c:<31}{len(rs):>5}{statistics.fmean(taus):>8.4f}"
                     f"{statistics.median(taus):>8.4f}{sum(r['exact_order'] for r in rs):>7}"
                     f"{statistics.fmean(r['mean_abs_disp'] for r in rs):>7.2f}")
    lines += ["", f"deterministic on re-run (first unit of each attacker x game): {same}",
              f"wall time {(time.time() - t_start) / 60:.1f} min"]
    open(os.path.join(OUT, "REPORT.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    if not same:
        sys.exit(1)


if __name__ == "__main__":
    main()
