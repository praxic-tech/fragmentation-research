"""
batch_game.py — the PAID path for the joint grid: spec -> batch -> resubmit ->
repair waves -> scored cells, using exactly the prompts and the scorer that the
interactive free-tier runs used.

WHY IT EXISTS
-------------
The interactive path (joint_game) builds a prompt, calls a model, repairs and
scores inside one process. The paid run cannot: it goes through the Batches API,
where a request and its answer are hours apart and a repair round is a second
batch. Before this file the batch path could submit and fetch, but nothing
turned a fetched answer back into a score -- and the only spec builder,
make_control_spec, discarded the alias maps (`masked, _ = mask_fragment_ids()`),
so even the G3 positive control was unscoreable.

THE CONTRACT WITH joint_game
----------------------------
Prompts come from joint_game.present / prompt_O / prompt_L / prompt_J. Rows are
written in joint_game's row schema and scored by joint_game.integrity_gate and
joint_game.report. There is no second scorer, so a paid number and a free-tier
number cannot disagree about what a score means.

FLOW
----
    build      one request per (cell, game, unit). max_tokens per request from
               cost_model_v2.max_tokens_for -- the SAME anchors that price the
               run, so the forecast and the cap cannot drift apart. A SIDECAR
               holds every alias map and shown order: the only way back from
               labels to fragment ids.
    submit     batch_submit.submit   (ledger reserve -> create -> attach)
    fetch      batch_submit.fetch    (streamed, resumable, settles the ledger)
    resubmit   requests that came back errored / expired / empty, unchanged.
               A transport hole, not a model answer. One cut off at max_tokens
               goes back with the same prompt and a larger cap.
    repair     units whose answer is unparseable or incomplete: the original
               prompt plus bookkeeping-only feedback. An unparseable answer gets
               the original prompt again -- there is no answer to correct.
    score      require_complete on every wave, merge attempts per unit,
               finalise, write joint_game rows, integrity gate, report.

The same rules as the interactive path: a unit with no real model answer in any
round is never written, so its cell is REFUSED rather than scored around.

    python adversaries/batch_game.py build --cells results/o_probe/random__sentence \\
        --games J O --docs 8 --pool-size 7 --tag grid-w0 --out runs/grid_w0.json
    python adversaries/batch_submit.py --spec runs/grid_w0.json --submit
    python adversaries/batch_submit.py --fetch runs/batches/grid-w0_state.json --wait
    python adversaries/batch_game.py resubmit --spec runs/grid_w0.json \\
        --results <results files> --tag grid-w0-rs1 --out runs/grid_w0_rs1.json
    python adversaries/batch_game.py repair --wave runs/grid_w0.json <results files> \\
        --round 1 --max-rounds 1 --tag grid-w1 --out runs/grid_w1.json
    python adversaries/batch_game.py score --wave runs/grid_w0.json <files> \\
        --wave runs/grid_w1.json <files> --out-root results/paid/grid
"""

import argparse
import io
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "harness"))
sys.path.insert(0, os.path.join(ROOT, "analysis"))

from answer_store import _cut_off as cut_off                       # noqa: E402
from batch_submit import (IN_PER_M, OUT_PER_M,                      # noqa: E402
                          IncompleteBatchError, _latest_rows,
                          failed_ids, make_custom_id)
from cost_model_v2 import (MODEL_MAX_OUTPUT, SIZING_MARGIN,         # noqa: E402
                           expected_out_tokens, max_tokens_for)
from joint_game import (_as_groups, build_units, integrity_gate,     # noqa: E402
                        present, prompt_J, prompt_L, prompt_O, report, sha)
from llm_adversary import extract_json_array                        # noqa: E402
from repair import finalise, repair_report_text, validate            # noqa: E402

DEFAULT_MODEL = "claude-sonnet-5"


def _rel(path):
    return os.path.relpath(os.path.abspath(path), ROOT).replace("\\", "/")


def _abs(rel):
    return os.path.join(ROOT, rel)


# ── build ────────────────────────────────────────────────────────────────────

