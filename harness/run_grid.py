"""
run_grid.py — drive the strategy x granularity grid.

Pipeline per cell: cut -> verify -> score -> append to grid_results.json.

    cut     : strategy's cut_corpus() -> prose_fragments.jsonl +
              prose_answer_key.jsonl (exact harness names, run_baselines.py
              reads nothing else).
    verify  : shell out to analysis/verify_fragments.py --cell <dir>.
              exits non-zero on bad cells; any cell that fails quarantined,
              not scored. expect ~0.12% dropped content and ~380/500 exact
              on a healthy cell (MIN_SENT_CHARS filter in corpus build, not
              a cutter bug).
    score   : shell out to harness/run_baselines.py --data <cell>.
              parse coverage from its json output; quarantine any cell
              where scored < expected (Arafat's coverage counts). sets
              status="ok" so resume actually fires next run.
    append  : one entry per cell written to grid_results.json after every
              cell, not at the end, so a crash mid-run leaves a valid file.

Resume: checks status=="ok" in grid_results.json before running. status was
previously never set to "ok" because score_with_memon() always raised — so
resume never fired once. That's fixed: score() sets status="ok" on success.

--dry-run: prints plan + dollar cost from analysis/cost_model_v2.py.
Minutes can't do the job the spec describes ("spend check before we commit
$60 on the ordering grid").
"""

import argparse
import importlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
RESULTS_PATH = REPO_ROOT / "results" / "grid_results.json"

VERIFY_SCRIPT = REPO_ROOT / "analysis" / "verify_fragments.py"
BASELINES_SCRIPT = REPO_ROOT / "harness" / "run_baselines.py"

# Must match the emitters in run_baselines.py and cost_model_v2.py.
BASELINES_JSON_BEGIN = "===RUN_BASELINES_JSON_BEGIN==="
BASELINES_JSON_END   = "===RUN_BASELINES_JSON_END==="
COST_JSON_BEGIN      = "===COST_MODEL_JSON_BEGIN==="
COST_JSON_END        = "===COST_MODEL_JSON_END==="
COST_MODEL = REPO_ROOT / "analysis" / "cost_model_v2.py"

CELLS = [
    ("random",          "sentence",    "build"),
    ("random",          "clause",      "build"),
    ("random",          "token-window","build"),
    ("semantic",        "sentence",    "have it"),
    ("semantic",        "clause",      "build"),
    ("semantic",        "token-window","build"),
    ("coherence-sever", "sentence",    "build"),
    ("coherence-sever", "clause",      "build"),
    ("coherence-sever", "token-window","build"),
    ("subject-verb",    "sentence",    "build"),
    ("subject-verb",    "clause",      "build"),
    ("subject-verb",    "token-window","skip"),
    ("llm-cut",         "llm-decides", "build (deferred)"),
]

SKIP_STATUSES    = {"skip"}
NOT_BUILT        = {"llm-cut"}

STRATEGY_MODULES = {
    "random":          ("random_cut",      {"seed": 42}),
    "semantic":        ("prose_cutter",    {"strategy": "semantic"}),
    "coherence-sever": ("coherence_sever", {}),
    "subject-verb":    ("subject_verb",    {}),
}


def load_results():
    if not RESULTS_PATH.exists():
        return []
    return json.loads(RESULTS_PATH.read_text())


def save_results(results):
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, indent=2))


def already_done(results, strategy, granularity):
    return any(
        r["strategy"] == strategy and r["granularity"] == granularity
        and r["status"] == "ok"
        for r in results
    )


def run_verify(cell_dir, raw_path):
    """Shell out to analysis/verify_fragments.py --cell <dir> --raw <raw_path>.

    raw_path MUST be the file the cell was actually cut from. The grid runs on
    the length-capped corpus (data/grid_corpus/), and verify_fragments defaults
    to the FULL data/prose/prose_raw.jsonl -- checking a truncated cell against
    the untruncated document reports the truncation as dropped content. Measured
    on the reference cell: 27.20% dropped and 79/180 reconstructing against the
    full corpus, versus 0.00% and 179/180 against the corpus it was cut from.
    Every grid cell would have looked catastrophically broken.

    Returns (passed:bool, output:str). A non-zero exit quarantines the cell."""
    if not VERIFY_SCRIPT.exists():
        return None, f"verify script not found at {VERIFY_SCRIPT}"
    result = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT),
         "--cell", str(cell_dir), "--raw", str(raw_path)],
        capture_output=True, text=True
    )
    passed = result.returncode == 0
    return passed, (result.stdout + result.stderr).strip()


