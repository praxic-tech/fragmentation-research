"""
hier_batch.py — the hierarchical attacker on the Batches API.

WHY
---
hierarchical.py asks the model one pair batch at a time at interactive list
price, twice the batch rate. The attack cannot be flattened into one batch: it
has a data dependence -- clustering decides which BRIDGE pairs to ask next. So
it runs in WAVES, by REPLAY:

    wave k   replay attack() for every pool. Pairs already answered come from
             the pool's PairCache. The first stage that needs pairs nobody has
             asked yet raises NeedPairs; those pairs, chunked exactly as
             score_pairs_llm chunks them, become wave k's requests.
    ingest   answers are parsed with the interactive path's pair_id rules and
             appended to each pool's cache.
    repeat   until attack() runs to the end for every pool -- at most
             1 + MAX_BRIDGE_ROUNDS waves -- then score.

attack() is untouched and deterministic: candidates, orientation and bridges all
derive from seeds and cached answers, so a replay asks for exactly the pairs the
interactive attacker would have asked, in the same chunks. Nothing is simulated;
every answer used is a model answer to the prompt that was shown. The G2c test
checks the equivalence: batch waves against a pair oracle reproduce the
offline attack() result exactly.

RULES -- the one-shot path's (RUN_DECISIONS D6), applied per pair batch
  max_tokens  the model ceiling, 128k; one attempt per batch.
  exhausted   a batch that uses the whole 128k: its pairs are recorded
              unanswered and never re-asked.
  transport   an errored / expired batch is asked once more in the next wave; a
              second failure records its pairs unanswered.
  malformed   a pair missing, duplicated or out of range in an answer is
              unanswered. Pair batches have no repair round, and an unanswered
              pair is NOT re-asked when a later bridge round proposes it again.
              This is the one place the batch path differs from the interactive
              one, which never caches an unanswered pair and so would ask it
              again; with every pair answered the two ask identical questions.
  holes       a pool with more than HOLE_CAP (25%) of its requested pairs
              unanswered is REFUSED, never scored.
  masking     fragments are masked with joint_game.present (per-unit seeds).
              Pair prompts carry text only; every prompt is preflighted.

    python adversaries/hier_batch.py plan   --cell results/grid_A/semantic__sentence \\
            --pool pool_000 --wave 0 --tag hier-s1 --out-root results/hier/s1 --spec-out runs/hier_s1_w0.json
    python adversaries/hier_batch.py ingest --spec runs/hier_s1_w0.json \\
            --results results/batches/hier-s1-w0.results.jsonl
    python adversaries/hier_batch.py score  --cell ... --pool pool_000 --out-root results/hier/s1
"""