def load_frame(pools_file, pool_ids_file=None):
    """Pre-registered pools as [(pool_id, [record_id, ...])], in file order.

    pool_ids_file (e.g. data/pools/linkage_grid.json) restricts to a subset.
    """
    with io.open(pools_file, encoding="utf-8") as fh:
        pools = json.load(fh)["pools"]
    keep = None
    if pool_ids_file:
        with io.open(pool_ids_file, encoding="utf-8") as fh:
            keep = set(json.load(fh)["pool_ids"])
    return [(p["pool_id"], list(p["members"])) for p in pools
            if keep is None or p["pool_id"] in keep]


def headline_docs(pools_file=None, grid_ids_file=None):
    """Every document in the 46 HEADLINE pools: pools.json minus the grid pools.

    docs/RUN_DECISIONS.md D2: these stay completely untouched until the headline
    run -- no testing, no tuning, no requests of any kind.
    """
    pools_file = pools_file or os.path.join(ROOT, "data", "pools", "pools.json")
    grid_ids_file = grid_ids_file or os.path.join(ROOT, "data", "pools",
                                                  "linkage_grid.json")
    grid = {pid for pid, _m in load_frame(pools_file, grid_ids_file)}
    return {m for pid, members in load_frame(pools_file) if pid not in grid
            for m in members}


def expected_cost(spec):
    """The spec's forecast at the rates measured on pool 1 -- what the tripwire
    reserves (x RESERVE_MARGIN). A request cut off before is expected to need
    at least the tokens it already used."""
    usd = 0.0
    for r in spec["requests"]:
        s = spec["sidecar"][make_custom_id(r["cell"], r["game"], r["unit"])]
        out = max(expected_out_tokens(s["game"], s["n_fragments"], s["n_records"]),
                  s.get("cut_off_at", 0))
        usd += (len(r["prompt"]) / 4 / 1e6 * IN_PER_M
                + min(out, r["max_tokens"]) / 1e6 * OUT_PER_M)
    return round(usd, 6)


def build_spec(cells, games, docs, pool_size, seed, tag, model=DEFAULT_MODEL,
               margin=SIZING_MARGIN, arm="masked", control=False, pools=None,
               o_docs=None, forbid_docs=None):
    """One request per (cell, game, unit), with a sidecar that makes it scoreable.

    arm="unmasked" is the G3 positive control: RAW fragment ids, presented in
    true order -- the leak deliberately reproduced, flagged per request so
    preflight skips it visibly rather than silently. It must score near 1.0 or
    the test cannot say anything about masking.
    """
    if arm not in ("masked", "unmasked"):
        raise ValueError(f"arm must be masked or unmasked, got {arm!r}")
    requests, sidecar = [], {}
    for cell_dir in cells:
        base = os.path.basename(os.path.normpath(cell_dir))
        cell = f"ctrl-{arm}-{base}" if control else base
        o_units, pool_units, _key, _truth = build_units(
            cell_dir, docs, pool_size, seed, pools=pools, o_docs=o_docs)
        if forbid_docs:
            # D2 as a refusal, not a promise: a request carrying any document
            # from the untouched headline pools cannot be built.
            used = {f["record_id"] for g in games
                    for _u, frags, _n in (o_units if g == "O" else pool_units)
                    for f in frags}
            bad = sorted(used & set(forbid_docs))
            if bad:
                raise ValueError(
                    f"{len(bad)} documents in {cell} belong to the untouched "
                    f"headline pools, e.g. {bad[:3]}. Headline documents may "
                    "not be requested before the headline run (RUN_DECISIONS D2).")
        for game in games:
            for unit_id, frags, n_records in (o_units if game == "O" else pool_units):
                if arm == "unmasked":
                    items = [(f["fragment_id"], f["text"]) for f in frags]
                    id_map = {f["fragment_id"]: f["fragment_id"] for f in frags}
                    shown = [f["fragment_id"] for f in frags]
                else:
                    items, id_map, shown = present(frags, seed)
                if game == "O":
                    prompt = prompt_O(items)
                elif game == "L":
                    prompt = prompt_L(items, n_records)
                else:
                    prompt = prompt_J(items, n_records)
                mt = max_tokens_for(game, len(items), n_records, margin=margin)
                cid = make_custom_id(cell, game, unit_id)
                req = {"cell": cell, "game": game, "unit": unit_id,
                       "prompt": prompt, "max_tokens": mt}
                if arm == "unmasked":
                    req["unmasked_control"] = True
                requests.append(req)
                sidecar[cid] = {
                    "custom_id": cid, "base_cid": cid, "round": 0,
                    "cell": cell, "cell_dir": _rel(cell_dir), "game": game,
                    "unit": unit_id, "n_records": n_records,
                    "n_fragments": len(items), "max_tokens": mt,
                    "alias_map": id_map, "shown_order": shown,
                    "prompt": prompt, "prompt_sha": sha(prompt),
                    "unmasked_control": arm == "unmasked", "model": model,
                }
    spec = {"tag": tag, "model": model,
            "build": {"docs": docs, "pool_size": pool_size, "seed": seed,
                      "margin": margin, "arm": arm, "games": list(games),
                      "cells": [_rel(c) for c in cells],
                      # the frame travels with the spec, so scoring rebuilds
                      # exactly the units that were asked
                      "pools": pools, "o_docs": o_docs,
                      "forbidden_docs": len(forbid_docs or ())},
            "requests": requests, "sidecar": sidecar}
    spec["expected_usd"] = expected_cost(spec)
    return spec


