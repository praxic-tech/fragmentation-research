"""
final_t12.py — tiers 1 and 2 (T1-pythia160m, T2-pythia1.4b) on the headline
units (RUN_DECISIONS D19, "tiers 1 and 2 design" and the tuning addendum).
Main comparison. No API calls; CPU only.

Reads the Colab pair scores, re-verifies them (runs/t12_tune.verify), and
decodes with the decoder recorded in results/final_t{1,2}/RECORD.json, which
the tuning addendum commits before this runs:
    Game J  headline, 46 pools   chosen decoder
    Game O  headline, 100 docs   chosen orderer over the document's own scores
Same pools, shown order, masking seeds, Game O presentation and scorer
(joint_game.score_row) as every other attacker.

Leak check (presentation invariance): every headline J pool decoded again under
10 random permutations of the alias order (seeds 0-9); F1_J range reported.

The first complete result is kept: refuses if REPORT.txt exists.

    python runs/final_t12.py --tier T1 [--scores models/t12/out]
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

import numpy as np                                             # noqa: E402

import crossenc_t3 as T3                                       # noqa: E402
import lm_pmi_t12 as L                                         # noqa: E402
import t3_units as U                                           # noqa: E402
import t12_tune as TU                                          # noqa: E402
from joint_game import score_row                               # noqa: E402
from final_t0_attacker import KEEP                             # noqa: E402
from final_t0_extended import o_row                           # noqa: E402

N_PERM = 10


def score_groups(pid, frags, key, truth, groups):
    return score_row({"game": "J", "unit": pid, "alias_map": {f["fragment_id"]: f["fragment_id"] for f in frags},
                      "raw_response": groups, "repair": {"policy_share": 0.0}}, key, truth)


def j_row(tier, cfg, cell, pid, members, store):
    frags, key, truth, shown, n_docs, ms = U.j_prepare(cell, pid, members)
    groups, tel = L.attack_from_scores(tier, shown, n_docs, store, cfg, seed=U.SEED, mask_seed=ms)
    r = score_groups(pid, frags, key, truth, groups)
    return {"game": "headlineJ", "cell": U.cell_name(cell), "pool": pid, "attacker": L.NAMES[tier],
            "n_fragments": len(frags), "n_docs": n_docs, **{k: r.get(k) for k in KEEP},
            "telemetry": tel, "reconstruction": groups}


def permuted_f1(cfg, cell, pid, members, store, seed):
    """Decode the pool with its fragments' alias order permuted (= re-masking)."""
    frags, key, truth, shown, n_docs, ms = U.j_prepare(cell, pid, members)
    ids, texts, back = T3.masked_view(shown, U.SEED, ms)
    sc = T3.store_load(store, texts)
    p = np.random.default_rng(seed).permutation(len(ids))
    scp = {k: sc[k][np.ix_(p, p)] for k in ("S", "P", "A")} | {"pos": sc["pos"][p]}
    groups = [[back[ids[p[i]]] for i in g] for g in T3.decode(scp, n_docs, cfg, U.SEED)]
    return score_groups(pid, frags, key, truth, groups)["joint_f1"]


