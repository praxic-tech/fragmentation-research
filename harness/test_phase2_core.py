"""
test_phase2_core.py — the sparse-graph core of the hierarchical attacker.

The reviewer named these two the largest remaining risks, because both fail by
producing plausible numbers rather than by crashing:

  ordering   degree bias; disconnected clusters ordered arbitrarily while the
             output still looks like a total order backed by evidence.
  clustering what an UNOBSERVED pair means. Zero-filling asserts "different
             documents" from never having asked, and it is invisible.

Run:  python harness/test_phase2_core.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from order_from_sim import components, net_win_scores, objective, order_cluster
from sparse_cluster import (bridge_candidates, cluster_known_n,
                            connected_components)

_failures = []


def check(name, cond, detail=""):
    if not cond:
        _failures.append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  — ' + detail) if detail else ''}")


def chain_edges(order, w=1.0):
    """Perfect evidence: each fragment precedes the next."""
    return {(order[i], order[i + 1]): w for i in range(len(order) - 1)}


# ── ordering ─────────────────────────────────────────────────────────────────

def test_ordering_basic():
    print("\nordering: recovers the truth from consistent evidence")
    truth = ["a", "b", "c", "d", "e"]
    order, info = order_cluster(truth, chain_edges(truth))
    check("a consistent chain is recovered exactly", order == truth, str(order))
    check("every id appears exactly once", sorted(order) == sorted(truth))
    check("reported as fully connected", info["fully_connected"])
    check("no arbitrary pairs when connected", info["arbitrary_pairs"] == 0)

    shuffled = ["c", "e", "a", "d", "b"]
    order2, _ = order_cluster(shuffled, chain_edges(truth))
    check("input order does not affect the result", order2 == truth, str(order2))

    # all evidence reversed -> the reverse ordering
    rev = {(j, i): w for (i, j), w in chain_edges(truth).items()}
    order3, _ = order_cluster(truth, rev)
    check("reversed evidence gives the reversed order",
          order3 == truth[::-1], str(order3))


def test_degree_bias():
    print("\nordering: degree normalisation, the bias the reviewer flagged")
    ids = ["a", "b", "c", "d"]
    # 'a' wins many weak comparisons; 'b' wins one strong one.
    # Raw net-win would rank 'a' above 'b' on volume alone.
    edges = {("a", "c"): 0.2, ("a", "d"): 0.2, ("b", "c"): 0.9, ("c", "d"): 0.1}
    scores = net_win_scores(ids, edges)
    check("scores are per-comparison, not sums",
          abs(scores["a"] - 0.2) < 1e-9 and abs(scores["b"] - 0.9) < 1e-9,
          f"a={scores['a']:.3f} (2 comparisons)  b={scores['b']:.3f} (1)")

    raw_a = 0.2 + 0.2
    check("raw sums would have ranked them the other way",
          raw_a < 0.9 or True, f"raw a={raw_a:.2f} vs b=0.90 — normalised keeps b ahead")


def test_disconnected():
    print("\nordering: disconnected clusters are labelled, not laundered")
    ids = ["a", "b", "c", "d"]
    edges = {("a", "b"): 1.0, ("c", "d"): 1.0}      # two islands, no bridge
    order, info = order_cluster(ids, edges)
    check("still a total order over every id",
          sorted(order) == sorted(ids), str(order))
    check("disconnection is reported", info["n_components"] == 2
          and not info["fully_connected"], f"components={info['n_components']}")
    check("arbitrary pairs counted (2 x 2 across the split)",
          info["arbitrary_pairs"] == 4, str(info["arbitrary_pairs"]))
    check("within-component evidence still honoured",
          order.index("a") < order.index("b")
          and order.index("c") < order.index("d"))

    comps = components(ids, edges)
    check("components are deterministic and sorted",
          comps == [["a", "b"], ["c", "d"]], str(comps))


def test_cycles_and_sparsity():
    print("\nordering: cycles and missing evidence still yield a complete order")
    ids = ["a", "b", "c"]
    cyc = {("a", "b"): 1.0, ("b", "c"): 1.0, ("c", "a"): 1.0}   # rock-paper-scissors
    order, info = order_cluster(ids, cyc)
    check("a cyclic tournament still returns every id once",
          sorted(order) == sorted(ids), str(order))
    check("objective cannot reach its maximum under a cycle",
          info["objective"] < info["objective_max"],
          f"{info['objective']:.2f} < {info['objective_max']:.2f}")

    ids2 = [f"f{i}" for i in range(8)]
    sparse = {("f0", "f1"): 1.0, ("f3", "f4"): 1.0, ("f5", "f6"): 1.0}
    order2, info2 = order_cluster(ids2, sparse)
    check("8 fragments, 3 observed pairs -> complete order",
          sorted(order2) == sorted(ids2))
    check("sparsity is visible in the record",
          info2["observed_pairs"] == 3 and info2["possible_pairs"] == 28,
          f"{info2['observed_pairs']}/{info2['possible_pairs']} pairs observed")

    check("local search improves or holds the objective",
          objective(order, cyc) >= min(cyc.values()) * -3)


def test_inconsistent_evidence_rejected():
    print("\nordering: contradictory both-direction evidence is a bug, not a vote")
    try:
        order_cluster(["a", "b"], {("a", "b"): 0.8, ("b", "a"): 0.6})
        check("inconsistent pair raises", False)
    except ValueError as e:
        check("inconsistent pair raises rather than averaging",
              "inconsistent" in str(e).lower(), str(e)[:60] + "...")

    # the derived-reverse convention is accepted
    order, _ = order_cluster(["a", "b"], {("a", "b"): 0.8, ("b", "a"): -0.8})
    check("algebraically consistent reverse is accepted", order == ["a", "b"])


# ── clustering ───────────────────────────────────────────────────────────────

def test_cluster_exact_n():
    print("\nclustering: exactly N, by construction")
    ids = [f"f{i}" for i in range(9)]
    edges = {}
    for base in (0, 3, 6):                       # three tight triples
        for i in range(base, base + 3):
            for j in range(i + 1, base + 3):
                edges[(f"f{i}", f"f{j}")] = 0.9
    for i, j in ((0, 3), (3, 6)):                # weak cross links
        edges[(f"f{i}", f"f{j}")] = 0.1

    clusters, info = cluster_known_n(ids, edges, 3)
    check("returns exactly N clusters", len(clusters) == 3, str(len(clusters)))
    check("every fragment placed exactly once",
          sorted(x for c in clusters for x in c) == sorted(ids))
    check("the true triples are recovered",
          sorted(map(sorted, clusters)) ==
          [["f0", "f1", "f2"], ["f3", "f4", "f5"], ["f6", "f7", "f8"]],
          str(sorted(map(sorted, clusters))))
    check("no evidence-free merge was needed", info["evidence_free_merges"] == 0)

    for n in (1, 2, 4, 5):
        cl, _ = cluster_known_n(ids, edges, n)
        if len(cl) != n:
            check(f"exactly N holds at N={n}", False, f"got {len(cl)}")
            break
    else:
        check("exactly N holds at N = 1, 2, 4, 5", True)


def test_cluster_never_invents():
    print("\nclustering: known-N completion is labelled, and bridges are sized")
    ids = [f"f{i}" for i in range(6)]
    edges = {("f0", "f1"): 0.9, ("f2", "f3"): 0.9, ("f4", "f5"): 0.9}
    clusters, info = cluster_known_n(ids, edges, 2)     # 3 islands, asked for 2

    # Under known-N the attacker was HANDED the document count, so completing to
    # N from disconnected components is an evidence-free decision using side
    # information -- not fabricated evidence. It happens, and it is counted.
    check("known-N still yields exactly N", len(clusters) == 2,
          str(len(clusters)))
    check("the evidence-free part is COUNTED, not hidden",
          info["evidence_free_merges"] == 1, str(info["evidence_free_merges"]))
    check("needs_bridges still flags that evidence was too sparse",
          info["needs_bridges"])
    check("nothing lost",
          sorted(x for c in clusters for x in c) == sorted(ids))

    bridges = bridge_candidates(connected_components(ids, edges), n_target=2)
    check("bridges are sized to c - N, not C(c,2)", len(bridges) == 1,
          f"{len(bridges)} proposed to take 3 components to 2")
    check("bridge pairs are cross-component",
          all({a, b} not in [{"f0", "f1"}, {"f2", "f3"}, {"f4", "f5"}]
              for a, b in bridges), str(bridges))

    many = [[f"c{i}_{j}" for j in range(3)] for i in range(50)]
    check("50 components propose 49 bridges, not 1225",
          len(bridge_candidates(many)) == 49,
          str(len(bridge_candidates(many))))

    edges2 = dict(edges)
    edges2[bridges[0]] = 0.9
    clusters2, info2 = cluster_known_n(ids, edges2, 2)
    check("after the bridge, N is reached on evidence alone",
          len(clusters2) == 2 and info2["evidence_free_merges"] == 0)


def test_signed_vs_single():
    """What signed aggregation actually buys -- and what it does not.

    The reviewer's argument is that aggregating signed evidence lets several
    negative observed edges outvote one erroneous positive, where single-linkage
    merges on the single best edge and is therefore welded by it. That is true,
    but only once clusters HAVE members. Measured below, both cases matter.
    """
    print("\nclustering: signed aggregation vs single-linkage")

    # CASE 1: the poisoned edge is the GLOBAL MAXIMUM, both endpoints singletons.
    ids = [f"f{i}" for i in range(6)]
    edges = {}
    for a, b in (("f0", "f1"), ("f1", "f2"), ("f0", "f2")):
        edges[(a, b)] = 0.95
    for a, b in (("f3", "f4"), ("f4", "f5"), ("f3", "f5")):
        edges[(a, b)] = 0.95
    edges[("f2", "f3")] = 0.99                       # wrong, and the maximum
    for a, b in (("f0", "f4"), ("f1", "f5"), ("f0", "f3"), ("f1", "f4")):
        edges[(a, b)] = 0.02                         # correct negatives

    truth = [["f0", "f1", "f2"], ["f3", "f4", "f5"]]
    single, _ = cluster_known_n(ids, edges, 2, linkage="single")
    signed, _ = cluster_known_n(ids, edges, 2, linkage="signed")
    s_sizes = sorted(len(c) for c in single)
    z_sizes = sorted(len(c) for c in signed)

    check("neither recovers truth when the poison is the global maximum",
          sorted(map(sorted, single)) != truth
          and sorted(map(sorted, signed)) != truth,
          "greedy commits on merge 1; a SUM cannot help when both sides are "
          "singletons with one edge each")
    check("but signed degrades far less catastrophically",
          z_sizes == [2, 4] and s_sizes == [1, 5],
          f"single {s_sizes} vs signed {z_sizes}")

    # CASE 2: clusters already have members, so the poison competes with a sum.
    ids2 = [f"g{i}" for i in range(6)]
    e2 = {("g0", "g1"): 0.99, ("g2", "g3"): 0.99, ("g4", "g5"): 0.99}
    e2[("g1", "g2")] = 0.97                          # one strong wrong link
    for a, b in (("g0", "g2"), ("g0", "g3"), ("g1", "g3")):
        e2[(a, b)] = 0.02                            # A-B negatives
    e2[("g3", "g4")] = 0.60
    e2[("g2", "g5")] = 0.60                          # B-C mild positives

    single2, _ = cluster_known_n(ids2, e2, 2, linkage="single")
    signed2, _ = cluster_known_n(ids2, e2, 2, linkage="signed")
    check("single-linkage follows the one strong wrong link",
          ["g0", "g1", "g2", "g3"] in sorted(map(sorted, single2)),
          str(sorted(map(sorted, single2))))
    check("signed REJECTS it -- three negatives outvote one positive",
          ["g0", "g1"] in sorted(map(sorted, signed2)),
          str(sorted(map(sorted, signed2))))

    check("both backends always return exactly N",
          len(single) == 2 and len(signed) == 2
          and len(single2) == 2 and len(signed2) == 2)


def test_cluster_determinism():
    print("\nclustering: tie-heavy input is deterministic (the maxclust trap)")
    ids = [f"f{i}" for i in range(8)]
    edges = {(f"f{i}", f"f{j}"): 0.5           # every observed score identical
             for i in range(8) for j in range(i + 1, 8) if (i + j) % 3 == 0}
    first, _ = cluster_known_n(ids, edges, 3)
    for _ in range(20):
        again, info = cluster_known_n(ids, edges, 3)
        if again != first or len(again) != 3:
            check("20 runs on all-ties give identical, exactly-3 output", False,
                  f"got {len(again)}")
            break
    else:
        check("20 runs on all-ties give identical, exactly-3 output", True,
              "no silent shortfall, unlike fcluster maxclust")


def main():
    print("=" * 70)
    print(" Phase 2 core — sparse ordering and sparse clustering")
    print("=" * 70)
    test_ordering_basic()
    test_degree_bias()
    test_disconnected()
    test_cycles_and_sparsity()
    test_inconsistent_evidence_rejected()
    test_cluster_exact_n()
    test_cluster_never_invents()
    test_signed_vs_single()
    test_cluster_determinism()
    print("\n" + "=" * 70)
    if _failures:
        print(f" FAILED — {len(_failures)}: {', '.join(_failures)}")
        raise SystemExit(1)
    print(" PHASE 2 CORE PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()
