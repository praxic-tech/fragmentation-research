
"""
sparse_cluster.py — cluster fragments from SPARSE membership evidence.

Membership scores exist only for pairs that candidate generation proposed. Most
pairs were never asked about. Every clustering algorithm has to decide what an
unobserved pair means, and that decision — not the model's answers — can end up
determining J-linkage.

FILLING MISSING ENTRIES WITH ZERO IS FORBIDDEN
----------------------------------------------
Zero means "definitely different documents". We never asked. Asserting a
confident negative on the strength of not having looked is the single easiest
way to manufacture a linkage result, and it would be invisible: the numbers come
out looking entirely reasonable.

So this is graph-native. Only observed edges exist; absence is absence.

    1. Build a graph from scored M_ij edges only.
    2. If the graph has MORE than N components, evidence is too sparse to reach
       N groups -- request bridge comparisons until it has at most N.
    3. Merge deterministically by descending M_ij and STOP at exactly N.

That is sparse single-linkage with a stopping rule, which is auditable in a way
that "average linkage over an imputed matrix" is not. If average-linkage is
wanted later, the rule for how a missing M_ij enters a cluster-to-cluster
average has to be written down first, because there is no neutral choice.

WHY NOT fcluster(..., criterion="maxclust")
-------------------------------------------
It returns AT MOST t clusters, not exactly t. On tie-heavy matrices it silently
returns fewer. Our matrices are tie-heavy -- the identifier similarity matrix is
83.5% exact zeros, which is why B_stat needs jitter at all. The primary
condition hands the attacker the exact document count, so an attacker that fails
to produce exactly N groups is failing to use side information we deliberately
gave it, and the known/unknown-N sensitivity stops being clean.

Here N is a stopping condition on a merge loop, so it is exact by construction.
"""

from collections import defaultdict

__all__ = ["cluster_known_n", "connected_components", "bridge_candidates"]


