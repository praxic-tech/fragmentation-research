
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


def bridge_candidates(components_list, k_per_pair=1):
    """Pairs to score next so that too-fragmented evidence can reach N groups.

    Returns cross-component pairs, nearest-first by component index so the
    smallest number of new queries connects the most. Deterministic: the caller
    spends real money on these, so the same graph must always ask the same
    questions.
    """
    out = []
    for a in range(len(components_list)):
        for b in range(a + 1, len(components_list)):
            ca, cb = components_list[a], components_list[b]
            for t in range(min(k_per_pair, len(ca), len(cb))):
                out.append((ca[t], cb[t]))
    return out


def cluster_known_n(ids, edges, n_clusters):
    """Merge by descending membership score, stop at exactly n_clusters.

    ids        : every fragment that must be placed
    edges      : {(i, j): M_ij} for OBSERVED pairs only, symmetric in meaning
    n_clusters : the oracle document count N

    Returns (clusters, info). `clusters` is a list of lists covering every id
    exactly once, and len(clusters) == n_clusters whenever that is achievable.

    info records what the result rests on:
        reached_n           did the merge actually land on N
        components_before   components of the observed graph before merging
        needs_bridges       True when the evidence graph is too fragmented to
                            reach N without new comparisons
        merges              merges performed
        forced_merges       merges that joined components with NO observed edge
                            between them -- zero for a graph-native result
        singletons          clusters of size 1 in the output

    When the graph has MORE than n_clusters components, N is not reachable
    without inventing links. Rather than fabricate them, this returns the
    components as-is with needs_bridges=True so the caller can spend budget on
    bridge comparisons and retry. Manufacturing merges from absent evidence is
    the failure this module exists to prevent.
    """
    ids = list(ids)
    if n_clusters < 1:
        raise ValueError("n_clusters must be >= 1")
    if len(ids) <= n_clusters:
        return [[f] for f in sorted(ids)], {
            "reached_n": len(ids) == n_clusters, "components_before": len(ids),
            "needs_bridges": False, "merges": 0, "forced_merges": 0,
            "singletons": len(ids),
        }

    idset = set(ids)
    obs = {(i, j): float(w) for (i, j), w in edges.items()
           if i in idset and j in idset and i != j}

    comps = connected_components(ids, obs)
    if len(comps) > n_clusters:
        # Too fragmented. Do NOT invent links to force N.
        return comps, {
            "reached_n": False, "components_before": len(comps),
            "needs_bridges": True, "merges": 0, "forced_merges": 0,
            "singletons": sum(1 for c in comps if len(c) == 1),
        }

    parent = {f: f for f in ids}
    size = {f: 1 for f in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    # Descending score; ties broken on the pair itself so the merge order is
    # reproducible rather than dependent on dict insertion order.
    ranked = sorted(obs.items(), key=lambda kv: (-kv[1], kv[0]))

    n_live = len(ids)
    merges = 0
    for (i, j), _w in ranked:
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

    groups = defaultdict(list)
    for f in ids:
        groups[find(f)].append(f)
    clusters = sorted((sorted(v) for v in groups.values()), key=lambda g: g[0])

    return clusters, {
        "reached_n": len(clusters) == n_clusters,
        "components_before": len(comps),
        "needs_bridges": False,
        "merges": merges,
        "forced_merges": 0,          # graph-native: never merges without an edge
        "singletons": sum(1 for c in clusters if len(c) == 1),
    }
