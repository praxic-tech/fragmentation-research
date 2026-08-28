"""
harness.py — Unified evaluation harness.

Evaluates four strategies on Game O (ordering) and Game L (grouping) for:
    - Identifier data (fixed 4 fragments per record)
    - Prose corpus (variable fragments per record)

Strategies:
    Random      — uniform random, repeated N_RUNS times → distribution stats
    Memon-G     — greedy nearest-neighbour (text-similarity-guided)
    Memon-MST   — maximum spanning tree path / MST-cut
    LLM         — loaded from data/llm_{ordering,grouping}_guesses.jsonl

One RNG seed controls everything.  Final output is two comparison tables
plus a harness_results.json file.

Usage:
    python harness.py
    python harness.py --seed 123 --runs 5000
    python harness.py --skip-memon        # quick mode: random + LLM only
"""

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent
ROOT = BASE.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(ROOT / "adversaries"))

from loader  import (load_fragments, load_answer_key,
                     group_fragments_by_record,
                     load_llm_ordering_guesses,
                     load_llm_grouping_guesses)
from orderers import (random_order,    random_grouping,
                      greedy_nn_order, mst_order)
# greedy_grouping / mst_grouping are deliberately NOT imported here: they are
# degenerate and reachable only through memon_linkage's legacy variants.
from scoring  import score_ordering, score_linkage
from memon_linkage import memon_grouping

# ── Constants ────────────────────────────────────────────────────────────────────
_NAN = "-"

# ── Paths (relative to the repo root, one level up from this file) ────────────
DATA          = ROOT / "data"
RESULTS       = ROOT / "results"

# Identifier data
ID_FRAGMENTS  = DATA / "identifier" / "fragments.jsonl"
ID_ANSWER_KEY = DATA / "identifier" / "answer_key.jsonl"
ID_LLM_ORDER  = RESULTS / "llm_ordering_guesses.jsonl"
ID_LLM_GROUP  = RESULTS / "llm_grouping_guesses.jsonl"

# Prose data
PROSE_FRAGMENTS  = DATA / "prose" / "prose_fragments.jsonl"
PROSE_ANSWER_KEY = DATA / "prose" / "prose_answer_key.jsonl"
PROSE_LLM_ORDER  = RESULTS / "prose_llm_ordering_guesses.jsonl"
PROSE_LLM_GROUP  = RESULTS / "prose_llm_grouping_guesses.jsonl"

DEFAULT_SEED  = 42
DEFAULT_RUNS  = 10_000


# ════════════════════════════════════════════════════════════════════════════════
# Fragment ID masking for Game L (prevents ID-based leakage)
# ════════════════════════════════════════════════════════════════════════════════

def mask_fragment_ids(fragments: list) -> tuple:
    """
    Replace fragment IDs with random labels to prevent ID-based leakage.
    Preserves the text content for similarity computation.

    Labels are drawn from a shuffled permutation of exactly len(fragments)
    distinct labels, so masking is COLLISION-FREE by construction. Shuffling is
    what hides the original order — the label index carries no positional
    information about the fragment it names.

    The previous implementation drew `random.randint(100000, 999999)` per
    fragment. With only 900,000 possible labels that is a birthday problem: at
    16,524 fragments ~128 labels collided, each collision overwrote an id_map
    entry, and `unmask_groups` then silently dropped those fragments from every
    Game L score. Invisible at 200 fragments (expected collisions ~0.02), which
    is why it survived until the corpus scaled.

    Returns:
        masked_fragments: list of fragments with masked IDs
        id_map: dict mapping masked_id -> original_id
    """
    labels = [f"m_{i:07d}" for i in range(len(fragments))]
    random.shuffle(labels)

    masked_fragments = []
    id_map = {}
    for label, f in zip(labels, fragments):
        id_map[label] = f["fragment_id"]
        masked_fragments.append({
            "fragment_id": label,
            "text": f["text"]
        })

    assert len(id_map) == len(fragments), "mask collision — labels must be unique"
    return masked_fragments, id_map


