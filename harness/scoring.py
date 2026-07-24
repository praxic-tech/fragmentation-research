"""
scoring.py — Game O and Game L scoring functions.
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
    """
    if set(guessed_order) != set(true_order):
        raise ValueError(
            "guessed_order and true_order must contain the same fragment IDs"
        )

    true_rank = {fid: i for i, fid in enumerate(true_order)}
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


def score_linkage(guessed_groups: dict, true_groups: dict) -> dict:
    """
    Pair-based precision / recall / F1 for a grouping guess.

    Both arguments: {any_key: [fragment_ids]}.
    The keys don't need to match; only co-membership matters.

    Returns {"precision": float, "recall": float, "f1": float}.
    """
    guessed_pairs = _pairs_from_groups(guessed_groups)
    true_pairs    = _pairs_from_groups(true_groups)

    tp        = len(guessed_pairs & true_pairs)
    precision = tp / len(guessed_pairs) if guessed_pairs else 0.0
    recall    = tp / len(true_pairs)    if true_pairs    else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0 else 0.0
    )
    return {"precision": precision, "recall": recall, "f1": f1}
