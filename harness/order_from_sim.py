"""
order_from_sim.py — turn sparse pairwise precedence evidence into a total order.

A parallel module rather than an edit to orderers.py, whose legacy behaviour has
to stay reproducible.

THE PROBLEM THIS SOLVES, AND WHY IT IS NOT A TOURNAMENT
-------------------------------------------------------
The hierarchical attacker only scores pairs that candidate generation proposed.
Inside a recovered cluster of m fragments there are m(m-1)/2 possible pairs and
we will have observed a small fraction of them. So this is rank aggregation over
a SPARSE graph, and two things follow that a tournament algorithm gets wrong:

  Raw net-win is DEGREE-BIASED. A fragment with 10 scored comparisons
  accumulates a larger |sum| than one with 3, for reasons that have nothing to
  do with where it belongs. Scores are divided by observed degree.

  A cluster's comparison graph can be DISCONNECTED. Between two components
  there is literally no evidence about relative order. Emitting a total order
  anyway is fine -- the output contract demands it -- but the arbitrary part
  must be recorded, or "always returns a total order" quietly launders a
  coin-flip as attacker evidence.

THE OBJECTIVE
-------------
Maximise, over permutations, the agreement with observed directional evidence:

    sum over observed (i,j) of  w_ij * 1[pi(i) < pi(j)]

with w antisymmetric (w_ji = -w_ij), so each unordered pair contributes once.
Exact optimisation is NP-hard (this is Kemeny); we do not need exact. Initialise
with degree-normalised net-win, then improve by adjacent swaps against this
exact objective.

Two move types, because one is not enough. Adjacent swaps are cheap --
swapping neighbours a,b changes the objective by exactly -2*w_ab when (a,b) is
observed, 0 otherwise -- but they cannot escape a bad seed. On a chain every
interior fragment wins one comparison and loses one, so net-win scores them all
zero and the seed is arbitrary; adjacent swaps then converge to a local optimum
well short of the truth. Measured on a 5-fragment reversed chain: objective 2 of
a possible 4. INSERTION moves (lift one fragment, reinsert it anywhere) fix
exactly that case and are the standard neighbourhood for linear ordering.

DELIBERATELY NOT BRADLEY-TERRY
------------------------------
BT is the principled-looking choice and it is the wrong one here. Its maximum
likelihood estimate is not guaranteed to exist when the comparison graph is
insufficiently connected -- which is exactly the regime sparse top-k candidate
generation produces. The initialiser only has to be sensible; the local search
optimises the real objective either way. Adding an estimator with its own
failure mode to the highest-risk component is a bad trade.
"""

import random
from collections import defaultdict

__all__ = ["net_win_scores", "objective", "components", "order_cluster"]


def _canon(edges):
    """Normalise an edge dict to one antisymmetric entry per unordered pair.

    Accepts {(i, j): w} meaning "evidence that i precedes j". If both (i,j) and
    (j,i) are supplied they must agree in antisymmetry; the caller is expected to
    have derived one from the other, so disagreement is a bug worth surfacing.
    """
    out = {}
    for (i, j), w in edges.items():
        if i == j:
            raise ValueError(f"self-comparison for {i!r}")
        key = (i, j) if i <= j else (j, i)
        val = float(w) if i <= j else -float(w)
        if key in out and abs(out[key] - val) > 1e-9:
            raise ValueError(
                f"inconsistent evidence for {key}: {out[key]:+.4f} vs {val:+.4f}. "
                "Query each unordered pair once and derive the reverse."
            )
        out[key] = val
    return out


def net_win_scores(ids, edges):
    """Degree-normalised net-win per fragment.

    Raw sums favour whichever fragment happened to be compared more often, which
    is an artifact of candidate generation, not evidence about position.
    """
    canon = _canon(edges)
    total = defaultdict(float)
    degree = defaultdict(int)
    for (i, j), w in canon.items():
        total[i] += w
        total[j] -= w
        degree[i] += 1
        degree[j] += 1
    return {f: (total[f] / degree[f] if degree[f] else 0.0) for f in ids}


def objective(order, edges):
    """Agreement with observed evidence for a given ordering."""
    canon = _canon(edges)
    pos = {f: k for k, f in enumerate(order)}
    total = 0.0
    for (i, j), w in canon.items():
        if i not in pos or j not in pos:
            continue
        total += w if pos[i] < pos[j] else -w
    return total


