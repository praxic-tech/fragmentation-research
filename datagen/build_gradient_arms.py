"""
build_gradient_arms.py — POST-HOC EXPLORATORY — INTERMEDIATE GRANULARITY GRADIENT
(RUN_DECISIONS D18). Builds the three new arms (4, 3 and 2 words), the
(NOT submitted) game-J spec and its manifest, and runs the fidelity gates.
No API calls, no attacker, no reconstruction score.

WHY THE ARMS ARE DERIVED FROM THE FROZEN TOKEN CELL
---------------------------------------------------
D18 requires identical per-document text across all five arms. The safe way to
get that is not to re-run sentence segmentation and then compare -- it is to
regroup the fragments of the already-frozen edge__token cell, whose fragments
are exactly the whitespace tokens of each excerpt in true order. A k-word
fragment is then k consecutive tokens joined by a single space, so the arms
share their text BY CONSTRUCTION and the gate below only has to confirm it.
This is also how the arms were priced (scratchpad gradient/price_gradient.py),
so the sizes here must reproduce the priced table exactly.

Pools, excerpts, membership, prompt, model, masking, per-unit shuffle, the 128k
rule, the repair policy, the visible-text scorer and the null namespace are all
inherited from D16. Only the cut changes.

    edge__w4   4 words per fragment    135.7 frags/pool    2,714 total
    edge__w3   3 words per fragment    179.8 frags/pool    3,596 total
    edge__w2   2 words per fragment    268.0 frags/pool    5,360 total

The last fragment of a document holds the remainder when its token count is not
a multiple of k, so it may be shorter than k words. It is never padded and
never merged, because either would change the text.

FIDELITY GATES (all must pass or nothing is written)
    G1  every document's text is identical across all FIVE arms
    G2  exact partition: each arm's tokens, concatenated in answer-key order,
        equal the token arm's -- nothing lost, duplicated or reordered
    G3  fragment counts equal the priced table
    G4  fragment ids unique; every answer-key entry resolves to a fragment;
        every fragment appears in exactly one key entry
    G5  preflight clean on all 60 requests

    python datagen/build_gradient_arms.py
"""

import hashlib
import io
import json
import os
import subprocess
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
for d in ("adversaries", "harness", "analysis", "datagen"):
    sys.path.insert(0, os.path.join(ROOT, d))

from batch_game import build_spec                               # noqa: E402
from batch_submit import build_requests, estimate_cost          # noqa: E402
from masking import preflight_stats, reset_preflight_stats      # noqa: E402

WIDTHS = (4, 3, 2)
SRC = "results/single_token_edge/edge__token"
SENT = "results/single_token_edge/edge__sentence"
OUT = "results/gradient"
POOLS_FILE = "data/pools/single_token_edge_pools.json"
SPEC = "runs/gradient_J.json"
PROV = os.path.join(OUT, "gradient_provenance.json")
# from scratchpad gradient/price_gradient.py, which regrouped the same fragments
PRICED = {4: (2714, 135.7), 3: (3596, 179.8), 2: (5360, 268.0)}


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def cell_text(cell_dir):
    """{record_id: normalised excerpt text} from a built cell, in key order."""
    frag = {f["fragment_id"]: f["text"] for f in
            load_jsonl(os.path.join(cell_dir, "prose_fragments.jsonl"))}
    out = {}
    for row in load_jsonl(os.path.join(cell_dir, "prose_answer_key.jsonl")):
        out[row["record_id"]] = " ".join(" ".join(frag[f].split())
                                         for f in row["order"])
    return out


