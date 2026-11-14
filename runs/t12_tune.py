"""
t12_tune.py — choose the tier 1 / tier 2 decoder on the dev pools only
(RUN_DECISIONS D19, "tiers 1 and 2 design"). CPU.

Verifies the Colab run first: SCORE_DONE.json is a full run of the pinned
revision on the bundle's texts, every unit's texts match what this repository
generates now (runs/t12_make_bundle.unit_texts), and every score file still
hashes to what the GPU recorded. Then runs tier 3's tuning procedure
(runs/t3_dev.stage_tune) on the dev score files alone, with the orderer set
{borda, path1} (no position output). No evaluation unit is decoded here.

Writes results/final_t{1,2}/dev_tuning.json and RECORD.json (chosen decoder,
dev scores, every score file's SHA-256). Those go into the tuning addendum
before runs/final_t12.py decodes anything.

    python runs/t12_tune.py --tier T1 --scores models/t12/out
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
import t3_dev as D3                                            # noqa: E402
import t12_make_bundle as B                                    # noqa: E402

ORDERERS_T12 = ("borda", "path1")


def out_dir(tier):
    base = os.environ.get("T12_RESULTS_ROOT", "results")          # override only for pipeline tests
    return os.path.join(base, "final_t1" if tier == "T1" else "final_t2")


def verify(tier, scores_dir):
    """The score store for `tier`, after checking the Colab run against this repository."""
    base = os.path.join(scores_dir, tier)
    done = json.load(open(os.path.join(base, "SCORE_DONE.json"), encoding="utf-8"))
    name, rev = L.MODELS[tier]
    if (done["model"], done["revision"]) != (name, rev) or done["limit"]:
        raise SystemExit(f"STOP: SCORE_DONE.json is not a full run of {name}@{rev}")
    rows = B.unit_texts()
    man = {(m["game"], m["unit"]): m for m in done["manifest"]}
    if len(man) != len(rows):
        raise SystemExit(f"STOP: manifest has {len(man)} units, expected {len(rows)}")
    store = os.path.join(base, "scores")
    files = {}
    for r in rows:
        m = man[(r["game"], r["unit"])]
        sha = T3.texts_sha(r["texts"])
        if m["texts_sha256"] != sha or m["n"] != len(r["texts"]):
            raise SystemExit(f"STOP: texts of {r['game']} {r['unit']} differ from what was scored")
        if sha not in files:
            files[sha] = T3.file_sha256(T3.store_path(store, sha))
        if files[sha] != m["file_sha256"]:
            raise SystemExit(f"STOP: score file for {r['game']} {r['unit']} changed since scoring")
    return done, store, files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=sorted(L.MODELS), required=True)
    ap.add_argument("--scores", default=os.path.join("models", "t12", "out"))
    a = ap.parse_args()
    out = out_dir(a.tier)
    if os.path.exists(os.path.join(out, "RECORD.json")):
        raise SystemExit(f"{out}/RECORD.json exists: the decoder is already chosen.")
    done, store, files = verify(a.tier, a.scores)
    print(f"{a.tier}: {len(files)} score files verified ({done['gpu']}, {done['precision']})", flush=True)

    T3.ORDERERS = ORDERERS_T12                    # stage_tune reads T3.ORDERERS at call time
    pools = D3.dev_pools(None, False)
    res = D3.stage_tune(pools, store, out)
    res["dev_" + a.tier] = res.pop("dev_T3")
    os.makedirs(out, exist_ok=True)
    json.dump(res, open(os.path.join(out, "dev_tuning.json"), "w", encoding="utf-8"), indent=1)
    rec = {"tier": a.tier, "attacker": L.NAMES[a.tier], "model": done["model"], "revision": done["revision"],
           "chosen": res["chosen"], "dev": res["dev_" + a.tier], "orderers_offered": list(ORDERERS_T12),
           "scored_on": {k: done[k] for k in ("gpu", "torch", "transformers", "precision", "side_cap",
                                              "texts_sha256")},
           "score_files_sha256": dict(sorted(files.items()))}
    json.dump(rec, open(os.path.join(out, "RECORD.json"), "w", encoding="utf-8"), indent=1)
    print(json.dumps({k: rec[k] for k in ("attacker", "chosen", "dev")}, indent=1))


if __name__ == "__main__":
    main()
