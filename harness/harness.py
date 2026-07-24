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

from loader  import (load_fragments, load_answer_key,
                     group_fragments_by_record,
                     load_llm_ordering_guesses,
                     load_llm_grouping_guesses)
from orderers import (random_order,    random_grouping,
                      greedy_nn_order, greedy_grouping,
                      mst_order,       mst_grouping)
from scoring  import score_ordering, score_linkage

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
    
    Returns:
        masked_fragments: list of fragments with masked IDs
        id_map: dict mapping masked_id -> original_id
    """
    masked_fragments = []
    id_map = {}
    for f in fragments:
        # Generate a random ID
        masked_id = f"m_{random.randint(100000, 999999)}"
        id_map[masked_id] = f["fragment_id"]
        masked_fragments.append({
            "fragment_id": masked_id,
            "text": f["text"]
        })
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
# Per-method evaluators
# ════════════════════════════════════════════════════════════════════════════════

def _avg_ordering_tau(fragments, true_order, order_fn) -> float:
    """
    Run order_fn on each record, compute per-record Kendall's tau,
    return the mean (NaN records skipped).
    """
    grouped = group_fragments_by_record(fragments)
    taus    = []
    for rec_id, frag_ids in grouped.items():
        try:
            guess = order_fn(frag_ids)
            # Check if lengths match
            if len(guess) != len(frag_ids):
                continue
            # Check if all fragment IDs are present
            if set(guess) != set(frag_ids):
                continue
            result = score_ordering(guess, true_order[rec_id])
            if not np.isnan(result["tau"]):
                taus.append(result["tau"])
        except Exception:
            continue
    return float(np.mean(taus)) if taus else float("nan")


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

def eval_memon(fragments, true_order, true_groups, method: str) -> dict:
    """
    Evaluate one Memon strategy ('greedy' or 'mst') on both games.
    Returns a result dict ready for the comparison table.
    """
    text_by_id = {f["fragment_id"]: f["text"] for f in fragments}
    n_groups   = len(true_groups)

    # Mask fragment IDs for Game L (prevents ID leakage)
    masked_fragments, id_map = mask_fragment_ids(fragments)

    # Game O - uses original fragments and text_by_id
    if method == "greedy":
        o_tau = _avg_ordering_tau(
            fragments, true_order,
            order_fn=lambda ids: greedy_nn_order(ids, text_by_id)
        )
        masked_groups = greedy_grouping(masked_fragments, n_groups)
    else:
        o_tau = _avg_ordering_tau(
            fragments, true_order,
            order_fn=lambda ids: mst_order(ids, text_by_id)
        )
        masked_groups = mst_grouping(masked_fragments, n_groups)

    # Convert masked IDs back to original IDs for scoring
    unmasked_groups = unmask_groups(masked_groups, id_map)
    l_scores = score_linkage(unmasked_groups, true_groups)

    return {
        "o_tau":       o_tau,
        "o_tau_std":   float("nan"),
        "l_precision": l_scores["precision"],
        "l_recall":    l_scores["recall"],
        "l_f1":        l_scores["f1"],
    }


# ── LLM ───────────────────────────────────────────────────────────────────────

def eval_llm(true_order, true_groups, llm_order_path, llm_group_path) -> dict:
    """
    Load and score pre-computed LLM guesses.
    Gracefully handles missing files without crashing.
    """
    # Game O
    o_tau = float("nan")
    if llm_order_path.exists():
        try:
            guesses = load_llm_ordering_guesses(llm_order_path)
            taus    = []
            for rec_id, guessed_order in guesses.items():
                if rec_id not in true_order:
                    continue
                r = score_ordering(guessed_order, true_order[rec_id])
                if not np.isnan(r["tau"]):
                    taus.append(r["tau"])
            if taus:
                o_tau = float(np.mean(taus))
        except Exception as e:
            print(f"  [warn] Error loading LLM ordering guesses: {e}")
    # If file doesn't exist, silently skip (o_tau stays NaN)

    # Game L
    l_scores = {"precision": float("nan"), "recall": float("nan"), "f1": float("nan")}
    if llm_group_path.exists():
        try:
            llm_groups = load_llm_grouping_guesses(llm_group_path)
            l_scores   = score_linkage(llm_groups, true_groups)
        except Exception as e:
            print(f"  [warn] Error loading LLM grouping guesses: {e}")
    # If file doesn't exist, silently skip (l_scores stay NaN)

    return {
        "o_tau":       o_tau,
        "o_tau_std":   float("nan"),
        "l_precision": l_scores["precision"],
        "l_recall":    l_scores["recall"],
        "l_f1":        l_scores["f1"],
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
    cw = [15, 24, 24, 10, 10, 10]
    headers = [
        "Method",
        "Game O tau (mean+/-std)",
        "Game O tau +/-2sigma CI",
        "L: F1",
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
            _f(r["l_f1"],        9).strip(),
            _f(r["l_precision"], 9).strip(),
            _f(r["l_recall"],    9).strip(),
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
                fragments, true_order, true_groups, method
            )
            r = results[label]
            print(f"  Game O tau : {r['o_tau']:+.4f}")
            print(f"  Game L   : F1={r['l_f1']:.4f}  P={r['l_precision']:.4f}"
                  f"  R={r['l_recall']:.4f}")
    else:
        print("\n[Memon methods skipped - use without --skip-memon to enable]")

    # ── LLM ───────────────────────────────────────────────────────────────────
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
    print(f"\nSaved: {out.relative_to(BASE)}")


if __name__ == "__main__":
    main()