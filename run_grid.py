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
RESULTS_PATH = BASE_DIR / "grid_results.json"

VERIFY_SCRIPT = REPO_ROOT / "analysis" / "verify_fragments.py"
BASELINES_SCRIPT = REPO_ROOT / "harness" / "run_baselines.py"
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
    RESULTS_PATH.write_text(json.dumps(results, indent=2))


def already_done(results, strategy, granularity):
    return any(
        r["strategy"] == strategy and r["granularity"] == granularity
        and r["status"] == "ok"
        for r in results
    )


def run_verify(cell_dir):
    """Shell out to analysis/verify_fragments.py --cell <dir>.
    Returns (passed:bool, output:str). A non-zero exit quarantines the cell."""
    if not VERIFY_SCRIPT.exists():
        return None, f"verify script not found at {VERIFY_SCRIPT}"
    result = subprocess.run(
        [sys.executable, str(VERIFY_SCRIPT), "--cell", str(cell_dir)],
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
    # parse JSON from stdout; run_baselines.py is expected to emit a JSON
    # block somewhere in its output — find the last {...} in stdout
    raw = result.stdout
    start = raw.rfind("{")
    end   = raw.rfind("}") + 1
    if start == -1:
        raise ValueError(f"no JSON found in run_baselines.py output:\n{raw[:500]}")
    score = json.loads(raw[start:end])

    # quarantine check on Arafat's coverage counts
    scored   = score.get("scored",   score.get("n_scored"))
    expected = score.get("expected", score.get("n_expected"))
    if scored is not None and expected is not None and scored < expected:
        score["quarantine"] = True
        score["quarantine_reason"] = f"scored {scored} < expected {expected}"

    return score


def get_dollar_cost(n_pending):
    """Ask cost_model_v2.py for the projected spend on n_pending cells.
    Falls back to None if the script isn't there yet."""
    if not COST_MODEL.exists():
        return None
    result = subprocess.run(
        [sys.executable, str(COST_MODEL), "--cells", str(n_pending)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    raw = result.stdout
    start = raw.rfind("{")
    end   = raw.rfind("}") + 1
    if start == -1:
        return None
    return json.loads(raw[start:end])


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
        cut_stats = module.cut_corpus(
            str(raw_path), str(cell_dir),
            granularity=granularity,
            docs=docs,
            **extra_kwargs,
        )
        entry["provenance"]["n_docs"]      = cut_stats.get("n_docs")
        entry["provenance"]["n_fragments"] = cut_stats.get("n_fragments")

        # ── verify ───────────────────────────────────────────────────────
        verify_passed, verify_out = run_verify(cell_dir)
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
        print(f"{strategy:<18}{granularity:<15}{grid_status:<12}{action}")

    print(f"\npending cells: {pending}")

    cost = get_dollar_cost(pending)
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
    parser.add_argument("--raw",      default=str(BASE_DIR / "prose_raw.jsonl"))
    parser.add_argument("--out-root", default=str(BASE_DIR / "grid_output"))
    parser.add_argument("--force",    action="store_true")
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--docs",     nargs="*",
                        help="restrict to these record_ids (wired from build_pools.py)")
    return parser.parse_args()


def main():
    args = parse_args()
    results = load_results()
    if args.dry_run:
        plan_dry_run(results)
        return
    run_grid(args.raw, args.out_root, force=args.force, docs=args.docs)


if __name__ == "__main__":
    main()