import argparse
import io
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (HERE, os.path.join(ROOT, "harness"), os.path.join(ROOT, "analysis")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from batch_game import at_ceiling, load_frame                       # noqa: E402
from batch_submit import (IN_PER_M, OUT_PER_M, IncompleteBatchError,  # noqa: E402
                          _latest_rows, make_custom_id)
from cost_model_v2 import MODEL_MAX_OUTPUT                          # noqa: E402
from hierarchical import (DEFAULT_PAIRS_PER_CALL, HOLE_CAP,          # noqa: E402
                          PairCache, attack, check_run_meta, derive,
                          orient, pair_prompt)
from joint_game import build_units, integrity_gate, present, report, sha  # noqa: E402
from llm_adversary import extract_json_array                        # noqa: E402
from masking import preflight                                       # noqa: E402

DEFAULT_MODEL = "claude-sonnet-5"
# D8: chosen by the blocker's coverage on development data under a rule fixed
# before any number was seen (analysis/hier_blocker_calibration.py), never by
# reconstruction F1. No k reached the adequacy thresholds; 20 is the fallback.
DEFAULT_K = 20
TRANSPORT_TRIES = 2
TOK_PER_CHAR = 0.393            # input tokens per prompt character, pool 1


class NeedPairs(Exception):
    """attack() reached pairs nobody has asked yet: they are the next wave."""

    def __init__(self, chunks):
        super().__init__(f"{len(chunks)} pair batches still to ask")
        self.chunks = chunks


def _rel(path):
    return os.path.relpath(os.path.abspath(path), ROOT).replace("\\", "/")


def pool_units(cell_dir, pools, seed):
    """[(pool_id, masked fragments, alias_map, n_records)] for the given pools."""
    _o, units, _key, _truth = build_units(cell_dir, 0, 7, seed, pools=pools, o_docs=[])
    out = []
    for pid, frags, n in units:
        items, id_map, _shown = present(frags, seed)
        out.append((pid, [{"fragment_id": lab, "text": t} for lab, t in items], id_map, n))
    return out


def _pending(hit):
    """Not answered and not given up on: still to be asked."""
    return hit is None or ("M" not in hit and not hit.get("unanswered"))


def _score_fn(cache, text_by_id, seed, pairs_per_call):
    """attack()'s score_fn, served from the cache; raises NeedPairs for the rest."""
    def score_fn(pairs):
        m, w, rows, todo = {}, {}, [], []
        for i, j, flip in orient(pairs, seed):
            hit = cache.get(i, j)
            if _pending(hit):
                todo.append((i, j, flip))
            elif not hit.get("unanswered"):
                m[(i, j)], w[(i, j)] = hit["M"], hit["W"]
                rows.append(hit)
            # an unanswered pair is a hole: absent from the evidence, counted
        if todo:
            chunks = []
            for s in range(0, len(todo), pairs_per_call):
                chunk = todo[s:s + pairs_per_call]
                shown = [(n + 1, text_by_id[j if flip else i], text_by_id[i if flip else j])
                         for n, (i, j, flip) in enumerate(chunk)]
                prompt = pair_prompt(shown)
                preflight(prompt, where="hierarchical pair batch")
                chunks.append({"pairs": {n + 1: [i, j, flip] for n, (i, j, flip) in enumerate(chunk)},
                               "prompt": prompt})
            raise NeedPairs(chunks)
        return m, w, rows
    return score_fn


def _pool_dir(out_root, cell, pid):
    return os.path.join(out_root, cell, pid)


def _open_cache(out_root, cell_dir, pool, seed, k, pairs_per_call, model):
    pid, _masked, id_map, _n = pool
    cell = os.path.basename(os.path.normpath(cell_dir))
    pdir = _pool_dir(out_root, cell, pid)
    check_run_meta(pdir, {"cell": _rel(cell_dir), "pool": pid, "seed": seed, "k": k,
                          "pairs_per_call": pairs_per_call, "model": model,
                          "alias_sha": sha(json.dumps(id_map, sort_keys=True))})
    return PairCache(os.path.join(pdir, "pairs.jsonl")), pdir


def replay(pool, cache, seed, k, pairs_per_call):
    """((groups, telemetry), []) if the attack completes, else (None, chunks)."""
    _pid, masked, _id_map, n = pool
    text_by_id = {f["fragment_id"]: f["text"] for f in masked}
    try:
        return attack(masked, n, _score_fn(cache, text_by_id, seed, pairs_per_call),
                      k=k, seed=seed), []
    except NeedPairs as need:
        return None, need.chunks


def expected_out(n_pairs, tax):
    """gpt-oss measured 250 + 70/pair per batch; sonnet unmeasured, so x tax."""
    return (250 + 70 * n_pairs) * tax


def plan(cells, pools, wave, tag, out_root, seed=42, k=DEFAULT_K,
         pairs_per_call=DEFAULT_PAIRS_PER_CALL, model=DEFAULT_MODEL):
    """One wave's Batches spec: every pair batch any pool still needs."""
    requests, sidecar, done = [], {}, []
    for cell_dir in cells:
        cell = os.path.basename(os.path.normpath(cell_dir))
        for pool in pool_units(cell_dir, pools, seed):
            cache, pdir = _open_cache(out_root, cell_dir, pool, seed, k, pairs_per_call, model)
            result, chunks = replay(pool, cache, seed, k, pairs_per_call)
            if result is not None:
                done.append(f"{cell}/{pool[0]}")
                continue
            for c, ch in enumerate(chunks):
                unit = f"{pool[0]}-w{wave}-c{c:03d}"
                cid = make_custom_id(cell, "H", unit)
                requests.append({"cell": cell, "game": "H", "unit": unit,
                                 "prompt": ch["prompt"], "max_tokens": MODEL_MAX_OUTPUT})
                sidecar[cid] = {"custom_id": cid, "cell": cell, "cell_dir": _rel(cell_dir),
                                "game": "H", "pool": pool[0], "wave": wave, "chunk": c,
                                "pairs": ch["pairs"], "prompt_sha": sha(ch["prompt"]),
                                "max_tokens": MODEL_MAX_OUTPUT, "model": model,
                                "cache": _rel(os.path.join(pdir, "pairs.jsonl"))}
    # String keys: the spec is saved as JSON and read back, and a float key
    # would come back as a string (the sample driver's first run died on it).
    est = {f"x{t:g}": round(sum(len(r["prompt"]) * TOK_PER_CHAR / 1e6 * IN_PER_M
                                + expected_out(len(s["pairs"]), t) / 1e6 * OUT_PER_M
                                for r, s in zip(requests, sidecar.values())), 4)
           for t in (1.0, 2.3, 5.0)}
    return {"tag": tag, "model": model, "attacker": "hierarchical", "wave": wave,
            "build": {"cells": [_rel(c) for c in cells], "pools": pools, "seed": seed,
                      "k": k, "pairs_per_call": pairs_per_call},
            "requests": requests, "sidecar": sidecar, "done": done,
            "expected_by_tax": est, "expected_usd": est["x2.3"]}


def ingest(spec, results_files):
    """File one fetched wave's answers into the pools' caches. Once per wave."""
    rows = _latest_rows(results_files)
    missing = [c for c in spec["sidecar"] if c not in rows]
    if missing:
        raise IncompleteBatchError(f"{len(missing)} pair batches never came back, e.g. "
                                   f"{missing[:3]}; fetch the rest before ingesting")
    stats, caches = Counter(), {}
    marks = {}
    for cid, s in spec["sidecar"].items():
        path = os.path.join(ROOT, s["cache"])
        mark = os.path.join(os.path.dirname(path), "ingested.json")
        if mark not in marks:
            marks[mark] = json.load(open(mark, encoding="utf-8")) if os.path.exists(mark) else []
            if spec["tag"] in marks[mark]:
                raise ValueError(f"{spec['tag']} was already ingested into {os.path.dirname(path)}")
        cache = caches.setdefault(path, PairCache(path))
        pairs = {int(pid): v for pid, v in s["pairs"].items()}
        r = rows[cid]

        def give_up(reason):
            for i, j, _f in pairs.values():
                cache.add({"pair": [i, j], "unanswered": True, "reason": reason,
                           "custom_id": cid})

        if r.get("result_type") != "succeeded":
            stats["transport"] += 1
            for i, j, _f in pairs.values():
                n = (cache.get(i, j) or {}).get("transport_failures", 0) + 1
                cache.add({"pair": [i, j], "transport_failures": n} if n < TRANSPORT_TRIES
                          else {"pair": [i, j], "unanswered": True,
                                "reason": f"transport failure x{n}", "custom_id": cid})
            continue
        if at_ceiling(r):
            stats["exhausted_128k"] += 1
            give_up("exhausted the 128k output ceiling (D6); not re-asked")
            continue
        if r.get("error") or not str(r.get("text", "")).strip():
            stats["empty"] += 1
            give_up(f"no answer: {r.get('error') or 'empty'}")
            continue
        try:
            answer = extract_json_array(r["text"])
        except ValueError:
            answer = []
        seen = set()
        for item in answer if isinstance(answer, list) else []:
            try:
                pid, same, before = int(item["pair_id"]), float(item["same"]), float(item["before"])
            except (KeyError, TypeError, ValueError):
                stats["malformed_pairs"] += 1
                continue
            if pid not in pairs or pid in seen or not (0 <= same <= 1 and 0 <= before <= 1):
                stats["malformed_pairs"] += 1
                continue
            seen.add(pid)
            i, j, flip = pairs[pid]
            cache.add({"pair": [i, j], "pair_id": pid, "flipped": flip, "same": same,
                       "before": before, **derive(i, j, flip, same, before),
                       "custom_id": cid})
            stats["answered_pairs"] += 1
        for pid, (i, j, _f) in pairs.items():
            if pid not in seen:
                cache.add({"pair": [i, j], "unanswered": True,
                           "reason": "missing or malformed in the answer", "custom_id": cid})
                stats["unanswered_pairs"] += 1
        stats["answered_batches"] += 1
    for mark, tags in marks.items():
        with io.open(mark, "w", encoding="utf-8") as fh:
            json.dump(tags + [spec["tag"]], fh)
    return dict(stats)


def score(cells, pools, out_root, seed=42, k=DEFAULT_K,
          pairs_per_call=DEFAULT_PAIRS_PER_CALL, model=DEFAULT_MODEL):
    """Write joint_game J rows and run the SAME integrity gate and report.
    Returns {cell: refused games}."""
    verdict = {}
    for cell_dir in cells:
        cell = os.path.basename(os.path.normpath(cell_dir))
        out_dir = os.path.join(out_root, cell)
        rows_out = []
        for pool in pool_units(cell_dir, pools, seed):
            pid, masked, id_map, n = pool
            cache, _pdir = _open_cache(out_root, cell_dir, pool, seed, k, pairs_per_call, model)
            result, chunks = replay(pool, cache, seed, k, pairs_per_call)
            if result is None:
                raise RuntimeError(f"{cell}/{pid} still needs {len(chunks)} pair batches: "
                                   "plan, submit and ingest another wave first")
            groups, tel = result
            asked = list(cache.rows.values())
            holes = sum(1 for r in asked if r.get("unanswered")) / len(asked) if asked else 0.0
            if holes > HOLE_CAP:
                print(f"  REFUSED {cell}/{pid}: {holes:.0%} of requested pairs have no "
                      f"answer (cap {HOLE_CAP:.0%}); not scored")
                continue
            rows_out.append({
                "game": "J", "unit": pid, "attacker": "hierarchical", "model": model,
                "seed": seed, "k": k, "n_fragments": len(masked), "n_records": n,
                "alias_map": id_map, "raw_response": groups,
                "repair": {"policy_share": 0.0, "model_answers": 1},
                "hole_share": holes, "pairs_asked": len(asked),
                "telemetry": {kk: tel[kk] for kk in ("bridge_rounds", "n_clusters", "exact_n",
                                                     "coverage", "clusters_disconnected",
                                                     "arbitrary_pairs_total", "scored_edges")},
                "evidence_free_merges": tel["clustering"].get("evidence_free_merges")})
        os.makedirs(out_dir, exist_ok=True)
        with io.open(os.path.join(out_dir, "J.jsonl"), "w", encoding="utf-8") as fh:
            for r in rows_out:
                fh.write(json.dumps(r) + "\n")
        io.open(os.path.join(out_dir, "J.rbnc.jsonl"), "w", encoding="utf-8").close()
        _o, _u, key, pool_truth = build_units(cell_dir, 0, 7, seed, pools=pools, o_docs=[])
        print("\n" + "=" * 74 + f"\n CELL {cell}   (hierarchical attacker)")
        refused = integrity_gate(out_dir, key, pool_truth, {"J": [p for p, _m in pools]})
        report(out_dir, key, pool_truth, withhold=refused)
        verdict[cell] = refused
    return verdict


def _pools_arg(a):
    frame = load_frame(a.pools_file, a.pool_ids_file)
    return [(p, m) for p, m in frame if p in set(a.pool)]


def main():
    ap = argparse.ArgumentParser(description="The hierarchical attacker, in batch waves.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "score"):
        p = sub.add_parser(name)
        p.add_argument("--cell", nargs="+", required=True)
        p.add_argument("--pool", nargs="+", required=True)
        p.add_argument("--pools-file", default=os.path.join(ROOT, "data", "pools", "pools.json"))
        p.add_argument("--pool-ids-file", default=None)
        p.add_argument("--out-root", required=True)
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--k", type=int, default=DEFAULT_K)
        if name == "plan":
            p.add_argument("--wave", type=int, required=True)
            p.add_argument("--tag", required=True)
            p.add_argument("--spec-out", required=True)
    g = sub.add_parser("ingest")
    g.add_argument("--spec", required=True)
    g.add_argument("--results", nargs="+", required=True)
    a = ap.parse_args()
    if a.cmd == "plan":
        spec = plan(a.cell, _pools_arg(a), a.wave, a.tag, a.out_root, seed=a.seed, k=a.k)
        os.makedirs(os.path.dirname(os.path.abspath(a.spec_out)), exist_ok=True)
        with io.open(a.spec_out, "w", encoding="utf-8") as fh:
            json.dump(spec, fh, indent=1)
        e = spec["expected_by_tax"]
        print(f"wave {a.wave}: {len(spec['requests'])} pair batches; complete: {spec['done']}; "
              f"expected ${e['x1']:.2f} / ${e['x2.3']:.2f} / ${e['x5']:.2f} at x1 / x2.3 / x5")
    elif a.cmd == "ingest":
        spec = json.load(open(a.spec, encoding="utf-8"))
        print(ingest(spec, a.results))
    else:
        v = score(a.cell, _pools_arg(a), a.out_root, seed=a.seed, k=a.k)
        if any(v.values()):
            sys.exit(1)


if __name__ == "__main__":
    main()