def unmask_groups(groups: dict, id_map: dict) -> dict:
    """
    Convert groups with masked IDs back to original IDs for scoring.
    """
    unmasked_groups = {}
    for gid, masked_ids in groups.items():
        unmasked_groups[gid] = [id_map[mid] for mid in masked_ids if mid in id_map]
    return unmasked_groups


# ════════════════════════════════════════════════════════════════════════════════
# Coverage reporting helper
# ════════════════════════════════════════════════════════════════════════════════

def _print_coverage(game: str, scored: int, supplied: int,
                    expected: int, malformed: int) -> None:
    """
    Print a coverage line for one game in one cell.

    Item (a): every score must show scored / supplied / expected so that
    bugs 1, 8, and 10 (fragments missing, records dropped, errors swallowed)
    are immediately visible.  Any cell where scored < expected is quarantined
    with a clear marker so it does not silently pollute the grid results.

    Format:
        Game O coverage: scored=50/50/50  malformed=0          <- healthy
        [QUARANTINE] Game O: scored=48/50/50  malformed=2      <- needs review
    """
    tag    = f"  {game} coverage:"
    detail = f"scored={scored}/{supplied}/{expected}  malformed={malformed}"
    if scored < expected or malformed > 0:
        print(f"  [QUARANTINE] {game}: {detail}")
    else:
        print(f"{tag} {detail}")


# ════════════════════════════════════════════════════════════════════════════════
# Per-method evaluators
# ════════════════════════════════════════════════════════════════════════════════

def _avg_ordering_tau(fragments, true_order, order_fn) -> dict:
    """
    Run order_fn on each record, compute per-record Kendall's tau,
    return a coverage dict.

    Bug 10 fix: the old version had a bare `except: continue` that silently
    swallowed errors and id-set mismatches, so "mean tau 0.70" could be the
    mean over 500 records or over 12, with no way to tell.  This version
    tracks every skip and error and returns them alongside the mean so the
    caller can print the coverage line and quarantine cells where
    scored < expected.

    Returns:
        {
            "tau":      float,   # mean tau, or nan if nothing was scored
            "scored":   int,     # records that produced a valid tau
            "supplied": int,     # records handed to this function
            "expected": int,     # records in true_order
            "skipped":  int,     # id-set mismatches or nan tau
            "errors":   int,     # exceptions raised by order_fn or score_ordering
        }
    """
    grouped  = group_fragments_by_record(fragments)
    taus     = []
    skipped  = 0
    errors   = 0
    supplied = len(grouped)
    expected = len(true_order)

    for rec_id, frag_ids in grouped.items():
        try:
            guess = order_fn(frag_ids)
            if len(guess) != len(frag_ids) or set(guess) != set(frag_ids):
                skipped += 1
                continue
            result = score_ordering(guess, true_order[rec_id])
            if not np.isnan(result["tau"]):
                taus.append(result["tau"])
            else:
                skipped += 1
        except Exception:
            errors += 1

    return {
        "tau":      float(np.mean(taus)) if taus else float("nan"),
        "scored":   len(taus),
        "supplied": supplied,
        "expected": expected,
        "skipped":  skipped,
        "errors":   errors,
    }


# ── Random ────────────────────────────────────────────────────────────────────

def eval_random(fragments, true_order, true_groups, n_runs):
    """
    Run random baseline n_runs times.
    Returns arrays: o_taus, l_precisions, l_recalls, l_f1s.
    """
    grouped = group_fragments_by_record(fragments)
    n_rec   = len(true_groups)

    o_taus, l_ps, l_rs, l_fs = [], [], [], []

    # Mask fragment IDs for Game L (prevents ID leakage)
    masked_fragments, id_map = mask_fragment_ids(fragments)

    for _ in range(n_runs):
        # Game O - uses original fragments (ordering needs real IDs)
        run_taus = []
        for rec_id, frag_ids in grouped.items():
            r = score_ordering(random_order(frag_ids), true_order[rec_id])
            if not np.isnan(r["tau"]):
                run_taus.append(r["tau"])
        if run_taus:
            o_taus.append(float(np.mean(run_taus)))

        # Game L - uses masked fragments, then unmaps back to original IDs
        masked_groups = random_grouping(masked_fragments, n_rec)
        unmasked_groups = unmask_groups(masked_groups, id_map)
        s = score_linkage(unmasked_groups, true_groups)
        l_ps.append(s["precision"])
        l_rs.append(s["recall"])
        l_fs.append(s["f1"])

    return (np.array(o_taus),
            np.array(l_ps), np.array(l_rs), np.array(l_fs))


