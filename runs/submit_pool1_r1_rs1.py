"""Resubmit the one cut-off repair request of grid pool 1 (random__token-window
prose_0156, repair round 1) at the 128k ceiling, prompt unchanged.
Expected ~$0.09, worst case $0.64. Approved by the user 2026-09-11."""
import io, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))
from batch_game import build_resubmit_spec
from batch_submit import build_requests, estimate_cost, submit
from run_ledger import Ledger

rp = json.load(open("runs/grid_A_pool1_r1.json", encoding="utf-8"))
rs = build_resubmit_spec(rp, ["results/batches/grid-A-pool1-r1.results.jsonl"], "grid-A-pool1-r1-rs1")
orig = {r["unit"]: r["prompt"] for r in rp["requests"]}
assert len(rs["requests"]) == 1 and rs["requests"][0]["max_tokens"] == 128000
assert rs["requests"][0]["prompt"] == orig[rs["requests"][0]["unit"]]
assert estimate_cost(build_requests(rs))["est_cost_worst_case"] <= 0.65
with io.open("runs/grid_A_pool1_r1_rs1.json", "w", encoding="utf-8") as fh:
    json.dump(rs, fh, indent=1)
state = submit(rs, ledger=Ledger())
print(json.dumps({k: state[k] for k in ("batch_id", "n_requests", "submitted_at")}))