def build_resubmit_spec(spec, results_files, tag):
    """The same requests for every id without a real answer yet.

    A resubmission is a TRANSPORT retry. It shares custom_ids with the original
    wave; its results file is added to that wave's file list at scoring time.

    The prompt never changes. The one thing that can: an answer cut off at
    max_tokens goes back with a larger cap, because sent unchanged it would be
    cut off in the same place. First to the current sizing, then to the model
    ceiling. One already cut off AT the ceiling is not sent again -- it is
    listed in "at_ceiling" and its unit stays a hole the integrity gate refuses.
    """
    have = _latest_rows(results_files)
    side = spec["sidecar"]
    cut = {c: have[c] for c in side if c in have and cut_off(have[c], side[c])}
    bad = set(failed_ids(results_files)) | (set(side) - set(have)) | set(cut)
    requests, sidecar, at_ceiling = [], {}, []
    for r in spec["requests"]:
        cid = make_custom_id(r["cell"], r["game"], r["unit"])
        if cid not in bad:
            continue
        s = side[cid]
        if cid in cut:
            hit = (cut[cid].get("usage") or {}).get("output_tokens", 0)
            if hit >= MODEL_MAX_OUTPUT:
                at_ceiling.append(cid)
                continue
            mt = max_tokens_for(s["game"], s["n_fragments"], s["n_records"])
            mt = mt if mt > hit else MODEL_MAX_OUTPUT
            r = {**r, "max_tokens": mt}
            s = {**s, "max_tokens": mt, "cut_off_at": hit}
        requests.append(r)
        sidecar[cid] = s
    out = {**spec, "tag": tag, "resubmit_of": spec["tag"], "requests": requests,
           "sidecar": sidecar, "at_ceiling": sorted(at_ceiling)}
    out["expected_usd"] = expected_cost(out)
    return out


# ── read waves back ──────────────────────────────────────────────────────────

def at_ceiling(row):
    """The call exhausted the model's whole output ceiling (RUN_DECISIONS D6)."""
    used = (row.get("usage") or {}).get("output_tokens", 0)
    return row.get("stop_reason") == "max_tokens" and used >= MODEL_MAX_OUTPUT


def _attempt(side, row):
    """One answer, parsed and validated against the unit's own labels.

    An unparseable answer is recorded as an attempt WITH AN ERROR, exactly as
    the interactive path records call_model's "did not return valid JSON": it
    is not a model answer to score, and if no round produces one the unit is
    never written.
    """
    labels = set(side["alias_map"])
    if at_ceiling(row):
        # D6: the call exhausted the model's whole output. Not a model answer,
        # not a transport hole -- a resource-bounded non-completion, never re-asked.
        return {"attempt": side["round"], "custom_id": row["custom_id"],
                "error": "resource-bounded non-completion", "rbnc": True,
                "groups": [], "report": None, "fetched_at": row.get("fetched_at"),
                "n_returned": 0, "n_distinct": 0, "n_expected": len(labels),
                "valid": False, "n_invalid": 0, "n_duplicated": 0,
                "n_missing": len(labels), "n_groups": 0, "group_count_error": False}
    try:
        groups = _as_groups(extract_json_array(row.get("text", "")))
        error = None
    except Exception as exc:                          # noqa: BLE001
        groups, error = [], f"unparseable answer: {type(exc).__name__}"
    rep = validate(groups, labels)
    return {"attempt": side["round"], "custom_id": row["custom_id"],
            "error": error, "groups": groups, "report": rep,
            "fetched_at": row.get("fetched_at"),
            **{k: rep[k] for k in ("n_returned", "n_distinct", "n_expected",
                                   "valid")},
            "n_invalid": len(rep["invalid"]),
            "n_duplicated": len(rep["duplicated"]),
            "n_missing": len(rep["missing"]),
            "n_groups": rep["n_groups"],
            "group_count_error": rep["group_count_error"]}