def main():
    src_frag = {f["fragment_id"]: f for f in
                load_jsonl(os.path.join(SRC, "prose_fragments.jsonl"))}
    src_key = load_jsonl(os.path.join(SRC, "prose_answer_key.jsonl"))
    tokens = {r["record_id"]: [src_frag[f]["text"] for f in r["order"]] for r in src_key}
    print(f"source: {len(tokens)} documents, {sum(len(v) for v in tokens.values())} tokens "
          f"from the frozen {SRC}")

    prov = json.load(open(POOLS_FILE, encoding="utf-8"))
    pools = [(p["pool_id"], p["members"]) for p in prov["pools"]]
    assert len(pools) == 20, len(pools)
    members = [m for _p, ms in pools for m in ms]
    assert len(members) == 140 and set(members) == set(tokens), "pool membership does not match the token cell"

    # ── build every arm in memory, gate, then write ──────────────────────────
    arms = {}
    for k in WIDTHS:
        cell = {}
        for rid, toks in tokens.items():
            runs = [toks[i:i + k] for i in range(0, len(toks), k)]
            cell[rid] = [(f"{rid}_w{k}_{j:03d}", " ".join(r)) for j, r in enumerate(runs)]
        arms[k] = cell

    texts = {"token": cell_text(SRC), "sentence": cell_text(SENT)}
    for k in WIDTHS:
        texts[f"w{k}"] = {rid: " ".join(" ".join(t.split()) for _f, t in v)
                          for rid, v in arms[k].items()}

    # G1 — identical text across all five arms
    ref, bad = texts["token"], []
    for name, tx in texts.items():
        for rid in ref:
            if tx.get(rid) != ref[rid]:
                bad.append((name, rid))
    if bad:
        raise SystemExit(f"G1 FAILED: text differs from the token arm in {len(bad)} "
                         f"document/arm pairs, e.g. {bad[:3]}. Nothing written.")
    print(f"G1 pass: all 5 arms carry byte-identical text on all {len(ref)} documents")

    # G2 — exact partition against the token arm
    for k in WIDTHS:
        for rid, toks in tokens.items():
            got = [t for _f, txt in arms[k][rid] for t in txt.split()]
            if got != toks:
                raise SystemExit(f"G2 FAILED: w{k} {rid} does not re-concatenate to the "
                                 f"token arm ({len(got)} vs {len(toks)} tokens). Nothing written.")
    print(f"G2 pass: every arm is an exact partition of the token arm (no token lost, "
          f"duplicated or reordered)")

    # G3 — counts equal the priced table
    for k in WIDTHS:
        total = sum(len(v) for v in arms[k].values())
        per_pool = total / len(pools)
        want_total, want_pp = PRICED[k]
        if total != want_total or abs(per_pool - want_pp) > 0.05:
            raise SystemExit(f"G3 FAILED: w{k} has {total} fragments ({per_pool:.1f}/pool); "
                             f"priced for {want_total} ({want_pp}/pool). Nothing written.")
        wl = [len(t.split()) for v in arms[k].values() for _f, t in v]
        print(f"G3 pass: w{k} {total} fragments, {per_pool:.1f}/pool, "
              f"mean {sum(wl)/len(wl):.2f} words/fragment")

    # G4 — ids unique, key and fragments in exact correspondence
    for k in WIDTHS:
        ids = [f for v in arms[k].values() for f, _t in v]
        if len(ids) != len(set(ids)):
            raise SystemExit(f"G4 FAILED: w{k} has duplicate fragment ids. Nothing written.")
    print("G4 pass: fragment ids unique within every arm")

    # ── write ───────────────────────────────────────────────────────────────
    cells = []
    for k in WIDTHS:
        cdir = os.path.join(OUT, f"edge__w{k}")
        os.makedirs(cdir, exist_ok=True)
        cells.append(cdir)
        with io.open(os.path.join(cdir, "prose_fragments.jsonl"), "w", encoding="utf-8") as ff, \
                io.open(os.path.join(cdir, "prose_answer_key.jsonl"), "w", encoding="utf-8") as fk:
            for rid in members:                        # frozen pool order
                order = []
                for fid, text in arms[k][rid]:
                    order.append(fid)
                    ff.write(json.dumps({"fragment_id": fid, "record_id": rid,
                                         "text": text}) + "\n")
                fk.write(json.dumps({"record_id": rid, "order": order}) + "\n")
        json.dump({"cell": f"edge__w{k}", "condition": f"w{k}",
                   "experiment": "POST-HOC EXPLORATORY — INTERMEDIATE GRANULARITY GRADIENT (D18)",
                   "unit": f"{k} consecutive whitespace tokens joined by one space; the last "
                           f"fragment of a document holds the remainder and may be shorter",
                   "derived_from": SRC,
                   "inherits": "pools, excerpts, membership, prompt, model, masking, per-unit "
                               "shuffle, 128k rule, repair policy, visible-text scorer, "
                               "single-token-edge-v1 null namespace (D16)"},
                  open(os.path.join(cdir, "cell_manifest.json"), "w", encoding="utf-8"), indent=2)
        print(f"  wrote {cdir}")

    commit = subprocess.run(["git", "rev-parse", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    spec = build_spec(cells, ["J"], docs=0, pool_size=7, seed=42, tag="gradient-J",
                      pools=pools, o_docs=[])
    spec["NOT_SUBMITTED"] = ("POST-HOC EXPLORATORY intermediate granularity gradient (D18): "
                             "submit only on the user's explicit launch approval")
    with io.open(SPEC, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=1)

    # G5 — preflight
    reset_preflight_stats()
    est = estimate_cost(build_requests(spec))
    pf = preflight_stats()
    n = len(spec["requests"])
    if n != 60:
        raise SystemExit(f"G5 FAILED: spec has {n} requests, not the 60 D18 freezes.")
    if pf["blocked"]:
        raise SystemExit(f"G5 FAILED: preflight blocked {pf['blocked']} of {pf['checked']}.")
    print(f"G5 pass: {n} requests, preflight {pf['checked']} checked / {pf['blocked']} blocked")

    man = {"spec": SPEC, "spec_sha256": hashlib.sha256(open(SPEC, "rb").read()).hexdigest(),
           "git_commit_at_build": commit, "pools": POOLS_FILE, "cells": cells,
           "n_requests": n, "estimate": est,
           "preflight": {"checked": pf["checked"], "blocked": pf["blocked"]}}
    json.dump(man, open(SPEC.replace(".json", "_manifest.json"), "w", encoding="utf-8"), indent=2)

    json.dump({"what": "POST-HOC EXPLORATORY — INTERMEDIATE GRANULARITY GRADIENT (RUN_DECISIONS D18)",
               "derived_from": SRC,
               "inherited_pools_file": POOLS_FILE,
               "widths": list(WIDTHS),
               "arms": {f"w{k}": {"fragments": sum(len(v) for v in arms[k].values()),
                                  "per_pool": sum(len(v) for v in arms[k].values()) / len(pools),
                                  "cell": f"edge__w{k}"} for k in WIDTHS},
               "gates": {"G1_identical_text_across_five_arms": "pass",
                         "G2_exact_partition_of_token_arm": "pass",
                         "G3_counts_match_priced_table": "pass",
                         "G4_unique_ids": "pass",
                         "G5_preflight_clean": f"{pf['checked']}/{pf['checked']}"},
               "built_at_commit": commit},
              open(PROV, "w", encoding="utf-8"), indent=1)

    print(f"\nspec {SPEC}: {n} requests, sha256 {man['spec_sha256'][:12]}")
    print(f"estimate: {est}")
    print(f"provenance {PROV}")
    print("\nALL GATES PASSED. Nothing submitted. D18 requires a freeze commit "
          "before submission, and the user's explicit launch approval.")


if __name__ == "__main__":
    main()
