"""
joint_metrics.py — one scoring surface for every attacker.

An attacker's answer is a PARTITION WITH AN ORDER INSIDE EACH GROUP: a list of
lists of fragment ids. One-shot J emits that from a single prompt, the
hierarchical attacker emits it from a graph solve, Memon emits it from grouping
plus a directional statistic. None of that is visible here, and it must not
become visible — an attacker-specific branch in scoring is how two attackers
stop being comparable.

THE HEADLINE METRIC: ordered-pair F1
------------------------------------
Game L counted unordered co-membership pairs: for {a,b}, same document? This
counts the same pairs WITH direction: for (a,b), same document AND a before b.

    true ordered pairs      one per true co-member pair, in the true direction
    guessed ordered pairs   one per guessed co-member pair, in the guessed one
    C                       co-member in truth AND direction matches
    precision C/|guessed|   recall C/|true|      F1 the harmonic mean

It generalises both metrics already in use rather than adding a third scale:

    ignore direction            -> exactly the old score_linkage F1
    perfect membership          -> the CONCORDANCE FRACTION, i.e. (1+tau)/2

That second identity is worth stating precisely, because getting it wrong is
easy: F1_J does NOT reduce to Kendall's tau. Random ordering gives F1_J = 0.5
and tau = 0; full reversal gives F1_J = 0 and tau = -1. The relationship is
F1_J = (1+tau)/2.

Because a group of m fragments contributes exactly one ordered pair per
unordered pair, |guessed ordered| = |guessed unordered| = P and likewise for
truth, which gives the decomposition

    F1_J = F1_L * (C/K)          linkage F1 x conditional direction accuracy

where K is the count of correctly co-clustered pairs ignoring direction. That
factorisation is the clean answer to "which half failed", and it replaces the
old J-minus-O gap, which confounded scale with task coupling.

DISCLOSED EDGE CASE
-------------------
A perfectly grouped but fully REVERSED document scores 0, because every pair
points the wrong way. That agrees with tau = -1 on the same output, but a
reversed reconstruction is arguably complete in information terms, so it belongs
in the methods section rather than in a footnote.

BASELINE, NOT FLOOR
-------------------
The reference point is "put everything in one bucket in an arbitrary order".
That is a trivial BASELINE, not a floor: an all-singleton answer scores 0, which
is lower. The word matters because a floor implies nothing can go beneath it.

The baseline is computed ANALYTICALLY, not by sampling. For one bucket of M
fragments with true group sizes m_d:

    T = sum over d of C(m_d, 2)      true within-document pairs
    P = C(M, 2)                       pairs created by the single bucket
    E[F1_L] = 2T/(P+T)                every true pair is inside the bucket
    E[F1_J] =  T/(P+T)                random direction is right half the time

so the joint baseline is exactly half the linkage baseline. Sampling it instead
was measurably noisy and, on a small pool, landed on 0 by luck.
"""

from itertools import combinations

__all__ = [
    "ordered_pairs", "unordered_pairs",
    "score_joint", "analytic_baseline", "decompose",
    "advantage", "paired_bootstrap_indices", "micro_q",
]


# ── pair extraction ──────────────────────────────────────────────────────────

def ordered_pairs(groups):
    """Every (earlier, later) pair implied by a list of ORDERED groups."""
    out = set()
    for g in groups:
        for i, a in enumerate(g):
            for b in g[i + 1:]:
                out.add((a, b))
    return out


def unordered_pairs(groups):
    """Every co-membership pair, direction discarded."""
    return {frozenset((a, b)) for g in groups for a, b in combinations(g, 2)}


def _true_groups_as_lists(true_order, members):
    return [true_order[r] for r in members]


# ── the headline metric ──────────────────────────────────────────────────────

def score_joint(guessed_groups, true_order, members):
    """Ordered-pair precision / recall / F1 for a partition-with-order.

    guessed_groups : list of lists of fragment ids, ordered within each group
    true_order     : {record_id: [fragment ids in true order]}
    members        : record_ids belonging to this pool
    """
    guessed = ordered_pairs(guessed_groups)
    truth = ordered_pairs(_true_groups_as_lists(true_order, members))
    tp = len(guessed & truth)
    p = tp / len(guessed) if guessed else 0.0
    r = tp / len(truth) if truth else 0.0
    return {
        "precision": p,
        "recall": r,
        "f1": 2 * p * r / (p + r) if (p + r) else 0.0,
        "tp": tp,
        "n_guessed": len(guessed),
        "n_true": len(truth),
    }