def merge_waves(waves):
    """waves: [(spec, [results files])]. Every wave must be COMPLETE.

    require_complete raises IncompleteBatchError on any missing, errored,
    expired, canceled or empty request -- those are resubmitted, never scored
    around.
    """
    side, attempts = {}, defaultdict(list)
    for spec, files in waves:
        cids = list(spec["sidecar"])
        rows = _latest_rows(files)
        missing = [c for c in cids if c not in rows]
        # A call that exhausted the full 128k is a non-completion (D6), not a
        # hole: it is kept as an attempt and never resubmitted. Every other
        # failure is a hole and refuses scoring, exactly as before.
        bad = sorted(c for c in set(failed_ids(files)) & set(cids)
                     if not at_ceiling(rows[c]))
        if missing or bad:
            raise IncompleteBatchError(
                f"{len(missing)} of {len(cids)} requests never came back and "
                f"{len(bad)} came back without an answer, e.g. "
                f"{(missing + bad)[:3]}. Resubmit them; do not score around them.")
        # A cut-off answer can arrive as "succeeded" with text in it -- pool 1
        # had one, a JSON list ending mid-label. Rows fetched before stop_reason
        # was recorded are caught by having used their whole cap.
        cut = sorted(c for c in cids if not at_ceiling(rows[c])
                     and cut_off(rows[c], spec["sidecar"][c]))
        if cut:
            raise IncompleteBatchError(
                f"{len(cut)} answers were cut off at max_tokens, e.g. "
                f"{cut[:3]}. Resubmit them with a larger cap "
                "(build_resubmit_spec does); a cut-off answer is not scored.")
        for cid in cids:
            s = spec["sidecar"][cid]
            if s["round"] == 0 or s["base_cid"] not in side:
                side[s["base_cid"]] = s
            attempts[s["base_cid"]].append(_attempt(s, rows[cid]))
    for base in attempts:
        attempts[base].sort(key=lambda a: a["attempt"])
    return attempts, side


def build_repair_spec(waves, round_no, max_rounds, tag, model=None):
    """A follow-up wave for every unit whose latest answer is not valid."""
    attempts, side = merge_waves(waves)
    requests, sidecar = [], {}
    for base, atts in sorted(attempts.items()):
        last = atts[-1]
        if last["error"] is None and last["valid"]:
            continue
        if last.get("rbnc"):
            continue                              # D6: exhausted 128k, never re-asked
        if len(atts) - 1 >= max_rounds:
            continue                              # budget spent; score as-is
        s = side[base]
        feedback = (repair_report_text(last["report"])
                    if last["error"] is None else "")
        sent = s["prompt"] + ("\n\n" + feedback if feedback else "")
        unit_r = f"{s['unit']}-r{round_no}"
        cid = make_custom_id(s["cell"], s["game"], unit_r)
        # Always the model ceiling. The sidecar holds the ROUND-0 cap, which
        # knows nothing of a resubmission that needed more: pool 1's repair of
        # random__token-window prose_0156 went out at 17,687 -- the cap that
        # document had already overflowed -- although its answer came from a
        # 128k resubmission, and was cut off. Batches bill actual usage, so
        # the ceiling costs nothing extra.
        mt = MODEL_MAX_OUTPUT
        req = {"cell": s["cell"], "game": s["game"], "unit": unit_r,
               "prompt": sent, "max_tokens": mt}
        if s.get("unmasked_control"):
            req["unmasked_control"] = True
        requests.append(req)
        sidecar[cid] = {**s, "custom_id": cid, "round": round_no,
                        "prompt_sent": sent, "max_tokens": mt}
    spec0 = waves[0][0]
    out = {"tag": tag, "model": model or spec0.get("model", DEFAULT_MODEL),
           "build": spec0["build"], "repair_round": round_no,
           "requests": requests, "sidecar": sidecar}
    out["expected_usd"] = expected_cost(out)
    return out


