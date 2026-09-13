"""
final_free_attackers.py — the free, local J attacker and baselines on the
frozen final pools (RUN_DECISIONS D12, "Free attackers on the final pools").
No API calls.

For every pool of every frozen final J spec -- headline (46 pools), grid pools
2-25 (9 cells) and identifier (20 pools) -- from the SAME fragment files and
truth the one-shot model's answers are scored against:
    analytic baseline   one bucket, arbitrary order: the scorer's joint_baseline
    Memon-inspired      memon_joint.attack at the frozen n = d = 2
Every answer goes through joint_game.score_row, the scorer the model's answers
go through, with no attacker-specific branch. The identifier schema-order
baseline is analysis/identifier_schema_baseline.py (D11); it is quoted here.

Presentation: the attacker never sees the file order (D1's leak). Fragments go
in shuffled by the same per-unit seed that orders the model's prompt, and
memon_joint.attack masks the ids itself with a per-unit seeded alias map.

Output: results/final_free/<game>/<cell>.memon_joint.jsonl (one row per pool)
and results/final_free/REPORT.txt. Per-pool rows and descriptive summaries
only; confidence intervals wait for the frozen results plan.

    python runs/final_free_attackers.py --smoke      # first pool of each game, writes nothing
    python runs/final_free_attackers.py [--workers 6]
"""

import argparse
import json
import os
import random
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

from joint_game import _unit_seed, build_units, score_row   # noqa: E402
from memon_joint import attack                                # noqa: E402

MEMON_N = MEMON_D = 2          # frozen (RUN_DECISIONS D12): the committed default
SEED = 42
OUT = os.path.join("results", "final_free")
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


def run_pool(job):
    game, cell, pid, members = job
    _o, units, key, truth = build_units(cell, 0, len(members), SEED,
                                        pools=[(pid, members)], o_docs=[])
    (_pid, frags, n_docs), = units
    # Never the file order: the per-unit seeded order the model's prompt used.
    shown = [{"fragment_id": f["fragment_id"], "text": f["text"]} for f in frags]
    random.Random(_unit_seed(frags, SEED, "order")).shuffle(shown)
    t0 = time.perf_counter()
    groups, tel = attack(shown, n_docs, n=MEMON_N, d=MEMON_D, seed=SEED,
                         mask_seed=_unit_seed(frags, SEED, "labels"))
    secs = time.perf_counter() - t0
    ident = {f["fragment_id"]: f["fragment_id"] for f in frags}
    r = score_row({"game": "J", "unit": pid, "alias_map": ident, "raw_response": groups,
                   "repair": {"policy_share": 0.0}}, key, truth)
    g = tel["grouping"]
    return {"game": game, "cell": os.path.basename(cell), "pool": pid,
            "attacker": "memon-inspired", "n": MEMON_N, "d": MEMON_D,
            "n_fragments": len(frags), "n_docs": n_docs,
            **{k: r.get(k) for k in KEEP},
            "context_coverage": tel["context_coverage"],
            "zero_weight_pairs": tel["zero_weight_pairs"],
            "score_pair_calls": tel["score_pair_calls"],
            "arbitrary_pairs": tel["arbitrary_pairs"],
            "exact_n_groups": g["exact_n"], "largest_group": g["largest"],
            "singletons": g["singletons"], "seconds": round(secs, 2)}


def _mean(rows, k):
    xs = [r[k] for r in rows if r.get(k) is not None]
    return statistics.fmean(xs) if xs else float("nan")