# ── Memon (greedy / MST) ──────────────────────────────────────────────────────

def eval_memon(fragments, true_order, true_groups, method: str,
               grouping_variant: str = "fixed") -> dict:
    """
    Evaluate one Memon strategy on both games.

    method selects the Game O ORDERING heuristic only:
        'greedy' — greedy nearest-neighbour ordering
        'mst'    — maximum spanning tree path ordering

    Game L GROUPING is the same for both, because there is only one correct
    grouping: TF-IDF cosine + average linkage (`memon_linkage`, variant
    "fixed"). The published single-linkage / MST-cut groupings are degenerate —
    they collapse ~90% of a corpus into one cluster and score at or below the
    trivial "everything in one bucket" strategy — so they are NOT on the live
    path. They remain reachable via grouping_variant="legacy-greedy" /
    "legacy-mst" purely to reproduce tables the team saw before the fix.
    """
    text_by_id = {f["fragment_id"]: f["text"] for f in fragments}
    n_groups   = len(true_groups)

    # Mask fragment IDs for Game L (prevents ID leakage)
    masked_fragments, id_map = mask_fragment_ids(fragments)

    # Game O - uses original fragments and text_by_id
    if method == "greedy":
        order_fn = lambda ids: greedy_nn_order(ids, text_by_id)
    elif method == "mst":
        order_fn = lambda ids: mst_order(ids, text_by_id)
    else:
        raise ValueError(f"unknown Memon ordering method {method!r}")

    o_cov = _avg_ordering_tau(fragments, true_order, order_fn=order_fn)
    o_tau = o_cov["tau"]

    # Item (a): coverage line for Game O
    _print_coverage("Game O", o_cov["scored"], o_cov["supplied"],
                    o_cov["expected"], o_cov["errors"])

    masked_groups = memon_grouping(masked_fragments, n_groups,
                                   variant=grouping_variant)

    # Bug 11 fix: grouping must return exactly n_groups clusters.
    # If it returns a different number, flag it rather than silently
    # scoring an incompatible partition.
    if len(masked_groups) != n_groups:
        print(f"  [QUARANTINE] Game L: grouping returned {len(masked_groups)} groups, "
              f"expected {n_groups} — cell is quarantined")

    # Convert masked IDs back to original IDs for scoring
    unmasked_groups = unmask_groups(masked_groups, id_map)
    all_ids = {f["fragment_id"] for f in fragments}
    l_scores = score_linkage(unmasked_groups, true_groups,
                             all_fragment_ids=all_ids)

    # Item (a): coverage line for Game L
    if l_scores["coverage"]:
        cov = l_scores["coverage"]
        _print_coverage("Game L", cov["unique"], cov["supplied"],
                        cov["expected"], 0)

    return {
        "o_tau":       o_tau,
        "o_tau_std":   float("nan"),
        "l_precision": l_scores["precision"],
        "l_recall":    l_scores["recall"],
        "l_f1":        l_scores["f1"],
        "l_floor":     l_scores["floor"]["f1"],
        "o_scored":    o_cov["scored"],
        "o_supplied":  o_cov["supplied"],
        "o_expected":  o_cov["expected"],
    }


# ── LLM ───────────────────────────────────────────────────────────────────────