def run_score(cell_dir):
    """Shell out to harness/run_baselines.py --data <cell_dir>.
    Parses its JSON output and returns the score dict, or raises on failure.
    Coverage counts come from Arafat's JSON output; quarantine if
    scored < expected."""
    if not BASELINES_SCRIPT.exists():
        raise FileNotFoundError(f"scorer not found at {BASELINES_SCRIPT}")
    result = subprocess.run(
        [sys.executable, str(BASELINES_SCRIPT), "--data", str(cell_dir)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"run_baselines.py exited {result.returncode}:\n{result.stderr[:500]}"
        )
    # run_baselines.py emits a DELIMITED block. The previous version took the
    # last {...} in stdout, which failed two ways: run_baselines printed no JSON
    # at all, so every cell raised; and had it printed nested JSON, a bare
    # rfind("{") lands on an inner object and parses part of the answer as the
    # whole thing.
    raw = result.stdout
    if BASELINES_JSON_BEGIN not in raw or BASELINES_JSON_END not in raw:
        raise ValueError(
            f"run_baselines.py emitted no {BASELINES_JSON_BEGIN} block:"
            f"\n{raw[-500:]}"
        )
    score = json.loads(
        raw.split(BASELINES_JSON_BEGIN)[1].split(BASELINES_JSON_END)[0])

    # Quarantine comes from the emitted per-method flags, not a top-level
    # scored/expected pair -- coverage is reported PER METHOD, so a cell where
    # one method lost records and another did not has to be caught on the
    # method that lost them. Reading a top-level key found nothing and every
    # cell passed.
    reasons = []
    if score.get('quarantined'):
        for method, why in (score.get('quarantine_reasons') or {}).items():
            reasons.append(f"{method}: {', '.join(why) if why else 'flagged'}")
    for method, r in (score.get('results') or {}).items():
        for game, sc, exp in (('O', r.get('o_scored'), r.get('o_expected')),
                              ('L', r.get('l_scored'), r.get('l_expected'))):
            if sc is not None and exp is not None and sc < exp:
                reasons.append(f"{method} Game {game}: scored {sc} < expected {exp}")
        if r.get('l_valid') is False:
            reasons.append(f"{method} Game L: guess is not an exact partition")
    score['quarantine'] = bool(reasons)
    score['quarantine_reasons_flat'] = reasons

    return score


def get_dollar_cost(pending_cells):
    """Projected spend for the pending cells, from analysis/cost_model_v2.py.

    Takes the actual (strategy, granularity) pairs rather than a count: clause
    costs roughly 4x sentence per ordering cell, so a flat per-cell average
    cannot do the spend-check job the dry run exists for. Returns None if the
    cost model is missing or unparseable, and the caller says so explicitly
    rather than printing a wrong number."""
    if not COST_MODEL.exists():
        return None
    result = subprocess.run(
        [sys.executable, str(COST_MODEL)], capture_output=True, text=True)
    raw = result.stdout
    if result.returncode != 0 or COST_JSON_BEGIN not in raw:
        return None
    model = json.loads(
        raw.split(COST_JSON_BEGIN)[1].split(COST_JSON_END)[0])

    # The joint model emits one cost per cell. 'ordering_per_cell' is the
    # superseded O+L shape, kept as a fallback so an old model file still
    # produces a number rather than a silent None.
    per_cell = model.get('joint_per_cell') or model.get('ordering_per_cell', {})
    breakdown, total = {}, 0.0
    for _strategy, granularity in pending_cells:
        usd = per_cell.get(granularity)
        if usd is None:
            continue
        breakdown[granularity] = breakdown.get(granularity, 0.0) + usd
        total += usd
    return {
        'total_usd': total,
        'breakdown': breakdown,
        'detail': '  '.join(f'{g} {v:.2f}' for g, v in sorted(breakdown.items())),
        'run_total_usd': model.get('totals', {}).get('total_usd'),
    }


def run_cell(strategy, granularity, raw_path, out_root, docs=None):
    module_name, extra_kwargs = STRATEGY_MODULES[strategy]
    cell_dir = Path(out_root) / f"{strategy}__{granularity}".replace(" ", "_")

    entry = {
        "strategy": strategy,
        "granularity": granularity,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "cutter_module": module_name,
            "cutter_function": "cut_corpus",
            "params": {"granularity": granularity, **extra_kwargs},
            "cell_dir": str(cell_dir),
            "n_docs": None,       # filled in after cut
            "n_fragments": None,  # filled in after cut
        },
    }
    t0 = time.time()

    try:
        # ── cut ──────────────────────────────────────────────────────────
        sys.path.insert(0, str(REPO_ROOT / "datagen"))
        module = importlib.import_module(module_name)
        # `or {}` so a cutter that returns nothing degrades to missing
        # provenance rather than an AttributeError that reads as a cut failure.
        cut_stats = module.cut_corpus(
            str(raw_path), str(cell_dir),
            granularity=granularity,
            docs=docs,
            **extra_kwargs,
        ) or {}
        entry["provenance"]["n_docs"]      = cut_stats.get("n_docs")
        entry["provenance"]["n_fragments"] = cut_stats.get("n_fragments")

        # ── verify ───────────────────────────────────────────────────────
        verify_passed, verify_out = run_verify(cell_dir, raw_path)
        entry["verify"] = {"passed": verify_passed, "output": verify_out}
        if verify_passed is False:
            entry["status"] = "verify_failed"
            entry["error"]  = f"verify_fragments.py exited non-zero:\n{verify_out[:300]}"
            return entry

        # ── score ────────────────────────────────────────────────────────
        score = run_score(cell_dir)
        entry["score"]  = score
        entry["status"] = "quarantine" if score.get("quarantine") else "ok"

    except Exception as e:
        entry["status"] = "error"
        entry["error"]  = f"{type(e).__name__}: {e}"

    entry["finished_at"]  = datetime.now(timezone.utc).isoformat()
    entry["duration_sec"] = round(time.time() - t0, 2)
    return entry