def report(rows):
    schema = None
    p = os.path.join("results", "audit", "identifier_schema_baseline.json")
    if os.path.exists(p):
        schema = statistics.fmean(x["schema_joint_f1"] for x in json.load(open(p))["pools"])
    by_cell = {}
    for r in rows:
        by_cell.setdefault((r["game"], r["cell"]), []).append(r)
    head = (f"{'game':<12}{'cell':<31}{'pools':>6}{'F1_J':>8}{'med':>8}{'base':>8}{'A_J':>8}"
            f"{'P_J':>7}{'R_J':>7}{'F1_L':>7}{'q_mic':>7}{'exact':>7}{'ctx':>7}{'w=0':>7}")
    lines = [f"FREE ATTACKERS ON THE FINAL POOLS -- Memon-inspired, n = d = {MEMON_N} "
             "(frozen, RUN_DECISIONS D12); $0", "", head, "-" * len(head)]
    for (game, cell), rs in by_cell.items():
        c, k = sum(r["C"] or 0 for r in rs), sum(r["K"] or 0 for r in rs)
        ex = sum(r["exact_records"] for r in rs)
        docs = sum(r["n_groups_true"] for r in rs)
        calls = sum(r["score_pair_calls"] for r in rs)
        zero = sum(r["zero_weight_pairs"] for r in rs) / (calls / 2) if calls else float("nan")
        lines.append(f"{game:<12}{cell:<31}{len(rs):>6}{_mean(rs, 'joint_f1'):>8.4f}"
                     f"{statistics.median(r['joint_f1'] for r in rs):>8.4f}"
                     f"{_mean(rs, 'joint_baseline'):>8.4f}{_mean(rs, 'joint_advantage'):>8.4f}"
                     f"{_mean(rs, 'joint_p'):>7.3f}{_mean(rs, 'joint_r'):>7.3f}"
                     f"{_mean(rs, 'j_linkage_f1'):>7.3f}{(c / k if k else float('nan')):>7.3f}"
                     f"{ex:>3}/{docs:<3}{_mean(rs, 'context_coverage'):>7.1%}{zero:>7.1%}")
    if schema is not None:
        lines.append(f"\nidentifier schema-order baseline (D11), mean F1_J over its 20 pools: {schema:.4f}")
    lines += ["", "COLUMNS",
              "  pools   pools scored (every pool completes: the attacker is local, no budget)",
              "  F1_J    mean ordered-pair F1 (joint membership + order); med = its median",
              "  base    mean analytic baseline: one bucket, arbitrary order",
              "  A_J     mean scorer advantage (F1_J - base) / (1 - base); the paper's advantage",
              "          definition and all confidence intervals wait for the frozen results plan",
              "  P_J/R_J mean directed-pair precision / recall",
              "  F1_L    mean linkage F1 (membership only); F1_J = F1_L x q",
              "  q_mic   micro order quality, sum C / sum K",
              "  exact   documents reconstructed exactly / documents",
              "  ctx     mean share of n-gram boundary contexts seen (the rest score the smoothing prior)",
              "  w=0     share of ordered pairs with zero directional evidence"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--smoke", action="store_true", help="first pool of each game; writes nothing")
    a = ap.parse_args()
    todo = list(jobs())
    if a.smoke:
        todo = [next(t for t in todo if t[0] == g) for g, _ in GAMES]
    print(f"{len(todo)} pools: Memon-inspired at n = d = {MEMON_N}, {a.workers} workers, $0", flush=True)
    rows, t0 = [], time.time()
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for i, row in enumerate(ex.map(run_pool, todo, chunksize=1), 1):
            rows.append(row)
            if i % 20 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)} pools, {time.time() - t0:.0f}s", flush=True)

    # Determinism: the first pool of each game again, in this process.
    same = True
    for game, _paths in GAMES:
        j = next(t for t in todo if t[0] == game)
        first = next(r for r in rows if (r["game"], r["pool"]) == (game, j[2])
                     and r["cell"] == os.path.basename(j[1]))
        again = run_pool(j)
        same &= {k: v for k, v in again.items() if k != "seconds"} == \
                {k: v for k, v in first.items() if k != "seconds"}
    print(f"deterministic on re-run (first pool of each game): {same}")

    text = report(rows)
    print("\n" + text)
    if a.smoke:
        return
    by_cell = {}
    for r in rows:
        by_cell.setdefault((r["game"], r["cell"]), []).append(r)
    for (game, cell), rs in by_cell.items():
        d = os.path.join(OUT, game)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{cell}.memon_joint.jsonl"), "w", encoding="utf-8") as fh:
            for r in sorted(rs, key=lambda r: r["pool"]):
                fh.write(json.dumps(r) + "\n")
    with open(os.path.join(OUT, "REPORT.txt"), "w", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(f"\nwrote {len(rows)} rows under {OUT}/ and {OUT}/REPORT.txt")
    if not same:
        sys.exit(1)


if __name__ == "__main__":
    main()
