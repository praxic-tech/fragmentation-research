"""
run_grid.py — the harness that drives the full strategy x granularity grid.

Pipeline per cell: cut -> verify -> score -> append to grid_results.json.

    cut     : call that strategy's cut_corpus() to write fragments.jsonl +
              answer_key.jsonl for the cell.
    verify  : reconstruct each doc from its fragments (in answer-key order)
              and confirm the word sequence matches the original raw text —
              a cheap sanity check that runs before we pay for scoring.
    score   : call the real reassembly scorer ("prose memon", ~15 min/cell —
              this is the expensive step and the reason resume exists at
              all). Not our code — plug the real call into
              score_with_memon() below. Left as a clearly-marked stub here.
    append  : one JSON object per cell appended to grid_results.json, with
              full provenance (module/function/params used, timestamps,
              status), so a partial or resumed run is auditable after the
              fact.

Resume: before running a cell, check grid_results.json for an existing
status="ok" entry for that (strategy, granularity) — if found, skip unless
--force. Since scoring is the ~15 min/cell cost, this is what makes it
affordable to re-run after a crash, a code fix, or a corpus update without
re-paying for cells that already scored cleanly.

Fault isolation: one cell's cut/verify/score is wrapped in try/except.
A failing cell is logged with status="error" and the run continues — it
does not take down the other 11 cells.

--dry-run: prints the full 12-cell plan, which cells resume would skip,
which are still pending, and a projected cost for the pending ones
(pending_count * ASSUMED_SCORE_SECONDS — the only per-cell timing we have
is the ~15 min/cell figure for scoring; cutting itself is fast and isn't
counted). Does not cut, verify, or score anything.
"""

import argparse
import importlib
import json
import os
import sys
import time
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE_DIR)
# cutters and the shared splitters live in datagen/; scoring lives here
for _p in (BASE_DIR, os.path.join(ROOT, "datagen")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

RESULTS_PATH = os.path.join(ROOT, "results", "grid_results.json")
DEFAULT_RAW = os.path.join(ROOT, "data", "prose", "prose_raw.jsonl")
ASSUMED_SCORE_SECONDS = 15 * 60  # the one timing figure we actually have

# ── the full 12-cell grid ────────────────────────────────────────────────
# (strategy, granularity, grid_status) — grid_status is documentation, not
# used for dispatch; "skip" cells are never run, "not_built" cells (llm-cut)
# are logged and skipped until that module exists.
CELLS = [
    ("random", "sentence", "build"),
    ("random", "clause", "build"),
    ("random", "token-window", "build"),
    ("semantic", "sentence", "have it"),
    ("semantic", "clause", "build"),
    ("semantic", "token-window", "build"),
    ("coherence-sever", "sentence", "build"),
    ("coherence-sever", "clause", "build"),
    ("coherence-sever", "token-window", "build"),
    ("subject-verb", "sentence", "build"),
    ("subject-verb", "clause", "build"),
    ("subject-verb", "token-window", "skip"),
    ("llm-cut", "llm-decides", "build (deferred — spec only, no corpus-scale run yet)"),
]

SKIP_STATUSES = {"skip"}
NOT_BUILT_STRATEGIES = {"llm-cut"}

# strategy -> (module name, cut_corpus kwargs beyond raw_path/out_dir/granularity)
# semantic dispatches to Arafat's committed cutter.py, which isn't part of
# this deliverable — if that module isn't importable in this environment,
# the cell fails and is logged, it doesn't stop the other 11.
STRATEGY_MODULES = {
    "random": ("random_cut", {"seed": 42}),
    "semantic": ("prose_cutter", {"strategy": "semantic"}),
    "coherence-sever": ("coherence_sever", {}),
    "subject-verb": ("subject_verb", {}),
}


def load_results():
    if not os.path.exists(RESULTS_PATH):
        return []
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_results(results):
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)


def already_done(results, strategy, granularity):
    return any(
        r["strategy"] == strategy and r["granularity"] == granularity and r["status"] == "ok"
        for r in results
    )


