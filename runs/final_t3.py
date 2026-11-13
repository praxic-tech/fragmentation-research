"""
final_t3.py — tier 3 (T3-crossenc) on every evaluation unit (RUN_DECISIONS D19,
"tier 3 design" and "tier 3 tuning, fixed before the evaluation run").
Main comparison. No API calls; CPU only.

Reads the pair scores computed once on Colab (runs/t3_score_eval.py) and
decodes them with the decoder chosen on dev and recorded in
results/final_t3/RECORD.json before any evaluation pair was scored:
    Game J  cluster-rank: spectral grouping + refine, borda ordering
    Game O  borda over the document's own pair scores
Before decoding, every score file is checked against SCORE_DONE.json (the
weights hash and each file's SHA-256), and every unit's texts against the
manifest. Same pools, shown order, masking seeds, Game O presentation and
scorer (joint_game.score_row) as tier 0 and every other attacker.

The first complete result is kept: refuses if REPORT.txt exists.

    python runs/final_t3.py [--scores models/t3]
"""

import argparse
import json
import os
import statistics
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis", "runs"):
    sys.path.insert(0, os.path.join(ROOT, d))

import harness as H                                            # noqa: E402
import crossenc_t3 as T3                                       # noqa: E402
import t3_units as U                                           # noqa: E402
from joint_game import score_row                               # noqa: E402
from final_t0_attacker import KEEP                             # noqa: E402
from final_t0_extended import o_row                            # noqa: E402

OUT = os.path.join("results", "final_t3")
ATT_J, ATT_O = "T3-crossenc", "T3-crossenc-O"
FROZEN = {"decoder": "cluster-rank", "grouper": "spectral", "refine": True, "orderer": "borda"}


def check_inputs(scores_dir):
    rec = json.load(open(os.path.join(OUT, "RECORD.json"), encoding="utf-8"))
    if rec["chosen"] != FROZEN:
        raise SystemExit(f"STOP: RECORD.json decoder {rec['chosen']} is not the frozen {FROZEN}")
    done = json.load(open(os.path.join(scores_dir, "SCORE_DONE.json"), encoding="utf-8"))
    if done["weights_sha256"] != rec["model_sha256"] or done["limit"]:
        raise SystemExit("STOP: SCORE_DONE.json is not a full run of the recorded weights")
    store = os.path.join(scores_dir, "eval_scores")
    units = U.all_unit_texts()
    man = {(m["kind"], m["game"], m["cell"], m["unit"]): m for m in done["manifest"]}
    if len(man) != len(units):
        raise SystemExit(f"STOP: manifest has {len(man)} units, expected {len(units)}")
    checked = {}
    for kind, game, cell, uid, texts in units:
        m = man[(kind, game, cell, uid)]
        sha = T3.texts_sha(texts)
        if m["texts_sha256"] != sha or m["n"] != len(texts):
            raise SystemExit(f"STOP: texts of {kind} {game} {cell} {uid} differ from what was scored")
        if sha not in checked:
            checked[sha] = T3.file_sha256(T3.store_path(store, sha))
        if checked[sha] != m["file_sha256"]:
            raise SystemExit(f"STOP: score file for {kind} {game} {cell} {uid} changed since scoring")
    return rec, done, store, len(checked)


def j_row(game, cell, pid, members, store):
    frags, key, truth, shown, n_docs, ms = U.j_prepare(cell, pid, members)
    t0 = time.perf_counter()
    groups, tel = T3.attack_from_scores(shown, n_docs, store, FROZEN, seed=U.SEED, mask_seed=ms)
    secs = time.perf_counter() - t0
    r = score_row({"game": "J", "unit": pid, "alias_map": {f["fragment_id"]: f["fragment_id"] for f in frags},
                   "raw_response": groups, "repair": {"policy_share": 0.0}}, key, truth)
    return {"game": game, "cell": U.cell_name(cell), "pool": pid, "attacker": ATT_J,
            "n_fragments": len(frags), "n_docs": n_docs, **{k: r.get(k) for k in KEEP},
            "telemetry": tel, "seconds": round(secs, 2), "reconstruction": groups}


def make_o_orderer(store):
    def t3_borda_o(shown, ltext):
        ids = sorted(shown)                                   # masked labels: neutral index order
        sc = T3.store_load(store, [ltext[i] for i in ids])
        if sc is None:
            raise FileNotFoundError("no pair scores for a Game O document")
        return [ids[i] for i in T3.order_borda(range(len(ids)), T3.before_logit(sc["P"]))]
    return t3_borda_o


