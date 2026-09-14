"""
harness.py — Unified evaluation harness.

Evaluates four strategies on Game O (ordering) and Game L (grouping) for:
    - Identifier data (fixed 4 fragments per record)
    - Prose corpus (variable fragments per record)

Strategies:
    Random      — uniform random, repeated N_RUNS times → distribution stats
    Jaccard-Greedy — greedy nearest-neighbour over word-bigram Jaccard (classical game-O floor)
    Jaccard-MST    — maximum spanning tree path, same similarity (classical game-O floor)
                     Michael's orderers, formerly mislabelled "Memon-Greedy / Memon-MST".
                     NOT Memon-inspired: symmetric word overlap, no PPM, no Hamiltonian-path
                     search. Their game L column is the shared TF-IDF grouper, not a Jaccard
                     linkage attack. Names and definitions: docs/adversaries.md (2026-09-13).
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
from masking import assert_ids_masked
import hashlib

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
# Cell status constants and coverage reporting
# ════════════════════════════════════════════════════════════════════════════════

# Three distinct LLM cell states carried in every return dict so run_grid.py
# can branch on them without parsing stdout.
STATUS_NOT_SUBMITTED = "not_submitted"   # file never existed
STATUS_LOAD_FAILED   = "load_failed"     # file exists but threw on load
STATUS_SCORED        = "scored"          # loaded and scored (may be quarantined)


def _coverage_line(game: str, scored: int, supplied: int,
                   expected: int, malformed: int,
                   partition_valid: bool = True,
                   status: str = STATUS_SCORED) -> tuple:
    """
    Build the coverage line string and a quarantine bool for one game.

    Returns (line: str, quarantined: bool).

    Issue 2 fix: three distinct states produce three distinct messages.
      not_submitted -> informational only, never quarantined by itself.
      load_failed   -> always quarantined.
      scored        -> quarantined only when coverage is actually bad.

    Issue 3 fix: partition_valid=False triggers quarantine even when
      unique == expected (duplicates that cancel with extras).
    """
    if status == STATUS_NOT_SUBMITTED:
        return f"  {game}: not submitted", False
    if status == STATUS_LOAD_FAILED:
        return f"  [QUARANTINE] {game}: file load failed", True
    # status == STATUS_SCORED
    detail   = f"scored={scored}/{supplied}/{expected}  malformed={malformed}"
    bad      = scored < expected or malformed > 0 or not partition_valid
    dup_note = "" if partition_valid else "  partition_valid=False"
    if bad:
        return f"  [QUARANTINE] {game}: {detail}{dup_note}", True
    return f"  {game} coverage: {detail}", False


# ════════════════════════════════════════════════════════════════════════════════
# Per-method evaluators
# ════════════════════════════════════════════════════════════════════════════════

def _avg_ordering_tau(fragments, true_order, order_fn) -> dict:
    """
    Run order_fn on each record, compute per-record Kendall's tau.

    Bug 10 fix: old version had a bare except that silently swallowed errors
    and id-set mismatches, so "mean tau 0.70" could be the mean over 500
    records or over 12 with no way to tell. This version tracks every skip
    and error and returns them alongside the mean so the caller can print
    the coverage line and quarantine cells where scored < expected.

    Returns:
        {"tau", "scored", "supplied", "expected", "skipped", "errors"}
    """
    grouped  = group_fragments_by_record(fragments)
    taus     = []
    skipped  = 0
    errors   = 0
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
        "supplied": len(grouped),
        "expected": len(true_order),
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


# ── Jaccard-Greedy / Jaccard-MST (classical orderers; the function names below keep
#    the historical "memon" spelling, see docs/adversaries.md) ──────────────────────────────────────────────────────

def _masked_shuffled_order(order_fn, frag_ids, text_by_id, seed):
    """Run a classic orderer on MASKED labels in a SEEDED, SHUFFLED presentation.

    Superseded (docs/RUN_DECISIONS.md D1): Game O handed the orderers the raw
    fragment ids in true order. Word-bigram Jaccard is exactly 0 for 86.7% of
    within-document pairs, so almost every step was a tie, and ties went to the
    raw id or the list position -- both of which reproduce the true order.
    Measured on the prose corpus: Greedy tau +0.3232 and MST +0.7044 as run,
    -0.0304 and -0.0175 masked and shuffled. Those O numbers were leakage.

    The seed is sha256 of the document's fragment set plus the run seed: the
    same in every process (never Python's hash()), and carrying no information
    about the true order. It uses its OWN generator, so the global stream that
    drives the random baseline and the Game L masking is not consumed.
    """
    ids = list(frag_ids)
    digest = hashlib.sha256(("|".join(sorted(ids)) + f"#{seed}").encode("utf-8"))
    rng = random.Random(int(digest.hexdigest()[:16], 16))
    labels = [f"m_{i:07d}" for i in range(len(ids))]
    rng.shuffle(labels)
    lab2id = dict(zip(labels, ids))
    shown = list(labels)
    rng.shuffle(shown)
    assert_ids_masked(shown, where=f"classic {order_fn.__name__}")
    ltext = {lab: text_by_id[lab2id[lab]] for lab in shown}
    return [lab2id[lab] for lab in order_fn(shown, ltext)]


def eval_memon(fragments, true_order, true_groups, method: str,
               grouping_variant: str = "fixed", seed: int = DEFAULT_SEED,
               legacy_unmasked_order: bool = False) -> dict:
    """
    Evaluate one classical Jaccard orderer (Jaccard-Greedy / Jaccard-MST) on both games.
    Historical name; not a Memon implementation (docs/adversaries.md).

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

    # Game O -- masked labels, seeded shuffled presentation (D1). The legacy
    # path is kept ONLY to reproduce the superseded numbers for the audit record.
    base_fn = {"greedy": greedy_nn_order, "mst": mst_order}.get(method)
    if base_fn is None:
        raise ValueError(f"unknown ordering method {method!r}")
    if legacy_unmasked_order:
        order_fn = lambda ids: base_fn(ids, text_by_id)
    else:
        order_fn = lambda ids: _masked_shuffled_order(base_fn, ids, text_by_id, seed)

    o_cov = _avg_ordering_tau(fragments, true_order, order_fn=order_fn)
    o_tau = o_cov["tau"]
    o_line, o_q = _coverage_line(
        "Game O", o_cov["scored"], o_cov["supplied"],
        o_cov["expected"], o_cov["errors"], status=STATUS_SCORED)
    print(o_line)

    masked_groups = memon_grouping(masked_fragments, n_groups,
                                   variant=grouping_variant)
    # Bug 11 fix: validate grouping returned exactly the requested count
    count_ok = len(masked_groups) == n_groups
    if not count_ok:
        print(f"  [QUARANTINE] Game L: grouping returned {len(masked_groups)} "
              f"groups, expected {n_groups}")

    unmasked_groups = unmask_groups(masked_groups, id_map)
    all_ids  = {f["fragment_id"] for f in fragments}
    l_scores = score_linkage(unmasked_groups, true_groups,
                             all_fragment_ids=all_ids)

    # Issue 1 fix: extract l_coverage fields into return dict
    l_cov        = l_scores.get("coverage") or {}
    l_scored     = l_cov.get("unique", 0)
    l_supplied   = l_cov.get("supplied", 0)
    l_expected   = len(all_ids)
    l_valid      = l_cov.get("valid", True)
    l_duplicates = l_cov.get("duplicates", 0)
    l_missing    = l_cov.get("missing", 0)

    l_line, l_q = _coverage_line(
        "Game L", l_scored, l_supplied, l_expected, 0,
        partition_valid=l_valid,   # Issue 3 fix
        status=STATUS_SCORED)
    print(l_line)
    if not count_ok:
        l_q = True

    quarantine_reasons = (
        (["game_o_coverage"] if o_q else []) +
        (["game_l_coverage"] if l_q else []) +
        (["game_l_count_mismatch"] if not count_ok else [])
    )

    return {
        "o_tau":       o_tau,  "o_tau_std":   float("nan"),
        "o_status":    STATUS_SCORED,
        "o_scored":    o_cov["scored"],   "o_supplied": o_cov["supplied"],
        "o_expected":  o_cov["expected"],
        "l_precision": l_scores["precision"],
        "l_recall":    l_scores["recall"],
        "l_f1":        l_scores["f1"],
        "l_baseline":  l_scores["baseline"]["f1"],
        "l_status":    STATUS_SCORED,
        "l_scored":    l_scored,   "l_supplied":  l_supplied,
        "l_expected":  l_expected, "l_valid":     l_valid,
        "l_duplicates": l_duplicates, "l_missing": l_missing,
        "quarantined":       len(quarantine_reasons) > 0,
        "quarantine_reasons": quarantine_reasons,
    }


# ── LLM ───────────────────────────────────────────────────────────────────────

def eval_llm(true_order, true_groups, llm_order_path, llm_group_path) -> dict:
    """
    Load and score pre-computed LLM guesses.

    Bug 7 fix:    per-record try for Game O so one bad record cannot abort
                  the whole scoring loop.
    Issue 2 fix:  three distinct cell states (not_submitted / load_failed /
                  scored) carried in the return dict so run_grid.py can
                  distinguish "batch hasn't landed yet" from "landed broken".
    Issue 1 fix:  l_coverage fields (l_scored, l_supplied, l_expected,
                  l_valid, l_duplicates, l_missing) included in return dict.
    Issue 3 fix:  partition_valid=False gates quarantine, not just counts.
    """
    quarantine_reasons = []

    # ── Game O ────────────────────────────────────────────────────────────────
    o_status   = STATUS_NOT_SUBMITTED
    o_tau      = float("nan")
    o_scored   = 0; o_supplied = 0; o_malformed = 0
    o_expected = len(true_order)

    if llm_order_path.exists():
        o_status = STATUS_LOAD_FAILED          # pessimistic until success
        try:
            guesses    = load_llm_ordering_guesses(llm_order_path)
            o_status   = STATUS_SCORED
            o_supplied = len(guesses)
            taus       = []
            for rec_id, guessed_order in guesses.items():
                if rec_id not in true_order:
                    o_malformed += 1; continue
                try:                            # Bug 7 fix: per-record try
                    r = score_ordering(guessed_order, true_order[rec_id])
                    if not np.isnan(r["tau"]): taus.append(r["tau"])
                    else: o_malformed += 1
                except Exception:
                    o_malformed += 1
            o_scored = len(taus)
            if taus: o_tau = float(np.mean(taus))
        except Exception as e:
            print(f"  [warn] Game O file load failed: {e}")
            # o_status stays STATUS_LOAD_FAILED

    o_line, o_q = _coverage_line("Game O", o_scored, o_supplied, o_expected,
                                  o_malformed, status=o_status)
    print(o_line)
    if o_q: quarantine_reasons.append("game_o_coverage")

    # ── Game L ────────────────────────────────────────────────────────────────
    l_status = STATUS_NOT_SUBMITTED
    l_scores = {
        "precision": float("nan"), "recall": float("nan"),
        "f1":        float("nan"), "empty": True,
        "coverage":  None,         "baseline": {"f1": float("nan")},
    }

    if llm_group_path.exists():
        l_status = STATUS_LOAD_FAILED          # pessimistic until success
        try:
            llm_groups = load_llm_grouping_guesses(llm_group_path)
            l_status   = STATUS_SCORED
            all_ids    = {fid for ids in true_groups.values() for fid in ids}
            l_scores   = score_linkage(llm_groups, true_groups,
                                       all_fragment_ids=all_ids)
        except Exception as e:
            print(f"  [warn] Game L file load failed: {e}")

    # Issue 1 fix: extract l_coverage into return dict
    l_cov      = l_scores.get("coverage") or {}
    l_scored   = l_cov.get("unique", 0)
    l_supplied = l_cov.get("supplied", 0)
    l_expected = sum(len(ids) for ids in true_groups.values())
    l_valid    = l_cov.get("valid", True)
    l_dup      = l_cov.get("duplicates", 0)
    l_missing  = l_cov.get("missing", 0)

    l_line, l_q = _coverage_line(
        "Game L", l_scored, l_supplied, l_expected, 0,
        partition_valid=l_valid,   # Issue 3 fix
        status=l_status)
    print(l_line)
    if l_q: quarantine_reasons.append("game_l_coverage")

    return {
        "o_tau":      o_tau,  "o_tau_std":  float("nan"),
        "o_status":   o_status,
        "o_scored":   o_scored,   "o_supplied": o_supplied,
        "o_expected": o_expected,
        "l_precision": l_scores["precision"],
        "l_recall":    l_scores["recall"],
        "l_f1":        l_scores["f1"],
        "l_baseline":  l_scores["baseline"]["f1"],
        "l_status":    l_status,
        "l_scored":    l_scored,   "l_supplied": l_supplied,
        "l_expected":  l_expected, "l_valid":    l_valid,
        "l_duplicates": l_dup,     "l_missing":  l_missing,
        "quarantined":       len(quarantine_reasons) > 0,
        "quarantine_reasons": quarantine_reasons,
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
        "L: base",
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
            _f(r["l_f1"],                        9).strip(),
            _f(r.get("l_baseline", float("nan")),   9).strip(),
            _f(r["l_precision"],                 9).strip(),
            _f(r["l_recall"],                    9).strip(),
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
    from scoring import trivial_baseline as _trivial_baseline
    results["Random"] = {
        "o_tau":       float(o_taus.mean()),
        "o_tau_std":   float(o_taus.std(ddof=1)),
        "l_precision": float(l_ps.mean()),
        "l_recall":    float(l_rs.mean()),
        "l_f1":        float(l_fs.mean()),
        "l_baseline":  _trivial_baseline(true_groups)["f1"],  # Item (c)
        "quarantined": False,
        "quarantine_reasons": [],
    }
    print(f"  Game O tau : {o_taus.mean():+.4f} +- {o_taus.std(ddof=1):.4f}"
          f"   2sigma CI [{o_taus.mean()-2*o_taus.std(ddof=1):+.4f},"
          f" {o_taus.mean()+2*o_taus.std(ddof=1):+.4f}]")
    print(f"  Game L F1: {l_fs.mean():.4f} +- {l_fs.std(ddof=1):.4f}")

    # ── Memon strategies ──────────────────────────────────────────────────────
    if not args.skip_memon:
        labels = [("greedy", "Jaccard-Greedy"), ("mst", "Jaccard-MST")]
        if args.legacy_unmasked_order:
            labels = [(m, f"{l} [LEGACY-LEAKS, audit only]") for m, l in labels]
        for method, label in labels:
            print(f"\n{label} ...")
            results[label] = eval_memon(
                fragments, true_order, true_groups, method,
                grouping_variant=args.grouping, seed=args.seed,
                legacy_unmasked_order=args.legacy_unmasked_order
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
    parser.add_argument("--legacy-unmasked-order", action="store_true",
                        help="AUDIT ONLY: reproduce the superseded, leaking Game O "
                             "numbers (raw ids, true order). Writes a separate file.")
    args = parser.parse_args()
    if args.legacy_unmasked_order:
        print("AUDIT ONLY: Game O on raw fragment ids in true order -- the "
              "superseded configuration. These numbers are leakage, not ordering "
              "ability (docs/RUN_DECISIONS.md D1).")

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
    out = RESULTS / ("harness_results_LEGACY_AUDIT.json"
                     if args.legacy_unmasked_order else "harness_results.json")
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