# ── score ────────────────────────────────────────────────────────────────────

def finalise_row(side, atts):
    """A joint_game row from every attempt on one unit, or None if the model
    never answered in any round (the unit then counts as MISSING)."""
    real = [a for a in atts if a["error"] is None]
    if not real:
        return None
    valid = [a for a in real if a["valid"]]
    chosen = valid[-1] if valid else real[-1]
    labels = set(side["alias_map"])
    final, actions = finalise(chosen["groups"], labels)
    raw = [x for g in final for x in g] if side["game"] == "O" else final
    record = {
        "calls": len(atts),
        "attempts": [{k: v for k, v in a.items() if k not in ("groups", "report")}
                     for a in atts],
        "repair_attempted": len(atts) > 1,
        "final_attempt_valid": atts[-1]["error"] is None and atts[-1]["valid"],
        "forced_finalise": not chosen["valid"],
        "group_count_error": chosen["group_count_error"],
        "model_answers": len(real),
        "policy_share": (actions["singletons_added"] / len(labels)
                         if labels else 0.0),
        **actions,
    }
    return {"game": side["game"], "unit": side["unit"],
            "model": side.get("model"), "seed": None,
            "n_fragments": side["n_fragments"], "n_records": side["n_records"],
            "alias_map": side["alias_map"], "shown_order": side["shown_order"],
            "prompt_sha": side["prompt_sha"], "prompt": side["prompt"],
            "raw_response": raw, "repair": record,
            "custom_ids": [a["custom_id"] for a in atts],
            "fetched_at": chosen["fetched_at"]}


def score(waves, out_root, allow_partial=False):
    """Write joint_game rows per cell and run the SAME gate and report.

    Returns {cell: refused games}. A cell is refused if any expected unit has no
    real answer in any round, or any unit is over joint_game.POLICY_CAP.
    """
    attempts, side = merge_waves(waves)
    build = waves[0][0]["build"]
    rows, rbnc = defaultdict(list), defaultdict(list)
    for base in sorted(attempts):
        s = side[base]
        row = finalise_row(s, attempts[base])
        if row is not None:
            rows[(s["cell"], s["game"])].append(row)
        elif any(a.get("rbnc") for a in attempts[base]):
            # D6: recorded beside the rows, never scored and never refused for
            rbnc[(s["cell"], s["game"])].append({
                "game": s["game"], "unit": s["unit"], "n_fragments": s["n_fragments"],
                "custom_ids": [a["custom_id"] for a in attempts[base]],
                "why": "exhausted the model's 128k output ceiling; not re-asked "
                       "(RUN_DECISIONS D6)"})

    cells = {}
    for s in side.values():
        cells.setdefault(s["cell"], (s["cell_dir"], set()))[1].add(s["game"])

    verdict = {}
    for cell in sorted(cells):
        cell_dir, games = cells[cell]
        out_dir = os.path.join(out_root, cell)
        os.makedirs(out_dir, exist_ok=True)
        for g in sorted(games):
            with io.open(os.path.join(out_dir, f"{g}.jsonl"), "w",
                         encoding="utf-8") as fh:
                for row in rows.get((cell, g), []):
                    fh.write(json.dumps(row) + "\n")
            with io.open(os.path.join(out_dir, f"{g}.rbnc.jsonl"), "w",
                         encoding="utf-8") as fh:
                for row in rbnc.get((cell, g), []):
                    fh.write(json.dumps(row) + "\n")
        o_units, pool_units, key, pool_truth = build_units(
            _abs(cell_dir), build["docs"], build["pool_size"], build["seed"],
            pools=build.get("pools"), o_docs=build.get("o_docs"))
        expected = {g: [u[0] for u in (o_units if g == "O" else pool_units)]
                    for g in sorted(games)}
        print()
        print("=" * 74)
        print(f" CELL {cell}")
        refused = integrity_gate(out_dir, key, pool_truth, expected)
        report(out_dir, key, pool_truth,
               withhold=frozenset() if allow_partial else refused)
        verdict[cell] = refused
    return verdict