def analytic_baseline(true_groups):
    """EXPECTED score of one bucket under a RANDOM order. Closed form.

    Not the score of one particular arbitrary ordering -- a fixed ordering has
    a definite score that can sit well above or below this. This is the
    expectation over orderings, which is exactly why the joint value is half
    the linkage value: a random direction is right half the time.

    true_groups : {record_id: [fragment ids]} — only the SIZES are used.
    Returns {"joint": ..., "linkage": ...} with joint == linkage / 2 exactly.
    """
    sizes = [len(v) for v in true_groups.values()]
    m = sum(sizes)
    t = sum(s * (s - 1) // 2 for s in sizes)
    p = m * (m - 1) // 2
    if p + t == 0:
        return {"joint": 0.0, "linkage": 0.0, "true_pairs": t, "bucket_pairs": p}
    return {
        "joint": t / (p + t),
        "linkage": 2 * t / (p + t),
        "true_pairs": t,
        "bucket_pairs": p,
    }


def advantage(f1, baseline):
    """A = (F1 - baseline) / (1 - baseline). 0 at baseline, 1 at perfect.

    Negative when the attack does worse than one bucket. MUST be computed per
    pool and then averaged: the baseline moves with each pool's fragment-count
    distribution, so normalising grand means is a different quantity.
    """
    denom = 1.0 - baseline
    if denom <= 0:
        return float("nan")
    return (f1 - baseline) / denom


# ── decomposition ────────────────────────────────────────────────────────────

def decompose(guessed_groups, true_order, members):
    """Split joint performance into linkage and conditional direction accuracy.

    Returns, per pool:
        f1_joint, f1_linkage   on the same scale, F1_J = F1_L * q
        C  correctly co-clustered AND correctly directed pairs
        K  correctly co-clustered pairs, direction ignored
        q  C/K, or None when K == 0
        a_joint, a_linkage     baseline-normalised advantages
        a_order                2q - 1, or None when q is None

    q is UNDEFINED when K == 0, and is reported as None rather than 0. Coercing
    it to zero converts "ordering could not be evaluated because linkage failed
    completely" into "ordering was completely wrong", which are different
    findings. Callers aggregate with micro_q() and report the undefined rate.
    """
    truth_lists = _true_groups_as_lists(true_order, members)
    g_ord, t_ord = ordered_pairs(guessed_groups), ordered_pairs(truth_lists)
    g_un, t_un = unordered_pairs(guessed_groups), unordered_pairs(truth_lists)

    c = len(g_ord & t_ord)
    k = len(g_un & t_un)
    denom = len(g_un) + len(t_un)

    f1_joint = 2 * c / denom if denom else 0.0
    f1_link = 2 * k / denom if denom else 0.0

    true_groups = {r: true_order[r] for r in members}
    base = analytic_baseline(true_groups)

    q = (c / k) if k else None
    return {
        "f1_joint": f1_joint,
        "f1_linkage": f1_link,
        "C": c,
        "K": k,
        "q": q,
        "baseline_joint": base["joint"],
        "baseline_linkage": base["linkage"],
        "a_joint": advantage(f1_joint, base["joint"]),
        "a_linkage": advantage(f1_link, base["linkage"]),
        "a_order": (2 * q - 1) if q is not None else None,
        "n_guessed_pairs": len(g_un),
        "n_true_pairs": len(t_un),
    }


def micro_q(rows):
    """Direction accuracy aggregated as sum(C)/sum(K) across pools.

    Returns (q, n_undefined_pools). q is None when sum(K) == 0 over the whole
    collection — which is also the behaviour a bootstrap replicate needs, since
    a resample can legitimately contain only pools where linkage failed.
    """
    total_c = sum(r["C"] for r in rows)
    total_k = sum(r["K"] for r in rows)
    undefined = sum(1 for r in rows if r["K"] == 0)
    return ((total_c / total_k) if total_k else None), undefined


# ── resampling ───────────────────────────────────────────────────────────────

def paired_bootstrap_indices(n_pools, n_replicates, rng):
    """Pool indices for a PAIRED bootstrap, one index vector per replicate.

    Every strategy and every attacker must be resampled with the SAME indices
    within a replicate. The shared-pool grid exists to buy that pairing, and
    resampling each cell independently throws it away — silently, since the
    output still looks like a distribution.

    Yielding the indices rather than the resampled data keeps the sharing
    structural: a caller cannot accidentally draw a second time.
    """
    for _ in range(n_replicates):
        yield [int(i) for i in rng.integers(0, n_pools, size=n_pools)]