def components(ids, edges):
    """Connected components of the OBSERVED-edge graph, deterministically ordered.

    Two fragments in different components have no evidence connecting them, at
    any remove. Components come back sorted by their smallest member so the
    caller's output does not depend on dict iteration order.
    """
    canon = _canon(edges)
    parent = {f: f for f in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (i, j) in canon:
        if i in parent and j in parent:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[ri] = rj

    groups = defaultdict(list)
    for f in ids:
        groups[find(f)].append(f)
    return sorted((sorted(v) for v in groups.values()), key=lambda g: g[0])


def _objective_of(order, canon):
    pos = {f: k for k, f in enumerate(order)}
    total = 0.0
    for (i, j), w in canon.items():
        if i in pos and j in pos:
            total += w if pos[i] < pos[j] else -w
    return total


def _local_search(order, canon, max_passes=64):
    """Hill climbing against the exact objective: adjacent swaps, then insertions.

    Adjacent swap: neighbours a,b swap when w_ab < 0, i.e. the evidence says b
    precedes a. Cheap, and enough for locally-wrong pairs.

    Insertion: lift one fragment and reinsert it at the best position. This is
    what escapes a flat seed. Net-win gives every interior fragment of a chain a
    score of zero -- one win, one loss -- so the seed is arbitrary there and
    adjacent swaps alone converge short of the truth.

    Deterministic: candidate moves are scanned in index order and only a strict
    improvement is taken, so equal-scoring alternatives never flip the result.

    Returns (order, swaps, converged). `converged` is True only when a complete
    pass produced no improving move -- terminating because max_passes ran out is
    a different condition and must not be reported as a local optimum.
    """
    order = list(order)
    n = len(order)
    swaps = 0

    for _ in range(max_passes):
        moved = False

        for p in range(n - 1):
            a, b = order[p], order[p + 1]
            key = (a, b) if a <= b else (b, a)
            w = canon.get(key)
            if w is None:
                continue
            w_ab = w if a <= b else -w          # evidence that a precedes b
            if w_ab < 0:
                order[p], order[p + 1] = b, a
                moved = True
                swaps += 1

        best = _objective_of(order, canon)
        for src in range(n):
            frag = order[src]
            rest = order[:src] + order[src + 1:]

            # Insertion deltas in O(n) instead of O(n * |E|).
            #
            # Moving `frag` changes the objective only through pairs that
            # involve `frag`; every other pair keeps its relative order. Let
            # w_t be the evidence that frag precedes rest[t]. Inserting at dst
            # puts frag after rest[:dst] and before rest[dst:], so its whole
            # contribution is
            #
            #     sum_{t >= dst} w_t  -  sum_{t < dst} w_t  =  total - 2*P(dst)
            #
            # with P the prefix sum of w. The objective at dst therefore
            # differs from the current one by 2*(P(src) - P(dst)), because
            # dst == src reproduces the current order exactly.
            #
            # This is the same search in the same order taking the same first
            # strict improvement -- only the arithmetic is cheaper. The naive
            # form is O(n^2 * |E|) per pass, which is fine on the hierarchical
            # attacker's sparse top-k graphs and unusable on the dense
            # within-cluster graphs the free n-gram attacker produces.
            prefix = [0.0] * (n + 1)
            for t, other in enumerate(rest):
                key = (frag, other) if frag <= other else (other, frag)
                w = canon.get(key)
                if w is None:
                    w_ft = 0.0
                else:
                    w_ft = w if frag <= other else -w
                prefix[t + 1] = prefix[t] + w_ft

            p_src = prefix[src]
            for dst in range(n):
                if dst == src:
                    continue
                if 2.0 * (p_src - prefix[dst]) > 1e-12:
                    order = rest[:dst] + [frag] + rest[dst:]
                    best = best + 2.0 * (p_src - prefix[dst])
                    moved = True
                    swaps += 1
                    break
            else:
                continue
            break

        if not moved:
            return order, swaps, True      # full pass, no move
    return order, swaps, False                                    # hit max_passes


def order_cluster(ids, edges, max_passes=64):
    """Total order over `ids` from sparse directional evidence.

    Returns (order, info). `order` contains every id exactly once, always.
    `info` records how much of that order rests on evidence:

        n_components        1 means fully connected; >1 means the inter-component
                            order is ARBITRARY and carries no evidence
        arbitrary_pairs     count of pairs whose relative order was decided by
                            the tie rule rather than by evidence
        observed_pairs      pairs that actually received a score
        possible_pairs      m(m-1)/2
        objective           agreement achieved
        objective_max       sum |w| -- the value if every observed pair were
                            satisfied; unreachable when evidence has cycles
        swaps               local-search moves

    The tie rule between components is deliberately EVIDENCE-FREE: components
    are concatenated in order of their smallest member. Ordering them by, say,
    mean score would dress an arbitrary decision as a measured one. Arbitrary is
    fine; arbitrary and labelled is honest.
    """
    ids = list(ids)
    m = len(ids)
    if m <= 1:
        return list(ids), {
            "n_components": 1 if m else 0, "arbitrary_pairs": 0,
            "observed_pairs": 0, "possible_pairs": 0,
            "objective": 0.0, "objective_max": 0.0, "swaps": 0,
            "fully_connected": True,
        }

    idset = set(ids)
    canon = {k: v for k, v in _canon(edges).items()
             if k[0] in idset and k[1] in idset}

    comps = components(ids, canon)
    scores = net_win_scores(ids, canon)

    order = []
    swaps = 0
    converged_all = True
    starts_used = 0

    for comp in comps:
        # MULTI-START. One seed is not enough: net-win is flat on a chain, so a
        # single start can sit in a poor local optimum. Three deterministic
        # starts, keeping whichever scores best on the OBSERVED-EDGE objective --
        # entirely attacker-computable, no ground truth, no model calls.
        by_score = sorted(comp, key=lambda f: (-scores[f], f))
        shuffled = list(comp)
        random.Random(hash(tuple(sorted(comp))) & 0xFFFFFFFF).shuffle(shuffled)
        best_order, best_val, best_conv, best_swaps = None, None, True, 0
        for seed_order in (by_score, list(reversed(by_score)), shuffled):
            cand, n, conv = _local_search(seed_order, canon, max_passes)
            val = _objective_of(cand, canon)
            starts_used += 1
            if best_val is None or val > best_val:
                best_order, best_val, best_conv, best_swaps = cand, val, conv, n
        order.extend(best_order)
        swaps += best_swaps
        converged_all = converged_all and best_conv

    # pairs whose relative order no evidence path could have determined
    sizes = [len(c) for c in comps]
    arbitrary = sum(a * b for i, a in enumerate(sizes) for b in sizes[i + 1:])

    return order, {
        "n_components": len(comps),
        "component_sizes": sizes,
        "converged": converged_all,
        "starts": starts_used,
        "arbitrary_pairs": arbitrary,
        "observed_pairs": len(canon),
        "possible_pairs": m * (m - 1) // 2,
        "objective": objective(order, canon),
        "objective_max": sum(abs(w) for w in canon.values()),
        "swaps": swaps,
        "fully_connected": len(comps) == 1,
    }