def plan_dry_run(results):
    print(f"{'strategy':<18}{'granularity':<15}{'status':<12}action")
    pending = 0
    pending_cells = []
    for strategy, granularity, grid_status in CELLS:
        if grid_status in SKIP_STATUSES:
            action = "skip (grid)"
        elif strategy in NOT_BUILT:
            action = "skip (not built)"
        elif already_done(results, strategy, granularity):
            action = "resume: already ok"
        else:
            action = "RUN"
            pending += 1
            pending_cells.append((strategy, granularity))
        print(f"{strategy:<18}{granularity:<15}{grid_status:<12}{action}")

    print(f"\npending cells: {pending}")

    cost = get_dollar_cost(pending_cells)
    if cost:
        print(f"projected cost: ${cost.get('total_usd', '?'):.2f}  "
              f"({cost.get('detail', '')})")
    else:
        # cost_model_v2.py not present yet — fall back to minutes only,
        # with an explicit note that this can't do the spend-check job
        mins = pending * 15
        print(f"projected time: ~{mins} min  "
              f"(no dollar estimate — analysis/cost_model_v2.py not found)")


def run_grid(raw_path, out_root, force=False, docs=None):
    results = load_results()

    for strategy, granularity, grid_status in CELLS:
        if grid_status in SKIP_STATUSES:
            print(f"[skip] {strategy} x {granularity}")
            continue
        if strategy in NOT_BUILT:
            print(f"[skip] {strategy} x {granularity} — not built yet")
            continue
        if not force and already_done(results, strategy, granularity):
            print(f"[resume] {strategy} x {granularity} — already ok")
            continue

        print(f"[run] {strategy} x {granularity} ...")
        entry = run_cell(strategy, granularity, raw_path, out_root, docs=docs)
        print(f"  -> status={entry['status']}  ({entry['duration_sec']}s)")
        if entry["status"] in ("error", "verify_failed", "quarantine"):
            print(f"  -> {entry.get('error', entry.get('score', {}).get('quarantine_reason', ''))}")

        results = [r for r in results
                   if not (r["strategy"] == strategy and r["granularity"] == granularity)]
        results.append(entry)
        save_results(results)

    return results


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw",
                    default=str(REPO_ROOT / "data" / "grid_corpus" / "prose_raw.jsonl"),
                    help="the grid runs on the length-capped corpus from "
                         "datagen/build_grid_corpus.py, not the full one")
    parser.add_argument("--out-root", default=str(REPO_ROOT / "results" / "grid"))
    parser.add_argument("--force",    action="store_true")
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--docs",     nargs="*",
                        help="restrict to these record_ids")
    parser.add_argument("--docs-from", metavar="JSON",
                        default=str(REPO_ROOT / "data" / "pools" / "ordering_grid.json"),
                        help="read the document selection from build_pools.py output "
                             "(default: data/pools/ordering_grid.json). Pass 'all' to "
                             "cut the whole corpus instead.")
    return parser.parse_args()


def main():
    args = parse_args()

    # The grid runs on ONE fixed document selection, built once by
    # datagen/build_pools.py. Rebuilding or varying it between cells makes the
    # cells incomparable without erroring, so the selection is the default and
    # cutting the whole corpus has to be asked for explicitly.
    docs = args.docs
    if not docs and args.docs_from and args.docs_from != "all":
        sel = Path(args.docs_from)
        if sel.exists():
            payload = json.loads(sel.read_text())
            docs = [d["record_id"] for d in payload["documents"]]
            print(f"[docs] {len(docs)} documents from {sel.name} "
                  f"(cap {payload.get('fragment_cap')} fragments)")
        else:
            print(f"[docs] {sel} not found — run datagen/build_pools.py first, "
                  "or pass --docs-from all")
            raise SystemExit(1)
    results = load_results()
    if args.dry_run:
        plan_dry_run(results)
        return
    run_grid(args.raw, args.out_root, force=args.force, docs=docs)


if __name__ == "__main__":
    main()
