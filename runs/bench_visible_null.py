"""
bench_visible_null.py — score-free engineering benchmark of the visible-text
permutation nulls (D16). Uses the largest frozen token pool with a SYNTHETIC
random reconstruction (never an attacker output) and reports timings and
reproducibility only; no null value from a real pool is printed.

    python runs/bench_visible_null.py
"""

import hashlib
import json
import os
import random
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness"):
    sys.path.insert(0, os.path.join(ROOT, d))

import numpy as np                                                            # noqa: E402

from joint_game import build_units                                            # noqa: E402
from visible_metrics import PoolScorer, null_rng, oracle_size_null, predicted_structure_null  # noqa: E402

FROZEN = json.load(open("results/single_token_edge/FROZEN_DESIGN.json", encoding="utf-8"))
POOLS = json.load(open(FROZEN["pools_file"], encoding="utf-8"))["pools"]
OUT = "results/single_token_edge/null_benchmark.json"


def scorer(cell, pid, members):
    _o, units, _k, truth = build_units(cell, 0, 7, 42, pools=[(pid, members)], o_docs=[])
    return PoolScorer(truth[pid], {f["fragment_id"]: f["text"] for f in units[0][1]})


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--hash":
        p = next(x for x in POOLS if x["pool_id"] == sys.argv[2])
        ps = scorer(FROZEN["cells"][1], p["pool_id"], p["members"])
        print(hashlib.sha256(oracle_size_null(ps, 50, null_rng(p["pool_id"], "token", "bench-det")).tobytes()).hexdigest())
        return
    sizes = {p["pool_id"]: sum(1 for l in open(os.path.join(FROZEN["cells"][1], "prose_fragments.jsonl"), encoding="utf-8")
                               if l.strip() and json.loads(l)["record_id"] in p["members"]) for p in POOLS}
    big = max(POOLS, key=lambda p: sizes[p["pool_id"]])
    tok = scorer(FROZEN["cells"][1], big["pool_id"], big["members"])
    sen = scorer(FROZEN["cells"][0], big["pool_id"], big["members"])
    r = random.Random(12345)
    ids = tok.all_ids[:]
    r.shuffle(ids)
    keep = ids[:-20]                                              # 20 synthetic "dropped" fragments
    cuts = sorted(r.sample(range(1, len(keep)), 6))
    syn = [keep[i:j] for i, j in zip([0] + cuts, cuts + [len(keep)])]
    t = {}
    for n in (200, 500, 1000, 10_000):
        t0 = time.perf_counter()
        oracle_size_null(tok, n, null_rng(big["pool_id"], "token", "bench-oracle"))
        t[f"token_oracle_{n}"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    predicted_structure_null(tok, syn, 1000, null_rng(big["pool_id"], "token", "bench-pred"))
    t["token_predicted_1000"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    oracle_size_null(sen, 1000, null_rng(big["pool_id"], "sentence", "bench-oracle"))
    t["sentence_oracle_1000"] = time.perf_counter() - t0
    per = {"token_oracle": t["token_oracle_10000"] / 10_000, "token_predicted": t["token_predicted_1000"] / 1000,
           "sentence": t["sentence_oracle_1000"] / 1000}
    n = FROZEN["permutations_per_pool_condition_null"]
    per_pool = n * (per["token_oracle"] + per["token_predicted"] + 2 * per["sentence"])
    a1 = oracle_size_null(tok, 50, null_rng(big["pool_id"], "token", "bench-det"))
    a2 = oracle_size_null(tok, 50, null_rng(big["pool_id"], "token", "bench-det"))
    hs = [subprocess.run([sys.executable, __file__, "--hash", big["pool_id"]], capture_output=True, text=True,
                         env={**os.environ, "PYTHONHASHSEED": s}).stdout.strip() for s in ("0", "1")]
    here = hashlib.sha256(a1.tobytes()).hexdigest()
    rep = {"what": "score-free benchmark of the visible-score permutation nulls (D16)",
           "implementation": "integer-coded tokens; bit-parallel LCS on Python ints (Crochemore et al. 2001 / "
                             "Hyyro); multiset overlap by bincount + minimum; scipy linear_sum_assignment; numpy "
                             "PCG64 seeded by SHA-256",
           "largest_token_pool": big["pool_id"], "token_fragments": sizes[big["pool_id"]],
           "reconstruction": "synthetic random partition into 7 groups + 20 dropped fragments (not an attacker output)",
           "seconds": t, "ms_per_permutation": {k: v * 1000 for k, v in per.items()},
           "frozen_permutations": n,
           "projected_seconds_per_pool_both_nulls_both_conditions": per_pool,
           "projected_minutes_20_pools": 20 * per_pool / 60,
           "deterministic_in_process": bool(np.array_equal(a1, a2)),
           "deterministic_across_processes_PYTHONHASHSEED_0_1": hs[0] == hs[1] == here}
    json.dump(rep, open(OUT, "w", encoding="utf-8"), indent=2)
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
