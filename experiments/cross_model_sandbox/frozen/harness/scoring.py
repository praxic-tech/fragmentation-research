"""
scoring.py — Game O and Game L scoring functions.

Changes from original (week 6):
  Bug 8:  score_linkage now accepts all_fragment_ids and returns a coverage
          report. Missing/extra/duplicate fragments are caught before scoring.
  Bug 9:  empty guess returns NaN, not 0.0 — distinguishable from a wrong answer.
  (b):    check_partition validates guessed_groups is an exact partition.
  (c):    trivial_baseline computes the F1 a single-bucket strategy achieves,
          so every linkage score has its reference printed alongside it.
          NOT a "floor": an all-singleton guess scores 0, which is lower.
"""

import math
from itertools import combinations

import numpy as np
from scipy.stats import kendalltau


# ── Game O: ordering ──────────────────────────────────────────────────────────

def score_ordering(guessed_order: list, true_order: list) -> dict:
    """
    Kendall's tau between a guessed ordering and the ground truth.

    Returns {"tau": float, "pvalue": float}.
    For single-element sequences scipy returns nan; callers should skip those.
    Raises ValueError if the fragment ID sets do not match.
    """
    # Length as well as set. A guess that repeats one label and omits none has
    # the same SET as the truth but a different LENGTH, so a set-only check
    # passes it through and scipy then dies on "Array shapes are incompatible
    # for broadcasting" — a crash, not a scored result. Observed on real LLM
    # ordering output, where repeated labels are a normal failure mode.
    if len(guessed_order) != len(true_order) or set(guessed_order) != set(true_order):
        raise ValueError(
            f"guessed_order and true_order must contain the same fragment IDs "
            f"exactly once each (got {len(guessed_order)} ids, "
            f"{len(set(guessed_order))} distinct; expected {len(true_order)})"
        )

    true_rank     = {fid: i for i, fid in enumerate(true_order)}
    guessed_ranks = [true_rank[fid] for fid in guessed_order]
    true_ranks    = list(range(len(true_order)))

    result = kendalltau(guessed_ranks, true_ranks)
    return {"tau": float(result.statistic), "pvalue": float(result.pvalue)}


# ── Game L: linkage / grouping ────────────────────────────────────────────────

def _pairs_from_groups(groups: dict) -> set:
    """
    All co-member (sorted) pairs across all groups.
    groups: {any_key: [fragment_ids]}
    """
    pairs = set()
    for ids in groups.values():
        for a, b in combinations(sorted(ids), 2):
            pairs.add((a, b))
    return pairs


def trivial_baseline(true_groups: dict) -> dict:
    """
    F1 / precision / recall of putting ALL fragments into one single cluster.

    This is the minimum bar any grouping method must clear to be doing
    something useful. An F1 without this reference is uninterpretable: 0.05 is
    excellent at 500-way grouping and worthless at 7-way.

    Recall is always 1.0 for a single bucket (every true pair is inside it).
    Precision equals true_pairs / all_pairs.
    """
    group_sizes      = [len(ids) for ids in true_groups.values()]
    N                = sum(group_sizes)
    if N < 2:
        return {"precision": 0.0, "recall": 1.0, "f1": 0.0}
    true_pairs_count = sum(n * (n - 1) // 2 for n in group_sizes)
    all_pairs_count  = N * (N - 1) // 2
    if all_pairs_count == 0:
        return {"precision": 0.0, "recall": 1.0, "f1": 0.0}
    prec = true_pairs_count / all_pairs_count
    rec  = 1.0
    f1   = 2 * prec / (prec + 1.0)
    return {"precision": prec, "recall": rec, "f1": f1}


def check_partition(guessed_groups: dict, all_fragment_ids: set) -> dict:
    """
    Verify that guessed_groups is an exact partition of all_fragment_ids.

    Returns a coverage report:
        supplied   — total fragment slots (counting duplicates)
        expected   — len(all_fragment_ids)
        unique     — distinct fragment IDs in guessed_groups
        duplicates — IDs appearing more than once
        missing    — IDs in all_fragment_ids but absent from guessed_groups
        extra      — IDs in guessed_groups but not in all_fragment_ids
        valid      — True only when partition is exact
    """
    guessed_ids = []
    for ids in guessed_groups.values():
        guessed_ids.extend(ids)
    guessed_set = set(guessed_ids)
    duplicates  = len(guessed_ids) - len(guessed_set)
    missing     = all_fragment_ids - guessed_set
    extra       = guessed_set - all_fragment_ids
    return {
        "supplied":   len(guessed_ids),
        "expected":   len(all_fragment_ids),
        "unique":     len(guessed_set),
        "duplicates": duplicates,
        "missing":    len(missing),
        "extra":      len(extra),
        "valid":      duplicates == 0 and len(missing) == 0 and len(extra) == 0,
    }


def score_linkage(
    guessed_groups: dict,
    true_groups: dict,
    all_fragment_ids: set = None,
) -> dict:
    """
    Pair-based precision / recall / F1 for a grouping guess.

    Both arguments: {any_key: [fragment_ids]}.
    Keys don't need to match; only co-membership matters.

    all_fragment_ids (optional): complete set of fragment IDs that should appear
        in guessed_groups. When supplied, a coverage check is run and its report
        is included in the return value under "coverage".

    Returns:
        {
            "precision": float, "recall": float, "f1": float,
            "empty":     bool,          # True when guessed_groups is empty
            "coverage":  dict | None,   # partition validity report (if checked)
            "baseline":  dict,          # trivial single-bucket reference
        }

    Bug 9 fix: empty guess returns NaN for all three metrics, not 0.0.
    Bug 8 fix: when all_fragment_ids is provided, coverage catches missing /
        duplicated / extra fragments before scoring.
    """
    baseline = trivial_baseline(true_groups)

    # Bug 9 fix: empty guess -> NaN, not 0.0
    if not guessed_groups:
        return {
            "precision": float("nan"), "recall": float("nan"),
            "f1":        float("nan"), "empty":  True,
            "coverage":  None,         "baseline":  baseline,
        }

    # Bug 8 fix: coverage check before scoring
    coverage = None
    if all_fragment_ids is not None:
        coverage = check_partition(guessed_groups, all_fragment_ids)

    guessed_pairs = _pairs_from_groups(guessed_groups)
    true_pairs    = _pairs_from_groups(true_groups)

    tp        = len(guessed_pairs & true_pairs)
    precision = tp / len(guessed_pairs) if guessed_pairs else 0.0
    recall    = tp / len(true_pairs)    if true_pairs    else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0 else 0.0
    )
    return {
        "precision": precision, "recall": recall, "f1": f1,
        "empty":    False,      "coverage": coverage, "baseline": baseline,
    }