def verify_reconstruction(fragments_path, answer_key_path, raw_path):
    """Cheap sanity check, not the real scorer: for each doc, join its
    fragments in answer-key order and confirm the word sequence matches the
    original raw text. Whitespace differences are ignored (the cutters don't
    all guarantee exact character-level reconstruction); word drops,
    additions, or reorderings are not."""
    frag_text = {}
    with open(fragments_path, "r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            frag_text[row["fragment_id"]] = row["text"]

    raw_text = {}
    with open(raw_path, "r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            raw_text[row["record_id"]] = row["text"]

    mismatches = []
    n_checked = 0
    with open(answer_key_path, "r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            record_id = row["record_id"]
            n_checked += 1
            reconstructed = " ".join(frag_text[fid] for fid in row["order"] if fid in frag_text)
            original = raw_text.get(record_id, "")
            if reconstructed.split() != original.split():
                mismatches.append(record_id)

    return {"n_checked": n_checked, "n_mismatched": len(mismatches), "mismatched_ids": mismatches[:10]}


def score_with_memon(fragments_path, answer_key_path):
    """Placeholder for the real ~15 min/cell reassembly scorer ("prose
    memon"). Not our code — replace this function body with the actual call
    when it's available. Raises so a cell that reaches scoring without this
    wired up is honestly logged as score_unavailable rather than silently
    faked."""
    raise NotImplementedError(
        "score_with_memon() is a stub — plug in the real prose-memon scoring call here"
    )


def run_cell(strategy, granularity, raw_path, out_root, score_fn=score_with_memon):
    module_name, extra_kwargs = STRATEGY_MODULES[strategy]
    out_dir = os.path.join(out_root, f"{strategy}__{granularity}".replace(" ", "_"))

    entry = {
        "strategy": strategy,
        "granularity": granularity,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "cutter_module": module_name,
            "cutter_function": "cut_corpus",
            "params": {"granularity": granularity, **extra_kwargs},
            "out_dir": out_dir,
        },
    }
    t0 = time.time()

    try:
        module = importlib.import_module(module_name)
        module.cut_corpus(raw_path, out_dir, granularity=granularity, **extra_kwargs)

        frag_path = os.path.join(out_dir, "prose_fragments.jsonl")
        key_path = os.path.join(out_dir, "prose_answer_key.jsonl")
        verify_result = verify_reconstruction(frag_path, key_path, raw_path)
        entry["verify"] = verify_result

        try:
            score = score_fn(frag_path, key_path)
            entry["score"] = score
            entry["status"] = "ok"
        except NotImplementedError as e:
            entry["status"] = "score_unavailable"
            entry["error"] = str(e)

    except Exception as e:
        entry["status"] = "error"
        entry["error"] = f"{type(e).__name__}: {e}"

    entry["finished_at"] = datetime.now(timezone.utc).isoformat()
    entry["duration_sec"] = round(time.time() - t0, 2)
    return entry


def plan_dry_run(results):
    print(f"{'strategy':<18}{'granularity':<15}{'plan status':<14}{'action'}")
    pending = 0
    for strategy, granularity, grid_status in CELLS:
        if grid_status in SKIP_STATUSES:
            action = "skip (grid marks this cell skip)"
        elif strategy in NOT_BUILT_STRATEGIES:
            action = "skip (not built yet)"
        elif already_done(results, strategy, granularity):
            action = "resume: already ok, skip"
        else:
            action = "RUN"
            pending += 1
        print(f"{strategy:<18}{granularity:<15}{grid_status:<14}{action}")

    projected_sec = pending * ASSUMED_SCORE_SECONDS
    print(f"\npending cells: {pending}")
    print(f"projected cost: {projected_sec/60:.0f} min (~{projected_sec/3600:.1f} hr) "
          f"at {ASSUMED_SCORE_SECONDS/60:.0f} min/cell (scoring only, cutting is fast and uncounted)")


def run_grid(raw_path, out_root, force=False, score_fn=score_with_memon):
    results = load_results()

    for strategy, granularity, grid_status in CELLS:
        if grid_status in SKIP_STATUSES:
            print(f"[skip] {strategy} x {granularity} — grid marks this cell skip")
            continue
        if strategy in NOT_BUILT_STRATEGIES:
            print(f"[skip] {strategy} x {granularity} — not built yet")
            continue
        if not force and already_done(results, strategy, granularity):
            print(f"[resume] {strategy} x {granularity} — already ok, skipping")
            continue

        print(f"[run] {strategy} x {granularity} ...")
        entry = run_cell(strategy, granularity, raw_path, out_root, score_fn=score_fn)
        print(f"  -> status={entry['status']}  ({entry['duration_sec']}s)")
        if entry["status"] == "error":
            print(f"  -> error: {entry['error']}")

        # drop any stale entry for this cell before appending the fresh one
        results = [r for r in results
                   if not (r["strategy"] == strategy and r["granularity"] == granularity)]
        results.append(entry)
        save_results(results)  # write after every cell, not just at the end

    return results


def parse_args():
    parser = argparse.ArgumentParser(description="Run the full strategy x granularity grid.")
    parser.add_argument("--raw", default=DEFAULT_RAW)
    parser.add_argument("--out-root", default=os.path.join(ROOT, "results", "grid"))
    parser.add_argument("--force", action="store_true", help="re-run cells even if already ok")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and projected cost only")
    return parser.parse_args()


def main():
    args = parse_args()
    results = load_results()
    if args.dry_run:
        plan_dry_run(results)
        return
    run_grid(args.raw, args.out_root, force=args.force)


if __name__ == "__main__":
    main()