def make_o_orderer(store, orderer):
    def t12_o(shown, ltext):
        ids = sorted(shown)
        sc = T3.store_load(store, [ltext[i] for i in ids])
        if sc is None:
            raise FileNotFoundError("no pair scores for a Game O document")
        return [ids[i] for i in T3.order_group(range(len(ids)), sc, orderer)]
    t12_o.__name__ = f"t12_{orderer}_o"
    return t12_o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=sorted(L.MODELS), required=True)
    ap.add_argument("--scores", default=os.path.join("models", "t12", "out"))
    a = ap.parse_args()
    out = TU.out_dir(a.tier)
    if os.path.exists(os.path.join(out, "REPORT.txt")):
        raise SystemExit(f"{out}/REPORT.txt exists: the first complete result is kept; nothing re-run.")
    rec = json.load(open(os.path.join(out, "RECORD.json"), encoding="utf-8"))
    done, store, files = TU.verify(a.tier, a.scores)
    if files != rec["score_files_sha256"]:
        raise SystemExit("STOP: score files differ from those recorded at tuning")
    cfg = rec["chosen"]
    att_j, att_o = L.NAMES[a.tier], L.NAMES[a.tier] + "-O"
    print(f"{att_j}: {len(files)} score files verified; decoder {cfg}", flush=True)
    t_start = time.time()

    jl = [j for j in U.j_units() if j[0] == "headlineJ"]
    jrows = [j_row(a.tier, cfg, cell, pid, members, store) for _g, cell, pid, members in jl]
    ou = [o for o in U.o_units() if o[0] == "headlineO"]
    orderer = make_o_orderer(store, cfg["orderer"] if cfg["orderer"] else "borda")
    orows = [o_row(att_o, orderer, game, cell, rid, frags, key) for game, cell, rid, frags, key in ou]
    assert (len(jrows), len(orows)) == (46, 100), (len(jrows), len(orows))

    for sub, att, rows in (("headlineJ", att_j, jrows), ("headlineO", att_o, orows)):
        cell = rows[0]["cell"]
        p = os.path.join(out, sub, f"{cell}.{att}.jsonl")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")

    # determinism: first unit of each game again
    g, cell, pid, members = jl[0]
    same = j_row(a.tier, cfg, cell, pid, members, store) == jrows[0]
    game, cell_o, rid, frags, key = ou[0]
    r2 = o_row(att_o, orderer, game, cell_o, rid, frags, key)
    same &= {k: v for k, v in r2.items() if k != "seconds"} == {k: v for k, v in orows[0].items() if k != "seconds"}

    # presentation invariance
    perm_means = []
    for s in range(N_PERM):
        perm_means.append(statistics.fmean(permuted_f1(cfg, cell, pid, members, store, s)
                                           for _g, cell, pid, members in jl))
    inv = {"seeds": list(range(N_PERM)), "mean_F1_J_per_seed": perm_means,
           "reported_F1_J": statistics.fmean(r["joint_f1"] for r in jrows),
           "max_abs_diff": max(abs(x - statistics.fmean(r["joint_f1"] for r in jrows)) for x in perm_means)}
    json.dump(inv, open(os.path.join(out, "INVARIANCE.json"), "w", encoding="utf-8"), indent=1)

    C, K = sum(r["C"] for r in jrows), sum(r["K"] for r in jrows)
    taus = [r["tau"] for r in orows]
    lines = [f"TIER {a.tier[1]} {att_j} (RUN_DECISIONS D19) -- first complete result, kept as is",
             f"model {rec['model']}@{rec['revision']}; decoder {cfg}",
             f"pair scores: {done['gpu']}, {done['precision']}; {len(files)} score files verified", "",
             "GAME J headline (46 pools)",
             f"  F1_J {statistics.fmean(r['joint_f1'] for r in jrows):.4f}   "
             f"base {statistics.fmean(r['joint_baseline'] for r in jrows):.4f}   "
             f"F1_L {statistics.fmean(r['j_linkage_f1'] for r in jrows):.4f}   q_micro {C / K:.4f}   "
             f"exact {sum(r['exact_records'] for r in jrows)}/{sum(r['n_docs'] for r in jrows)}",
             "GAME O headline (100 documents; random tau = 0)",
             f"  tau {statistics.fmean(taus):.4f}   median {statistics.median(taus):.4f}   "
             f"exact {sum(r['exact_order'] for r in orows)}",
             "", f"presentation invariance, {N_PERM} permutations: mean F1_J "
             f"{min(perm_means):.4f}-{max(perm_means):.4f} (max |diff| {inv['max_abs_diff']:.4f})",
             f"deterministic on re-run (first unit of each game): {same}",
             f"wall time {(time.time() - t_start) / 60:.1f} min"]
    open(os.path.join(out, "REPORT.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    if not same:
        sys.exit(1)


if __name__ == "__main__":
    main()
