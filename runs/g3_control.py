"""G3 -- the masking SIDE-CHANNEL diagnostic (RUN_DECISIONS D8). Approved by the
user 2026-09-11 (~$2). Development pool pool_000 only; never a headline pool.

The same J question is asked twice per cell:
  MASKED    the run's own presentation: shuffled labels, per-unit seeds
  UNMASKED  RAW fragment ids, in TRUE order -- a deliberately planted leak
Cells: semantic x sentence (reference) and random x sentence.

It is a diagnostic of the side channel, NOT a requirement that masked
reconstruction be low. The unmasked arm shows what an exploitable id leak looks
like. The masked arm is checked for any sign of following label numbers or the
presentation order beyond what its accuracy implies.

    python runs/g3_control.py --build     # build + freeze, no API
    python runs/g3_control.py --submit    # submit, wait, fetch, score, diagnose
"""
import hashlib, io, json, os, subprocess, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(ROOT, d))
from batch_game import build_spec, headline_docs, load_frame, score
from batch_submit import (DEFAULT_STATE_DIR, build_requests, estimate_cost, fetch,
                          read_state, results_path, state_path, submit)
from joint_game import build_units, score_row
from run_ledger import Ledger

TAG, SPEC = "g3-control", "runs/g3_control.json"
CELLS = ["results/grid_A/semantic__sentence", "results/grid_A/random__sentence"]
OUT = "results/g3_control"
frame = load_frame("data/pools/pools.json", "data/pools/linkage_grid.json")
pools = [frame[0]]
assert pools[0][0] == "pool_000" and not (set(pools[0][1]) & headline_docs())

if "--build" in sys.argv:
    kw = dict(docs=0, pool_size=7, seed=42, tag=TAG, pools=pools, o_docs=[],
              control=True, forbid_docs=headline_docs())
    m = build_spec(CELLS, ["J"], arm="masked", **kw)
    u = build_spec(CELLS, ["J"], arm="unmasked", **kw)
    spec = {**m, "requests": m["requests"] + u["requests"],
            "sidecar": {**m["sidecar"], **u["sidecar"]},
            "expected_usd": m["expected_usd"] + u["expected_usd"],
            "purpose": "G3 masking side-channel diagnostic (D8); development pool_000 only"}
    with io.open(SPEC, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=1)
    est = estimate_cost(build_requests(spec))
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    json.dump({"spec": SPEC, "spec_sha256": hashlib.sha256(open(SPEC, "rb").read()).hexdigest(),
               "git_commit": commit, "n_requests": len(spec["requests"]), "estimate": est,
               "expected_usd": spec["expected_usd"], "pools": [pools[0][0]], "cells": CELLS},
              open(SPEC.replace(".json", "_manifest.json"), "w", encoding="utf-8"), indent=2)
    print(f"G3: {len(spec['requests'])} requests (2 masked, 2 unmasked), expected ${spec['expected_usd']:.2f}, "
          f"worst ${est['est_cost_worst_case']:.2f}")

if "--submit" in sys.argv:
    spec = json.load(open(SPEC, encoding="utf-8"))
    sp = state_path(DEFAULT_STATE_DIR, TAG)
    state = read_state(sp) if os.path.exists(sp) else submit(spec, ledger=Ledger())
    res = fetch(state, wait=True, poll_seconds=60, ledger=Ledger())
    print(f"fetched {res['counts']}  actual ${res['actual_cost']:.4f}", flush=True)
    files = [results_path(DEFAULT_STATE_DIR, TAG)]
    score([(spec, files)], OUT)

    b = spec["build"]
    out = {"what": "G3 masking side-channel diagnostic (D8)", "actual_usd": res["actual_cost"], "cells": {}}
    for cd in CELLS:
        base = os.path.basename(cd)
        _o, _u, key, truth = build_units(cd, 0, 7, 42, pools=b["pools"], o_docs=[])
        for arm in ("masked", "unmasked"):
            cell = f"ctrl-{arm}-{base}"
            p = os.path.join(OUT, cell, "J.jsonl")
            if not os.path.exists(p):
                out["cells"][cell] = {"scored": False}
                continue
            raw = [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]
            if not raw:
                out["cells"][cell] = {"scored": False, "note": "non-completion or refused"}
                continue
            row = raw[0]
            s = score_row(row, key, truth)
            # Side channel: over pairs of same-record fragments placed in the same
            # guessed group, how often does the answer's order agree with the
            # TRUE order, the LABEL-NUMBER order, and the SHOWN order? Without a
            # side channel, agreement with labels / shown order is what truth
            # alone implies: P(A=T)P(T=X) + (1-P(A=T))(1-P(T=X)).
            inv = row["alias_map"]
            pos_true = {f: (r, i) for r, order in truth[row["unit"]].items() for i, f in enumerate(order)}
            shown_ix = {lab: i for i, lab in enumerate(row["shown_order"])}
            num = lambda lab: lab
            agree = {"T": 0, "L": 0, "S": 0, "TL": 0, "TS": 0}
            n = 0
            for g in row["raw_response"]:
                labs = [lab for lab in g if lab in inv]
                for x in range(len(labs)):
                    for y in range(x + 1, len(labs)):
                        a, c = labs[x], labs[y]
                        (ra, ia), (rc, ic) = pos_true[inv[a]], pos_true[inv[c]]
                        if ra != rc:
                            continue
                        n += 1
                        t = ia < ic
                        agree["T"] += t                         # answer puts a first; truth agrees?
                        agree["L"] += num(a) < num(c)
                        agree["S"] += shown_ix[a] < shown_ix[c]
                        agree["TL"] += t == (num(a) < num(c))
                        agree["TS"] += t == (shown_ix[a] < shown_ix[c])
            if n:
                pAT, pTL, pTS = agree["T"] / n, agree["TL"] / n, agree["TS"] / n
                exp = lambda pTX: pAT * pTX + (1 - pAT) * (1 - pTX)
                side = {"pairs": n, "answer_agrees_with_truth": pAT,
                        "answer_agrees_with_label_numbers": agree["L"] / n,
                        "expected_from_truth_alone_labels": exp(pTL),
                        "answer_agrees_with_shown_order": agree["S"] / n,
                        "expected_from_truth_alone_shown": exp(pTS)}
            else:
                side = {"pairs": 0}
            out["cells"][cell] = {"scored": True, "joint_f1": s.get("joint_f1"),
                                  "joint_advantage": s.get("joint_advantage"),
                                  "linkage_f1": s.get("f1"), "q": s.get("q"), "side_channel": side}
    os.makedirs("results/audit", exist_ok=True)
    json.dump(out, open("results/audit/g3_diagnostic.json", "w", encoding="utf-8"), indent=2)
    print(json.dumps(out, indent=2))