def eval_llm(true_order, true_groups, llm_order_path, llm_group_path) -> dict:
    """
    Load and score pre-computed LLM guesses.
    Gracefully handles missing files without crashing.

    Bug 7 fix: the old version wrapped the entire Game O loop in one try block.
    One malformed record raised an exception that aborted the loop, leaving
    o_tau as NaN — indistinguishable from "no file found".  This version wraps
    each record individually so good records are still scored.

    Item (a): coverage line printed for both games.
    Item (d): malformed / zero-answer counts appear in the coverage line,
              not as a buried [warn] message.
    """
    # ── Game O ────────────────────────────────────────────────────────────────
    o_tau      = float("nan")
    o_scored   = 0
    o_supplied = 0
    o_expected = len(true_order)
    o_malformed = 0

    if llm_order_path.exists():
        try:
            guesses    = load_llm_ordering_guesses(llm_order_path)
            o_supplied = len(guesses)
            taus       = []
            for rec_id, guessed_order in guesses.items():
                if rec_id not in true_order:
                    o_malformed += 1
                    continue
                try:                                    # Bug 7 fix: per-record try
                    r = score_ordering(guessed_order, true_order[rec_id])
                    if not np.isnan(r["tau"]):
                        taus.append(r["tau"])
                    else:
                        o_malformed += 1
                except Exception as rec_err:
                    o_malformed += 1                    # Item (d): count, not warn
            o_scored = len(taus)
            if taus:
                o_tau = float(np.mean(taus))
        except Exception as e:
            print(f"  [warn] Error loading LLM ordering file: {e}")

    # Item (a): coverage line — quarantine if scored < expected
    _print_coverage("Game O", o_scored, o_supplied, o_expected, o_malformed)

    # ── Game L ────────────────────────────────────────────────────────────────
    l_scores = {
        "precision": float("nan"), "recall": float("nan"),
        "f1": float("nan"), "empty": True,
        "coverage": None, "floor": {"f1": float("nan")},
    }

    if llm_group_path.exists():
        try:
            llm_groups = load_llm_grouping_guesses(llm_group_path)
            all_ids    = {fid for ids in true_groups.values() for fid in ids}
            l_scores   = score_linkage(llm_groups, true_groups,
                                       all_fragment_ids=all_ids)
        except Exception as e:
            print(f"  [warn] Error loading LLM grouping guesses: {e}")

    # Item (a): coverage line for Game L
    if l_scores["coverage"]:
        cov = l_scores["coverage"]
        _print_coverage("Game L", cov["unique"], cov["supplied"],
                        cov["expected"], 0)
    elif l_scores["empty"]:
        print(f"  Game L coverage: no groups submitted")

    return {
        "o_tau":       o_tau,
        "o_tau_std":   float("nan"),
        "l_precision": l_scores["precision"],
        "l_recall":    l_scores["recall"],
        "l_f1":        l_scores["f1"],
        "l_floor":     l_scores["floor"]["f1"],
        "o_scored":    o_scored,
        "o_supplied":  o_supplied,
        "o_expected":  o_expected,
    }


# ════════════════════════════════════════════════════════════════════════════════
# Comparison table (ASCII only)
# ════════════════════════════════════════════════════════════════════════════════

def _f(val: float, w: int = 8) -> str:
    """Format a single float value, right-aligned, or '-' for NaN."""
    if np.isnan(val):
        return f"{_NAN:>{w}}"
    return f"{val:>+{w}.4f}"


def _f_pm(mu: float, sd: float) -> str:
    """Format mean ± std."""
    if np.isnan(mu) or np.isnan(sd):
        return _NAN
    return f"{mu:+.4f} +- {sd:.4f}"


def _f_ci(mu: float, sd: float) -> str:
    """Format mean ± 2σ confidence interval."""
    if np.isnan(mu) or np.isnan(sd):
        return _NAN
    lo, hi = mu - 2 * sd, mu + 2 * sd
    return f"[{lo:+.4f}, {hi:+.4f}]"


