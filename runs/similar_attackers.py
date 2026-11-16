"""
similar_attackers.py — the non-LLM attackers on the similar pools
(RUN_DECISIONS D20, POST-HOC EXPLORATORY). CPU; no API calls.

The 46 pools of data/pools/similar_pools.json, with the headline fragments,
shown order and masking seeds every attacker uses (runs/t3_units.j_prepare),
scored by joint_game.score_row. Nothing is tuned here: every attacker runs
with what was frozen for the headline pools.

    T0-PUP, T0-classical   run now (runs/final_t0_attacker.run_pool, frozen settings)
    T3-crossenc            frozen weights; decoder runs/final_t3.FROZEN
    T1-pythia160m, T2-...  decoders recorded in results/final_t{1,2}/RECORD.json
Tiers 1-3 need pair scores from Colab (runs/similar_make_bundle.py). A tier
whose SCORE_DONE.json is not under --scores is skipped and listed as pending;
when it is there, the run is checked first: full run, texts match what this
repository generates, every score file hashes to what the GPU recorded.

Writes results/final_similar/similarJ/prose.<attacker>.jsonl. An attacker
whose file exists is not re-run (first complete result kept).

    python runs/similar_attackers.py [--scores models/similar/out]
"""

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis", "runs"):
    sys.path.insert(0, os.path.join(ROOT, d))

import crossenc_t3 as T3                                       # noqa: E402
import lm_pmi_t12 as L                                         # noqa: E402
import t3_units as U                                           # noqa: E402
import final_t0_attacker as F0                                 # noqa: E402
import similar_make_bundle as B                                # noqa: E402
from joint_game import score_row                               # noqa: E402

GAME = B.GAME
OUT = os.path.join("results", "final_similar", GAME)
T3_FROZEN = {"decoder": "cluster-rank", "grouper": "spectral", "refine": True, "orderer": "borda"}
T3_WEIGHTS = "de081db6893e57ebc69b2cbb202851558f49b7d41eea38dc2c77ba73e947582a"


def path_for(att):
    return os.path.join(OUT, f"prose.{att}.jsonl")


def write(att, rows):
    os.makedirs(OUT, exist_ok=True)
    with open(path_for(att), "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    f1 = sum(r["joint_f1"] for r in rows) / len(rows)
    fl = sum(r["j_linkage_f1"] for r in rows) / len(rows)
    q = sum(r["C"] for r in rows) / max(sum(r["K"] for r in rows), 1)
    print(f"{att:16s} {len(rows)} pools   F1_J {f1:.4f}   F1_L {fl:.4f}   q_micro {q:.4f}", flush=True)


def verify(tier, scores_dir, want):
    """The score store for a Colab tier, after checking the run against this repository."""
    base = os.path.join(scores_dir, tier)
    done = json.load(open(os.path.join(base, "SCORE_DONE.json"), encoding="utf-8"))
    if done["limit"] or any(done.get(k) != v for k, v in want.items()):
        raise SystemExit(f"STOP: {base}/SCORE_DONE.json is not a full run of the frozen {tier} model")
    rows = B.unit_texts()
    man = {m["unit"]: m for m in done["manifest"]}
    if len(man) != len(rows):
        raise SystemExit(f"STOP: {tier} manifest has {len(man)} units, expected {len(rows)}")
    store = os.path.join(base, "scores")
    for r in rows:
        m = man[r["unit"]]
        sha = T3.texts_sha(r["texts"])
        if m["texts_sha256"] != sha or m["n"] != len(r["texts"]):
            raise SystemExit(f"STOP: texts of {r['unit']} differ from what {tier} scored")
        if T3.file_sha256(T3.store_path(store, sha)) != m["file_sha256"]:
            raise SystemExit(f"STOP: {tier} score file for {r['unit']} changed since scoring")
    return done, store


def decode_row(att, cfg, cell, pid, members, store):
    frags, key, truth, shown, n_docs, ms = U.j_prepare(cell, pid, members)
    groups, tel = T3.attack_from_scores(shown, n_docs, store, cfg, seed=U.SEED, mask_seed=ms)
    tel["attacker"] = att
    r = score_row({"game": "J", "unit": pid, "alias_map": {f["fragment_id"]: f["fragment_id"] for f in frags},
                   "raw_response": groups, "repair": {"policy_share": 0.0}}, key, truth)
    return {"game": GAME, "cell": "prose", "pool": pid, "attacker": att, "n_fragments": len(frags),
            "n_docs": n_docs, **{k: r.get(k) for k in F0.KEEP}, "telemetry": tel, "reconstruction": groups}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", default=os.path.join("models", "similar", "out"))
    a = ap.parse_args()
    pools, cell = B.pools(), B.cell_dir()
    pending = []

    cls = None
    for att in ("T0-PUP", "T0-classical"):
        if os.path.exists(path_for(att)):
            print(f"{att}: already written, kept")
            continue
        cls = cls or F0.load_classical()
        write(att, [F0.run_pool((att, GAME, cell, pid, members), cls) for pid, members in pools])

    tiers = [("T3", "T3-crossenc", T3_FROZEN, {"weights_sha256": T3_WEIGHTS})]
    for tier in ("T1", "T2"):
        rp = os.path.join("results", "final_" + tier.lower(), "RECORD.json")
        if not os.path.exists(rp):
            pending.append(f"{L.NAMES[tier]} (no tuning record)")
            continue
        rec = json.load(open(rp, encoding="utf-8"))
        tiers.append((tier, L.NAMES[tier], rec["chosen"], {"model": rec["model"], "revision": rec["revision"]}))
    for tier, att, cfg, want in tiers:
        if os.path.exists(path_for(att)):
            print(f"{att}: already written, kept")
            continue
        if not os.path.exists(os.path.join(a.scores, tier, "SCORE_DONE.json")):
            pending.append(f"{att} (pair scores not on this machine)")
            continue
        done, store = verify(tier, a.scores, want)
        print(f"{att}: {len(pools)} score files verified ({done['gpu']})", flush=True)
        write(att, [decode_row(att, cfg, cell, pid, members, store) for pid, members in pools])
    if pending:
        print("pending:", "; ".join(pending))


if __name__ == "__main__":
    main()
