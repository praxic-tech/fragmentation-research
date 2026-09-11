"""Paid sample of the batch hierarchical attacker. Authorized by the user
2026-09-11 ("run a sample run with a small amt of credits to test it").

One grid development pool (pool_000, 0 headline documents), the reference cut
(semantic x sentence). Wave 0 = candidate pairs; later waves = bridge rounds.
Each wave: submit -> wait -> fetch (ledger settles) -> ingest -> plan the next.
HARD STOP: the sample never spends more than SAMPLE_CAP, and never more than
1 + MAX_BRIDGE_ROUNDS waves. Resumable: a wave already submitted is fetched,
never submitted twice.
"""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))
from batch_game import headline_docs, load_frame
from batch_submit import (DEFAULT_STATE_DIR, build_requests, estimate_cost, fetch,
                          read_state, results_cost, results_path, state_path, submit)
from hier_batch import ingest, plan, score
from hierarchical import MAX_BRIDGE_ROUNDS
from run_ledger import Ledger

SAMPLE_CAP = 3.00
CELL = "results/grid_A/semantic__sentence"
OUT = "results/hier/sample1"
frame = load_frame("data/pools/pools.json", "data/pools/linkage_grid.json")
pools = [(p, m) for p, m in frame if p == "pool_000"]
assert pools and not (set(pools[0][1]) & headline_docs())

spent = 0.0
for wave in range(1 + MAX_BRIDGE_ROUNDS + 1):
    tag = f"hier-sample1-w{wave}"
    path = f"runs/hier_sample1_w{wave}.json"
    sp = state_path(DEFAULT_STATE_DIR, tag)
    if os.path.exists(sp):
        # already submitted: use exactly the spec that was sent, never re-plan it
        spec = json.load(open(path, encoding="utf-8"))
    else:
        # not submitted yet: (re)plan from the caches, overwriting any dry-run spec
        spec = plan([CELL], pools, wave, tag, OUT)
        json.dump(spec, open(path, "w", encoding="utf-8"), indent=1)
    if not spec["requests"]:
        print(f"wave {wave}: nothing left to ask -- the attack is complete")
        break
    e = spec["expected_by_tax"]
    print(f"wave {wave}: {len(spec['requests'])} pair batches, expected ${e['x2.3']:.2f} (x2.3), "
          f"${e['x5']:.2f} (x5); spent so far ${spent:.2f}", flush=True)
    if not os.path.exists(sp) and spent + e["x5"] > SAMPLE_CAP:
        sys.exit(f"STOP: wave {wave} could take the sample past ${SAMPLE_CAP:.2f}")
    state = read_state(sp) if os.path.exists(sp) else submit(spec, ledger=Ledger())
    res = fetch(state, wait=True, poll_seconds=60, ledger=Ledger())
    spent += results_cost(results_path(DEFAULT_STATE_DIR, tag))
    print(f"  fetched: {res['counts']}  actual ${res['actual_cost']:.4f}", flush=True)
    print(f"  ingest: {ingest(spec, [results_path(DEFAULT_STATE_DIR, tag)])}", flush=True)
else:
    sys.exit("STOP: wave limit reached with pairs still pending")

print(f"\nsample spend: ${spent:.4f}")
verdict = score([CELL], pools, OUT)
print("verdict:", {k: sorted(v) for k, v in verdict.items()})