def print_comparison_table(results: dict, title: str, seed: int, n_runs: int) -> None:
    """Pretty-print the unified comparison table to stdout using ASCII only."""
    
    print(f"\n{'='*70}")
    print(f" {title}")
    print('='*70)
    
    # Column widths
    cw = [15, 24, 24, 10, 10, 10, 10]
    headers = [
        "Method",
        "Game O tau (mean+/-std)",
        "Game O tau +/-2sigma CI",
        "L: F1",
        "L: floor",   # Item (c): trivial single-bucket floor alongside F1
        "L: P",
        "L: R",
    ]

    def hline():
        return "+" + "+".join("-" * w for w in cw) + "+"

    def row(*cells):
        parts = [f" {str(c):<{w - 2}} " for c, w in zip(cells, cw)]
        return "|" + "|".join(parts) + "|"

    print()
    print(hline())
    print(row(*headers))
    print(hline().replace("-", "="))

    for name, r in results.items():
        has_dist = not np.isnan(r.get("o_tau_std", float("nan")))

        tau_cell = (
            _f_pm(r["o_tau"], r["o_tau_std"]) if has_dist
            else _f(r["o_tau"], 10).strip()
        )
        ci_cell = (
            _f_ci(r["o_tau"], r["o_tau_std"]) if has_dist
            else _NAN
        )

        print(row(
            name,
            tau_cell,
            ci_cell,
            _f(r["l_f1"],          9).strip(),
            _f(r.get("l_floor", float("nan")), 9).strip(),
            _f(r["l_precision"],   9).strip(),
            _f(r["l_recall"],      9).strip(),
        ))

    print(hline())
    print(f"  seed={seed}  |  random_runs={n_runs:,}")


# ════════════════════════════════════════════════════════════════════════════════
# Core evaluation function
# ════════════════════════════════════════════════════════════════════════════════

def evaluate_dataset(fragments_path, answer_key_path, llm_order_path, llm_group_path, 
                     dataset_name, args):
    """
    Evaluate a single dataset and return results.
    """
    print(f"\n{'='*70}")
    print(f" Evaluating: {dataset_name}")
    print('='*70)
    
    # Load data
    fragments   = load_fragments(fragments_path)
    true_order  = load_answer_key(answer_key_path)
    true_groups = group_fragments_by_record(fragments)
    
    print(f"  {len(fragments)} fragments across {len(true_order)} records")
    print(f"  n_groups = {len(true_groups)}")
    
    # Check fragment distribution
    grouped = group_fragments_by_record(fragments)
    sizes = [len(ids) for ids in grouped.values()]
    print(f"  Fragment counts per record: min={min(sizes)}, max={max(sizes)}, mean={np.mean(sizes):.1f}")
    print()

    results = {}

    # ── Random baseline ───────────────────────────────────────────────────────
    print(f"Random baseline ({args.runs:,} runs) ...")
    o_taus, l_ps, l_rs, l_fs = eval_random(
        fragments, true_order, true_groups, args.runs
    )
    results["Random"] = {
        "o_tau":       float(o_taus.mean()),
        "o_tau_std":   float(o_taus.std(ddof=1)),
        "l_precision": float(l_ps.mean()),
        "l_recall":    float(l_rs.mean()),
        "l_f1":        float(l_fs.mean()),
    }
    print(f"  Game O tau : {o_taus.mean():+.4f} +- {o_taus.std(ddof=1):.4f}"
          f"   2sigma CI [{o_taus.mean()-2*o_taus.std(ddof=1):+.4f},"
          f" {o_taus.mean()+2*o_taus.std(ddof=1):+.4f}]")
    print(f"  Game L F1: {l_fs.mean():.4f} +- {l_fs.std(ddof=1):.4f}")

    # ── Memon strategies ──────────────────────────────────────────────────────
    if not args.skip_memon:
        for method, label in [("greedy", "Memon-Greedy"), ("mst", "Memon-MST")]:
            print(f"\n{label} ...")
            results[label] = eval_memon(
                fragments, true_order, true_groups, method,
                grouping_variant=args.grouping
            )
            r = results[label]
            print(f"  Game O tau : {r['o_tau']:+.4f}")
            print(f"  Game L   : F1={r['l_f1']:.4f}  P={r['l_precision']:.4f}"
                  f"  R={r['l_recall']:.4f}")
        print(f"\n  [Game L grouping = '{args.grouping}' for both rows — one "
              f"grouping algorithm; greedy/MST differ in ordering only]")
    else:
        print("\n[Memon methods skipped - use without --skip-memon to enable]")

    # ── LLM ───────────────────────────────────────────────────────────────────
    if args.skip_llm:
        print("\n[LLM adversary skipped]")
        return results

    print("\nLLM guesses ...")
    results["LLM"] = eval_llm(true_order, true_groups, llm_order_path, llm_group_path)
    r = results["LLM"]
    
    # Check if any LLM data was loaded
    has_llm_data = not (np.isnan(r['o_tau']) and np.isnan(r['l_f1']))
    if has_llm_data:
        if not np.isnan(r['o_tau']):
            print(f"  Game O tau : {r['o_tau']:+.4f}")
        if not np.isnan(r['l_f1']):
            print(f"  Game L   : F1={r['l_f1']:.4f}  P={r['l_precision']:.4f}"
                  f"  R={r['l_recall']:.4f}")
    else:
        print(f"  No LLM guesses found (files: {llm_order_path.name}, {llm_group_path.name})")
        print(f"  LLM results will show as '-' in the table")

    return results