# ── cli ──────────────────────────────────────────────────────────────────────

def _load(path):
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _dump(obj, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1)
    print(f"wrote {path}: {len(obj['requests'])} requests")


def _waves(arg):
    return [(_load(w[0]), w[1:]) for w in arg]


def main():
    ap = argparse.ArgumentParser(description="The paid path for the joint grid.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build")
    b.add_argument("--cells", nargs="+", required=True)
    b.add_argument("--games", nargs="+", default=["J", "O"])
    b.add_argument("--docs", type=int, default=8)
    b.add_argument("--pool-size", type=int, default=7)
    b.add_argument("--seed", type=int, default=42)
    b.add_argument("--model", default=DEFAULT_MODEL)
    b.add_argument("--margin", type=float, default=SIZING_MARGIN)
    b.add_argument("--arm", choices=["masked", "unmasked"], default="masked")
    b.add_argument("--control", action="store_true",
                   help="tag cells ctrl-<arm>-... for the G3 positive control")
    b.add_argument("--pools-file", default=None,
                   help="pre-registered pools, e.g. data/pools/pools.json")
    b.add_argument("--pool-ids-file", default=None,
                   help="restrict to these pool ids, e.g. "
                        "data/pools/linkage_grid.json")
    b.add_argument("--forbid-headline", action="store_true",
                   help="refuse to build if any request touches a document in "
                        "the 46 untouched headline pools (RUN_DECISIONS D2)")
    b.add_argument("--o-docs-file", default=None,
                   help="JSON list of record ids for the per-document O arm")
    b.add_argument("--tag", required=True)
    b.add_argument("--out", required=True)

    r = sub.add_parser("resubmit")
    r.add_argument("--spec", required=True)
    r.add_argument("--results", nargs="+", required=True)
    r.add_argument("--tag", required=True)
    r.add_argument("--out", required=True)

    p = sub.add_parser("repair")
    p.add_argument("--wave", nargs="+", action="append", required=True,
                   metavar="SPEC_THEN_RESULTS")
    p.add_argument("--round", type=int, required=True)
    p.add_argument("--max-rounds", type=int, default=1)
    p.add_argument("--tag", required=True)
    p.add_argument("--out", required=True)

    s = sub.add_parser("score")
    s.add_argument("--wave", nargs="+", action="append", required=True,
                   metavar="SPEC_THEN_RESULTS")
    s.add_argument("--out-root", required=True)
    s.add_argument("--allow-partial", action="store_true")

    a = ap.parse_args()
    if a.cmd == "build":
        frame = (load_frame(a.pools_file, a.pool_ids_file)
                 if a.pools_file else None)
        o_docs = _load(a.o_docs_file) if a.o_docs_file else None
        _dump(build_spec(a.cells, a.games, a.docs, a.pool_size, a.seed, a.tag,
                         a.model, a.margin, a.arm, a.control, pools=frame,
                         o_docs=o_docs,
                         forbid_docs=headline_docs() if a.forbid_headline
                         else None), a.out)
    elif a.cmd == "resubmit":
        spec = build_resubmit_spec(_load(a.spec), a.results, a.tag)
        if not spec["requests"]:
            print("nothing to resubmit: every request has a real answer")
            return
        _dump(spec, a.out)
    elif a.cmd == "repair":
        spec = build_repair_spec(_waves(a.wave), a.round, a.max_rounds, a.tag)
        if not spec["requests"]:
            print("nothing to repair: every unit is valid or out of rounds")
            return
        _dump(spec, a.out)
    else:
        verdict = score(_waves(a.wave), a.out_root, a.allow_partial)
        refused = sorted(c for c, v in verdict.items() if v)
        if refused and not a.allow_partial:
            print()
            print(f"REFUSED cells: {', '.join(refused)}")
            sys.exit(1)


if __name__ == "__main__":
    main()