def strip(r):
    return {k: v for k, v in r.items() if k not in ("seconds", "telemetry")} | \
        {"telemetry": {k: v for k, v in r.get("telemetry", {}).items() if k != "seconds"}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", default=os.path.join("models", "t3"))
    a = ap.parse_args()
    if os.path.exists(os.path.join(OUT, "REPORT.txt")):
        raise SystemExit(f"{OUT}/REPORT.txt exists: the first complete result is kept; nothing re-run.")
    rec, done, store, n_files = check_inputs(a.scores)
    print(f"inputs verified: {n_files} score files, weights {rec['model_sha256'][:12]}, "
          f"scored on {done['gpu']}; decoder {FROZEN}", flush=True)
    t_start = time.time()

    jl = list(U.j_units())
    jrows = {}
    for i, (game, cell, pid, members) in enumerate(jl, 1):
        row = j_row(game, cell, pid, members, store)
        jrows.setdefault((row["attacker"], row["game"], row["cell"]), []).append(row)
        if i % 50 == 0:
            print(f"  J {i}/{len(jl)}  {(time.time() - t_start) / 60:.1f} min", flush=True)
    orderer = make_o_orderer(store)
    ou = list(U.o_units())
    orows = {}
    for game, cell, rid, frags, key in ou:
        row = o_row(ATT_O, orderer, game, cell, rid, frags, key)
        orows.setdefault((ATT_O, game, row["cell"]), []).append(row)
    print(f"  O {len(ou)} documents done", flush=True)

    for (att, g, c), rs in list(jrows.items()) + list(orows.items()):
        p = os.path.join(OUT, g, f"{c}.{att}.jsonl")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            for r in rs:
                fh.write(json.dumps(r) + "\n")

    # determinism: first unit of every game, decoded again
    same = True
    for g, _p in U.J_GAMES:
        game, cell, pid, members = next(j for j in jl if j[0] == g)
        first = next(r for r in jrows[(ATT_J, game, U.cell_name(cell))] if r["pool"] == pid)
        same &= strip(j_row(game, cell, pid, members, store)) == strip(first)
    for g, _p in U.O_GAMES:
        game, cell, rid, frags, key = next(u for u in ou if u[0] == g)
        first = next(r for r in orows[(ATT_O, game, U.cell_name(cell))] if r["doc"] == rid)
        same &= strip(o_row(ATT_O, orderer, game, cell, rid, frags, key)) == strip(first)

    n_j, n_o = sum(map(len, jrows.values())), sum(map(len, orows.values()))
    assert (n_j, n_o) == (U.N_J, U.N_O), (n_j, n_o)
    lines = ["TIER 3 T3-crossenc (RUN_DECISIONS D19) -- first complete result, kept as is",
             f"weights SHA-256 {rec['model_sha256']}; decoder {FROZEN}",
             f"pair scores: {done['gpu']}, {done['precision']}; {n_files} score files verified",
             f"rows: Game J {n_j} pools, Game O {n_o} documents", "",
             "GAME J", f"{'game':<18}{'cell':<31}{'pools':>6}{'F1_J':>8}{'base':>8}"
             f"{'F1_L':>8}{'q_mic':>8}{'exact':>9}"]
    for (_a, g, c), rs in sorted(jrows.items(), key=lambda kv: (kv[0][1], kv[0][2])):
        C, K = sum(r["C"] for r in rs), sum(r["K"] for r in rs)
        lines.append(f"{g:<18}{c:<31}{len(rs):>6}"
                     f"{statistics.fmean(r['joint_f1'] for r in rs):>8.4f}"
                     f"{statistics.fmean(r['joint_baseline'] for r in rs):>8.4f}"
                     f"{statistics.fmean(r['j_linkage_f1'] for r in rs):>8.4f}"
                     f"{(C / K if K else float('nan')):>8.4f}"
                     f"{sum(r['exact_records'] for r in rs):>5}/{sum(r['n_docs'] for r in rs)}")
    lines += ["", "GAME O (membership given; random tau = 0)",
              f"{'game':<11}{'cell':<31}{'docs':>5}{'tau':>8}{'med':>8}{'exact':>7}{'disp':>7}"]
    for (_a, g, c), rs in sorted(orows.items(), key=lambda kv: (kv[0][1], kv[0][2])):
        taus = [r["tau"] for r in rs]
        lines.append(f"{g:<11}{c:<31}{len(rs):>5}{statistics.fmean(taus):>8.4f}"
                     f"{statistics.median(taus):>8.4f}{sum(r['exact_order'] for r in rs):>7}"
                     f"{statistics.fmean(r['mean_abs_disp'] for r in rs):>7.2f}")
    lines += ["", f"deterministic on re-run (first unit of each game): {same}",
              f"wall time {(time.time() - t_start) / 60:.1f} min"]
    open(os.path.join(OUT, "REPORT.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    if not same:
        sys.exit(1)


if __name__ == "__main__":
    main()