# ════════════════════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="Unified evaluation harness")
    parser.add_argument("--seed",       type=int,  default=DEFAULT_SEED,
                        help="RNG seed (default: 42)")
    parser.add_argument("--runs",       type=int,  default=DEFAULT_RUNS,
                        help="Random baseline repetitions (default: 10 000)")
    parser.add_argument("--skip-memon", action="store_true",
                        help="Skip Memon methods (fast mode: random + LLM only)")
    parser.add_argument("--skip-llm",   action="store_true",
                        help="Skip the LLM adversary (baselines only)")
    parser.add_argument("--grouping",   default="fixed",
                        choices=["fixed", "legacy-greedy", "legacy-mst"],
                        help="Game L grouping algorithm. Default 'fixed' is the "
                             "validated B_stat; the legacy options are degenerate "
                             "and exist only to reproduce pre-fix tables.")
    parser.add_argument("--skip-prose", action="store_true",
                        help="Skip prose corpus evaluation (identifier data only)")
    parser.add_argument("--skip-ids",   action="store_true",
                        help="Skip identifier data evaluation (prose only)")
    args = parser.parse_args()

    # One seed controls everything
    random.seed(args.seed)
    np.random.seed(args.seed)

    all_results = {}

    # ── Identifier Data ──────────────────────────────────────────────────────
    if not args.skip_ids:
        id_results = evaluate_dataset(
            ID_FRAGMENTS, ID_ANSWER_KEY, ID_LLM_ORDER, ID_LLM_GROUP,
            "IDENTIFIER DATA (4 fragments per record)", args
        )
        all_results["identifier"] = id_results
        print_comparison_table(id_results, "Identifier Data Results", 
                               seed=args.seed, n_runs=args.runs)

    # ── Prose Corpus ─────────────────────────────────────────────────────────
    if not args.skip_prose:
        prose_results = evaluate_dataset(
            PROSE_FRAGMENTS, PROSE_ANSWER_KEY, PROSE_LLM_ORDER, PROSE_LLM_GROUP,
            "PROSE CORPUS (variable fragments per record)", args
        )
        all_results["prose"] = prose_results
        print_comparison_table(prose_results, "Prose Corpus Results",
                               seed=args.seed, n_runs=args.runs)

    # ── Persist ───────────────────────────────────────────────────────────────
    out = RESULTS / "harness_results.json"
    with open(out, "w") as fh:
        json.dump(
            {
                "seed": args.seed, 
                "n_runs": args.runs,
                "skip_memon": args.skip_memon,
                "results": all_results
            },
            fh, indent=2
        )
    print(f"\nSaved: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()