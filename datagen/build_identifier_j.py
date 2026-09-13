"""
build_identifier_j.py — the identifier Game J cell, its frozen pools, and its
frozen (NOT submitted) spec. RUN_DECISIONS D11. No API calls.

WHAT IS FIXED HERE, BEFORE ANY IDENTIFIER J ANSWER EXISTS
  records   r_0050 .. r_0499: the 450 records NO language model has seen. The
            first 50 (r_0000..r_0049) were shown to an LLM in the week-2/3
            exploratory O / L runs; they are excluded for that exposure, not
            for their results.
  pools     the 450 ordered by sha256('identifier-J|' + record_id), cut into
            pools of 7 (64 pools). Primary sample = the first 20. The rest are
            a reserve that is NOT run unless a new decision says so.
  cell      one fragment per field, exactly as data/identifier (name, ssn,
            account, address); answer-key order = the generator's fixed field
            order. That order is a TEMPLATE, so the ordering half of J is
            reported against a schema-order baseline as well as the analytic one.

    python datagen/build_identifier_j.py
"""

import datetime
import hashlib
import inspect
import io
import json
import os
import subprocess
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))

N_PRIMARY = 20
POOL_SIZE = 7
EXPOSED = {f"r_{i:04d}" for i in range(50)}
SRC = {"records": "data/identifier/records.jsonl", "fragments": "data/identifier/fragments.jsonl",
       "answer_key": "data/identifier/answer_key.jsonl"}
CELL = "results/identifier_J/identifier__field"
POOLS = "data/pools/identifier_J_pools.json"
SPEC = "runs/final_identifierJ.json"


def load(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def sha_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main():
    frags = load(SRC["fragments"])
    key = load(SRC["answer_key"])
    order = defaultdict(list)
    for k in sorted(key, key=lambda k: (k["record_id"], k["position"])):
        order[k["record_id"]].append(k["fragment_id"])
    eligible = sorted(r for r in order if r not in EXPOSED)
    ranked = sorted(eligible, key=lambda r: hashlib.sha256(f"identifier-J|{r}".encode()).hexdigest())
    pools = [(f"idpool_{i:03d}", ranked[i * POOL_SIZE:(i + 1) * POOL_SIZE])
             for i in range(len(ranked) // POOL_SIZE)]
    keep = {r for _p, ms in pools for r in ms}

    os.makedirs(CELL, exist_ok=True)
    with io.open(os.path.join(CELL, "prose_fragments.jsonl"), "w", encoding="utf-8") as fh:
        for f in frags:
            if f["record_id"] in keep:
                fh.write(json.dumps({"fragment_id": f["fragment_id"], "record_id": f["record_id"],
                                     "text": f["text"]}) + "\n")
    with io.open(os.path.join(CELL, "prose_answer_key.jsonl"), "w", encoding="utf-8") as fh:
        for r in sorted(keep):
            fh.write(json.dumps({"record_id": r, "order": order[r]}) + "\n")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    json.dump({"cell": "identifier__field", "strategy": "one fragment per field (name, ssn, account, address)",
               "granularity": "field", "source": SRC, "source_sha256": {k: sha_file(v) for k, v in SRC.items()},
               "records": len(keep), "excluded": "r_0000..r_0049 (shown to an LLM in exploratory O/L runs)",
               "order_note": "answer-key order is the generator's FIXED field template: report J against "
                             "a schema-order baseline as well as the analytic one (D11)",
               "git_commit": commit, "cut_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "n_fragments": 4 * len(keep), "fidelity_gate": "pass (one fragment per field, verbatim)"},
              open(os.path.join(CELL, "cell_manifest.json"), "w", encoding="utf-8"), indent=2)
    json.dump({"what": "identifier Game J pools (RUN_DECISIONS D11)",
               "rule": "records r_0050..r_0499 ordered by sha256('identifier-J|' + record_id), pools of 7 "
                       "in that order; primary = first 20; the rest are an unrun reserve. Ids only: no text, "
                       "score or outcome was read.",
               "primary": [p for p, _ in pools[:N_PRIMARY]], "reserve": [p for p, _ in pools[N_PRIMARY:]],
               "pools": [{"pool_id": p, "members": ms} for p, ms in pools]},
              open(POOLS, "w", encoding="utf-8"), indent=1)

    from batch_game import build_spec
    from batch_submit import build_requests, estimate_cost
    from masking import preflight_stats, reset_preflight_stats
    spec = build_spec([CELL], ["J"], docs=0, pool_size=POOL_SIZE, seed=42, tag="final-identifierJ",
                      pools=pools[:N_PRIMARY], o_docs=[])
    spec["NOT_SUBMITTED"] = "identifier J (D11): submit only on the user's explicit go"
    with io.open(SPEC, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=1)
    reset_preflight_stats()
    est = estimate_cost(build_requests(spec))
    pf = preflight_stats()
    json.dump({"spec": SPEC, "spec_sha256": sha_file(SPEC), "git_commit": commit,
               "pools": POOLS, "cell": CELL, "n_requests": len(spec["requests"]),
               "estimate": est, "preflight": {"checked": pf["checked"], "blocked": pf["blocked"]}},
              open(SPEC.replace(".json", "_manifest.json"), "w", encoding="utf-8"), indent=2)
    t, p = 7 * 6, (28 * 27) // 2
    print(f"identifier J: {len(eligible)} eligible records -> {len(pools)} pools of 7; primary {N_PRIMARY}")
    print(f"  spec: {len(spec['requests'])} requests, preflight {pf['checked']} checked / {pf['blocked']} blocked, "
          f"input ~${est['est_cost_input_only']:.3f}, worst case ${est['est_cost_worst_case']:.2f}")
    print(f"  baselines per pool (28 fragments): analytic J T/(P+T) = {t / (p + t):.3f}; "
          f"schema-order one bucket = {2 * t / (p + t):.3f}")


if __name__ == "__main__":
    main()
