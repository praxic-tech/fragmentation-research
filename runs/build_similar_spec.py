"""
build_similar_spec.py — the one-shot Sonnet spec for the similar pools
(RUN_DECISIONS D20, POST-HOC EXPLORATORY). Builds and freezes; sends nothing.

Exactly the headline build (runs/final_headlineJ.json: cell data/prose, game J,
pool size 7, seed 42, the same max_tokens margin and model) with the 46 pools
of data/pools/similar_pools.json. Writes runs/similar_J.json and its manifest
(spec SHA-256, preflight counts, expected and worst-case cost). Refuses to
overwrite.

    python runs/build_similar_spec.py
"""

import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness"):
    sys.path.insert(0, os.path.join(ROOT, d))

from batch_game import build_spec, expected_cost              # noqa: E402
from batch_submit import IN_PER_M, OUT_PER_M, RESERVE_MARGIN  # noqa: E402
from masking import preflight_stats, reset_preflight_stats   # noqa: E402

SPEC = os.path.join("runs", "similar_J.json")
HEAD = os.path.join("runs", "final_headlineJ.json")


def main():
    if os.path.exists(SPEC):
        raise SystemExit(f"{SPEC} exists: frozen once.")
    head = json.load(open(HEAD, encoding="utf-8"))
    hb = head["build"]
    frame = json.load(open(os.path.join("data", "pools", "similar_pools.json"), encoding="utf-8"))
    pools = [(p["pool_id"], p["members"]) for p in frame["pools"]]
    assert sorted(m for _p, ms in pools for m in ms) == sorted(m for _p, ms in hb["pools"] for m in ms), \
        "similar pools must hold exactly the headline documents"
    reset_preflight_stats()
    spec = build_spec(hb["cells"], ["J"], docs=0, pool_size=hb["pool_size"], seed=hb["seed"],
                      tag="final-similarJ", model=head["model"], margin=hb["margin"], arm=hb["arm"],
                      pools=pools, o_docs=[])
    pf = preflight_stats()
    if pf["blocked"]:
        raise SystemExit(f"STOP: preflight blocked {pf['blocked']} prompts")
    with open(SPEC, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=1)
    worst = sum(len(r["prompt"]) // 4 / 1e6 * IN_PER_M + r["max_tokens"] / 1e6 * OUT_PER_M for r in spec["requests"])
    man = {"what": "POST-HOC EXPLORATORY — SIMILAR POOLS (RUN_DECISIONS D20), one-shot Sonnet, game J",
           "spec": SPEC.replace("\\", "/"), "spec_sha256": hashlib.sha256(open(SPEC, "rb").read()).hexdigest(),
           "model": spec["model"], "n_requests": len(spec["requests"]),
           "expected_usd_cost_model": spec["expected_usd"], "headline_expected_usd_cost_model": expected_cost(head),
           "est_cost_worst_case": round(worst, 2),
           "ledger_reserve": round(min(worst, RESERVE_MARGIN * spec["expected_usd"]), 2),
           "preflight": {"checked": pf["checked"], "blocked": pf["blocked"]},
           "same_as_headline": {k: hb[k] for k in ("cells", "pool_size", "seed", "margin", "arm")}}
    json.dump(man, open(SPEC.replace(".json", "_manifest.json"), "w", encoding="utf-8"), indent=2)
    print(json.dumps(man, indent=1))


if __name__ == "__main__":
    main()