def connected_components(ids, edges):
    """Components of the observed-edge graph, deterministically ordered.

    edges: {(i, j): score} for observed pairs only. Any score present counts as
    a link for connectivity purposes -- connectivity asks whether we have ANY
    evidence relating two fragments, not whether that evidence was positive.
    """
    parent = {f: f for f in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for (i, j) in edges:
        if i in parent and j in parent:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[ri] = rj

    groups = defaultdict(list)
    for f in ids:
        groups[find(f)].append(f)
    return sorted((sorted(v) for v in groups.values()), key=lambda g: g[0])


def bridge_candidates(components_list, sim=None, n_target=None,
                      per_link=1):
    """Cross-component pairs to score next, SIZED TO WHAT IS NEEDED.

    The previous version emitted one pair for every pair of components -- C(c,2).
    At 50 components that is 1,225 extra model queries and at 100 it is 4,950,
    for a job that needs at most c - N links to bring c components down to N.
    It also picked lexicographic representatives, so the proposals were not the
    most promising cross-component candidates, just the alphabetically first.

    Now: build a component-level MAXIMUM SPANNING FOREST using the blocker
    similarity, and propose only the edges on it, best first. That is c-1 links
    to fully connect, or c - n_target when a target is given.

    sim(a, b) -> float. Without it, falls back to lexicographic representatives
    and a spanning chain, still c-1 rather than C(c,2).
    """
    c = len(components_list)
    if c < 2:
        return []
    need = c - 1 if n_target is None else max(0, c - n_target)
    if need == 0:
        return []

    if sim is None:
        # No similarity available: a chain still connects everything in c-1.
        chain = []
        for a in range(c - 1):
            for t in range(min(per_link, len(components_list[a]),
                               len(components_list[a + 1]))):
                chain.append((components_list[a][t], components_list[a + 1][t]))
        return chain[:need * per_link]

    # Best cross-component pair for every component pair, then a greedy maximum
    # spanning forest over components.
    best = {}
    for a in range(c):
        for b in range(a + 1, c):
            top = None
            for x in components_list[a]:
                for y in components_list[b]:
                    sv = sim(x, y)
                    if top is None or sv > top[0]:
                        top = (sv, x, y)
            if top is not None:
                best[(a, b)] = top

    parent = list(range(c))

    def find(v):
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v

    out = []
    for (a, b), (_sv, x, y) in sorted(best.items(),
                                      key=lambda kv: (-kv[1][0], kv[0])):
        ra, rb = find(a), find(b)
        if ra == rb:
            continue
        parent[rb] = ra
        pair = (x, y) if x <= y else (y, x)
        out.append(pair)
        if len(out) >= need:
            break
    return out


def _signed_merge(ids, obs, n_clusters):
    """Agglomerate on AGGREGATED signed evidence over observed edges only.

    s_ij = 2*M_ij - 1, so a confident "same" is +1, a confident "different" is
    -1, and total uncertainty is 0. The gain from merging clusters A and B is

        delta(A, B) = sum of s_ij over OBSERVED (i in A, j in B) pairs

    Unobserved pairs contribute no term. That is not the same as scoring them 0,
    0.5, or anything else -- there is simply nothing to add. So this aggregates
    without imputing, which was the objection to average-linkage.

    Why it exists: single-linkage merges on the single best edge, so ONE
    erroneous high-confidence pair welds two documents and the error cascades.
    Measured on a synthetic oracle, accuracy 100% -> 75% dropped joint F1 from
    1.0000 to 0.2667. Aggregating lets several negative observed edges outvote
    one wrong positive.

    Bounded 2M-1 rather than log-odds deliberately: LLM probability calibration
    is unknown, and log-odds gives unbounded weight to a confidently wrong edge,
    which is the failure mode being fixed.

    MEASURED LIMIT, do not overclaim this. Aggregation only helps once clusters
    HAVE members. When the erroneous edge is the global maximum and both its
    endpoints are still singletons, greedy commits to it on the first merge and
    a sum of one term is just that term. Measured on a 6-fragment poisoned case:

        poison is the global max   single -> sizes [1, 5]   signed -> [2, 4]
                                   neither recovers the truth
        clusters already formed    single follows the poison
                                   signed rejects it, 3 negatives outvoting 1

    So signed is strictly less catastrophic and correct in the second regime,
    but it is not a fix for greedy's irrevocable first merge. Escaping that
    needs a non-greedy objective or a merge-undo step, neither of which is
    built.
    """
    clusters = {i: [f] for i, f in enumerate(sorted(ids))}
    where = {f: i for i, c in clusters.items() for f in c}

    pair_sum = defaultdict(float)
    for (i, j), m in obs.items():
        a, b = where[i], where[j]
        if a == b:
            continue
        pair_sum[(a, b) if a < b else (b, a)] += 2.0 * m - 1.0

    merges = 0
    while len(clusters) > n_clusters and pair_sum:
        (a, b), _best = max(pair_sum.items(), key=lambda kv: (kv[1], -kv[0][0], -kv[0][1]))
        clusters[a].extend(clusters[b])
        for f in clusters[b]:
            where[f] = a
        del clusters[b]
        merged = defaultdict(float)
        for (x, y), v in pair_sum.items():
            if (x, y) == (a, b):
                continue
            nx = a if x == b else x
            ny = a if y == b else y
            if nx == ny:
                continue
            merged[(nx, ny) if nx < ny else (ny, nx)] += v
        pair_sum = merged
        merges += 1

    return [sorted(c) for c in clusters.values()], merges


def _complete_to_n(clusters, n_clusters):
    """Force exactly N when evidence has run out. Deterministic and LABELLED.

    Under known-N the attacker was HANDED the document count. Assigning two
    evidence-disconnected components to the same document because the global
    constraint requires N groups is not fabricating evidence -- it is an
    evidence-free decision using side information we deliberately gave it.
    Refusing to do it, and emitting more than N groups, would mean the known-N
    attacker failed to use what it was told.

    So it happens, deterministically (smallest components first, so the largest
    recovered structures stay intact), and the count is reported as
    evidence_free_merges. Arbitrary is fine; arbitrary and unlabelled is not.
    """
    work = sorted((sorted(c) for c in clusters), key=lambda c: (len(c), c[0]))
    forced = 0
    while len(work) > n_clusters:
        a = work.pop(0)
        b = work.pop(0)
        work.append(sorted(a + b))
        work.sort(key=lambda c: (len(c), c[0]))
        forced += 1
    return sorted(work, key=lambda c: c[0]), forced


def cluster_known_n(ids, edges, n_clusters, linkage="signed"):
    """Cluster to exactly n_clusters from observed membership evidence.

    ids        : every fragment that must be placed
    edges      : {(i, j): M_ij} for OBSERVED pairs only, symmetric in meaning
    n_clusters : the oracle document count N
    linkage    : "signed" aggregates signed evidence over observed edges;
                 "single" merges on the single best edge (brittle, kept for
                 comparison). THE CHOICE MUST BE FROZEN ON DEVELOPMENT DATA,
                 never picked per pool by whichever scores better against truth.

    Always returns exactly n_clusters when len(ids) >= n_clusters. Evidence
    cannot always reach N; when it cannot, the remainder is completed
    deterministically and counted in evidence_free_merges rather than hidden.
    """
    ids = list(ids)
    if n_clusters < 1:
        raise ValueError("n_clusters must be >= 1")
    if linkage not in ("signed", "single"):
        raise ValueError(f"unknown linkage {linkage!r}")
    if len(ids) <= n_clusters:
        return [[f] for f in sorted(ids)], {
            "reached_n": len(ids) == n_clusters, "components_before": len(ids),
            "needs_bridges": False, "merges": 0, "evidence_free_merges": 0,
            "singletons": len(ids), "linkage": linkage,
        }

    idset = set(ids)
    obs = {(i, j): float(w) for (i, j), w in edges.items()
           if i in idset and j in idset and i != j}
    comps = connected_components(ids, obs)

    if linkage == "signed":
        clusters, merges = _signed_merge(ids, obs, n_clusters)
    else:
        parent = {f: f for f in ids}
        size = {f: 1 for f in ids}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        n_live, merges = len(ids), 0
        for (i, j), _w in sorted(obs.items(), key=lambda kv: (-kv[1], kv[0])):
            if n_live <= n_clusters:
                break
            ri, rj = find(i), find(j)
            if ri == rj:
                continue
            if size[ri] < size[rj] or (size[ri] == size[rj] and ri > rj):
                ri, rj = rj, ri
            parent[rj] = ri
            size[ri] += size[rj]
            n_live -= 1
            merges += 1
        grouped = defaultdict(list)
        for f in ids:
            grouped[find(f)].append(f)
        clusters = [sorted(v) for v in grouped.values()]

    clusters, forced = _complete_to_n(clusters, n_clusters)

    return clusters, {
        "reached_n": len(clusters) == n_clusters,
        "components_before": len(comps),
        "needs_bridges": len(comps) > n_clusters,
        "merges": merges,
        "evidence_free_merges": forced,
        "singletons": sum(1 for c in clusters if len(c) == 1),
        "linkage": linkage,
    }
