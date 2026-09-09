"""
memon_joint.py — the Memon n-gram baseline, adapted to game J.

The published Memon method answers two SEPARATE questions with two DIFFERENT
statistics, and neither one alone can answer J:

    grouping   B_stat, TF-IDF cosine (memon_linkage.build_tfidf). SYMMETRIC.
               sim(a,b) == sim(b,a), so it cannot say which fragment comes
               first. A path built from it has arbitrary orientation.
    ordering   memon.score_pair, char n-gram boundary log-likelihood.
               DIRECTIONAL. log P(B follows A) != log P(A follows B).

So: GROUP WITH B_stat, ORDER WITH score_pair. Emitting one ordered partition
puts Memon on the same scoring surface as one-shot J and the hierarchical
attacker, with no attacker-specific branch in the scorer.

WHY THIS ATTACKER EXISTS
------------------------
It costs nothing. Every number here is local computation, so it runs on every
grid cell for free, which makes attacker-dependence a claim measurable across
the whole grid rather than on the two cells an LLM budget reaches. A defence
that only resists the expensive attacker is a weaker result than one that
resists both.

TWO DEPARTURES FROM THE LEGACY CODE, BOTH DELIBERATE
----------------------------------------------------
1. `memon_order_guess` is brute force over n! permutations. At 25 fragments per
   document that is 1.5e25 orderings. Ordering routes through
   `order_from_sim.order_cluster` instead: same objective, feasible search.

2. `memon_grouping(variant="fixed")` ends in `fcluster(criterion="maxclust")`,
   which returns AT MOST n_groups, not exactly n_groups. The known-N attacker
   was handed the document count and must use it. This module cuts the same
   average-linkage tree with `cut_tree(Z, n_clusters=[N])`, which is exact, and
   reports what maxclust would have returned as a diagnostic so the difference
   is measured rather than assumed.

`memon_linkage.py` and `memon.py` are NOT edited; their published numbers stay
reproducible.

TURNING A LOG-LIKELIHOOD DIFFERENCE INTO A PREFERENCE WEIGHT
------------------------------------------------------------
`order_cluster` wants an antisymmetric w_ij in a bounded range. score_pair
returns unbounded log-probabilities whose scale depends on n, d and the
character vocabulary, so raw differences cannot be compared across cells.

    W_ij = 2 * sigmoid(s_ij - s_ji) - 1 = tanh((s_ij - s_ji) / 2)

s_ij - s_ji is already a log-odds ratio between the two orientations of the
same pair, so the logistic is the reading of the statistic rather than a
rescaling chosen to make the numbers behave. It has NO free parameter --
nothing here is tuned against truth -- and antisymmetry holds exactly, because
sigmoid(-x) = 1 - sigmoid(x). Bounded rather than raw for the same reason the
clusterer uses 2M-1: one pathological pair cannot dominate the objective.

Run:  python adversaries/memon_joint.py --cell results/grid/pilot_reference
      python adversaries/memon_joint.py --cell <pilot cell> --sweep-n
"""

import argparse
import io
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np
from scipy.cluster.hierarchy import cut_tree, fcluster
from scipy.cluster.hierarchy import linkage as hier_linkage
from scipy.spatial.distance import squareform

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "harness"))
sys.path.insert(0, os.path.join(ROOT, "adversaries"))

from masking import assert_ids_masked, mask_fragment_ids        # noqa: E402
from memon import build_model, build_vocab, score_pair          # noqa: E402
from memon_linkage import build_tfidf                            # noqa: E402
from order_from_sim import order_cluster                         # noqa: E402

__all__ = ["group_known_n", "direction_edges", "attack"]

DEFAULT_N = 2
DEFAULT_D = 2


# ── grouping: B_stat, cut to exactly N ───────────────────────────────────────

def group_known_n(frag_ids, text_by_id, n_groups, seed=42):
    """Average-linkage over TF-IDF cosine distance, cut to EXACTLY n_groups.

    The jitter reproduces memon_linkage's tie-breaking: the identifier
    similarity matrix is 83.5% exact zeros and scipy's linkage is sensitive to
    tie order. Same magnitude, same seed convention, so grouping here matches
    the legacy grouping wherever cut_tree and maxclust agree.
    """
    ids = list(frag_ids)
    m = len(ids)
    if m == 0:
        return [], {"n_groups": 0, "exact_n": n_groups == 0,
                    "maxclust_n_groups": 0, "cut_tree_disagreed": False,
                    "largest": 0, "singletons": 0}
    if m <= n_groups:
        return [[f] for f in sorted(ids)], {
            "n_groups": m, "exact_n": m == n_groups,
            "maxclust_n_groups": m, "cut_tree_disagreed": False,
            "largest": 1, "singletons": m,
        }

    sim = build_tfidf(ids, text_by_id)
    rng = np.random.default_rng(seed)
    D = np.empty((m, m), dtype=np.float64)
    for i in range(m):
        D[i, i] = 0.0
        for j in range(i + 1, m):
            D[i, j] = D[j, i] = 1.0 - sim(ids[i], ids[j])
    D += rng.random((m, m)) * 1e-6
    D = (D + D.T) / 2.0
    np.fill_diagonal(D, 0.0)

    Z = hier_linkage(squareform(D, checks=False), method="average")
    labels = [int(x) for x in cut_tree(Z, n_clusters=[n_groups])[:, 0]]

    # Diagnostic only: what the legacy call would have returned on this tree.
    maxclust_n = len({int(x) for x in fcluster(Z, t=n_groups,
                                               criterion="maxclust")})

    grouped = defaultdict(list)
    for idx, lab in enumerate(labels):
        grouped[lab].append(ids[idx])
    clusters = sorted((sorted(v) for v in grouped.values()), key=lambda c: c[0])
    sizes = sorted((len(c) for c in clusters), reverse=True)

    return clusters, {
        "n_groups": len(clusters),
        "exact_n": len(clusters) == n_groups,
        "maxclust_n_groups": maxclust_n,
        "cut_tree_disagreed": maxclust_n != n_groups,
        "largest": sizes[0] if sizes else 0,
        "singletons": sum(1 for c in clusters if len(c) == 1),
    }


# ── ordering: directional n-gram evidence ────────────────────────────────────

def _weight(s_ab, s_ba):
    """Antisymmetric preference in (-1, 1) from two boundary log-likelihoods.

    score_pair returns -inf when a text is shorter than the n-gram order or the
    successor is empty. Two -infs mean the statistic could not be evaluated in
    either direction, which is absence of evidence rather than evidence of a
    tie: the pair still enters the graph so the fragments stay connected, at
    weight 0. The exponent is clamped because a 40-nat difference is already
    saturated and exp() overflows well before the weight would change.
    """
    a_ok = math.isfinite(s_ab)
    b_ok = math.isfinite(s_ba)
    if not a_ok and not b_ok:
        return 0.0
    if not a_ok:
        return -1.0
    if not b_ok:
        return 1.0
    x = s_ab - s_ba
    if x > 40.0:
        return 1.0
    if x < -40.0:
        return -1.0
    return 2.0 / (1.0 + math.exp(-x)) - 1.0


def context_coverage(clusters, text_by_id, model, n, d):
    """Fraction of boundary steps whose context was actually seen in the model.

    The diagnostic that keeps a high-n result honest. `p_char` falls back to a
    Laplace prior over the whole vocabulary whenever the context is unseen, and
    at high n almost every context is unique to one fragment. If coverage
    collapses, the statistic is scoring the smoothing prior rather than the
    corpus, and any ordering it produces is close to arbitrary -- which would
    show up as W near zero, but is worth measuring directly rather than
    inferring from the outcome.
    """
    seen = total = 0
    for c in clusters:
        ids = sorted(c)
        for i in range(len(ids)):
            for j in range(len(ids)):
                if i == j:
                    continue
                ta, tb = text_by_id[ids[i]], text_by_id[ids[j]]
                if len(ta) < n or not tb:
                    continue
                for step in range(min(d, len(tb))):
                    ctx = (ta + tb[:step])[-n:]
                    if len(ctx) < n:
                        continue
                    total += 1
                    if model.get(ctx):
                        seen += 1
    return (seen / total) if total else 0.0


def direction_edges(cluster_ids, text_by_id, model, vocab, n, d):
    """Dense within-cluster directional evidence, one entry per unordered pair.

    Dense is affordable here precisely because there is no model to pay: a
    25-fragment document is 300 pairs and 600 score_pair calls, all local. The
    hierarchical attacker is sparse because each pair costs a token budget;
    this one is not, and pretending otherwise would understate the baseline.
    """
    ids = sorted(cluster_ids)
    edges = {}
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            s_ab = score_pair(text_by_id[a], text_by_id[b], model, vocab, n, d)
            s_ba = score_pair(text_by_id[b], text_by_id[a], model, vocab, n, d)
            edges[(a, b)] = _weight(s_ab, s_ba)
    return edges


# ── the attack ───────────────────────────────────────────────────────────────

def attack(fragments, n_docs, n=DEFAULT_N, d=DEFAULT_D, seed=42,
           mask_seed=None):
    """Group with B_stat, order with score_pair. Returns (groups, telemetry).

    `groups` is a list of ordered fragment-id lists in the CALLER'S id space --
    the same output shape as one-shot J and the hierarchical attacker, scored
    by the same joint_metrics code with no attacker-specific branch.

    MASKING HAPPENS HERE, NOT IN THE CALLER. An offline attacker builds no
    prompt, so preflight() never sees it and raw `prose_0002_frag_000` ids flow
    straight into every sort and tie-break. Measured cost of getting this wrong
    on this exact attacker: q = 1.0000 at n = 8, from 6,543 zero-weight pairs
    and 0.0% context coverage -- a perfect ordering score with no evidence
    behind a single pair, because order_cluster's evidence-free tie rule sorted
    by an id that spells out the position.

    mask_seed defaults to `seed` so a run is reproducible; pass it explicitly to
    vary the alias assignment independently of the clustering jitter.
    """
    masked, id_map = mask_fragment_ids(fragments,
                                       seed=seed if mask_seed is None
                                       else mask_seed)
    back = dict(id_map)
    fragments = masked

    ids = [f["fragment_id"] for f in fragments]
    assert_ids_masked(ids, where="memon_joint.attack")
    text_by_id = {f["fragment_id"]: f["text"] for f in fragments}

    clusters, gtel = group_known_n(ids, text_by_id, n_docs, seed=seed)

    model = build_model(fragments, n)
    vocab = build_vocab(fragments)

    ordered, infos, pair_calls, zero_weight = [], [], 0, 0
    for c in clusters:
        if len(c) <= 1:
            ordered.append(list(c))
            continue
        edges = direction_edges(c, text_by_id, model, vocab, n, d)
        pair_calls += 2 * len(edges)
        zero_weight += sum(1 for w in edges.values() if w == 0.0)
        order, info = order_cluster(c, edges)
        ordered.append(order)
        infos.append(info)

    placed = [x for g in ordered for x in g]
    assert sorted(placed) == sorted(ids), "memon_joint dropped or duplicated ids"

    ordered = [[back[x] for x in g] for g in ordered]

    return ordered, {
        "attacker": "memon-joint",
        "n": n, "d": d, "seed": seed,
        "mask_seed": seed if mask_seed is None else mask_seed,
        "n_fragments": len(ids),
        "n_docs_given": n_docs,
        "grouping": gtel,
        "score_pair_calls": pair_calls,
        "context_coverage": context_coverage(clusters, text_by_id, model,
                                             n, d),
        "zero_weight_pairs": zero_weight,
        "clusters_ordered": len(infos),
        "all_orderings_connected": all(i["fully_connected"] for i in infos),
        "arbitrary_pairs": sum(i["arbitrary_pairs"] for i in infos),
        "mean_objective_frac": (
            sum((i["objective"] / i["objective_max"]) if i["objective_max"]
                else 0.0 for i in infos) / len(infos)) if infos else 0.0,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def _load_pool(cell_dir, n_docs):
    frags = [json.loads(l) for l in
             io.open(os.path.join(cell_dir, "prose_fragments.jsonl"),
                     encoding="utf-8") if l.strip()]
    key = {json.loads(l)["record_id"]: json.loads(l)["order"] for l in
           io.open(os.path.join(cell_dir, "prose_answer_key.jsonl"),
                   encoding="utf-8") if l.strip()}
    by_rec = defaultdict(list)
    for f in frags:
        by_rec[f["record_id"]].append(f)
    rids = sorted(by_rec)[:n_docs]
    return [f for r in rids for f in by_rec[r]], {r: key[r] for r in rids}


def _run_one(frags, truth, n, d, seed):
    from joint_metrics import (advantage, analytic_baseline, decompose,
                               score_joint)
    members = list(truth)
    groups, tel = attack(frags, len(members), n=n, d=d, seed=seed)
    res = score_joint(groups, truth, members)
    base = analytic_baseline({r: truth[r] for r in members})
    dec = decompose(groups, truth, members)
    return {
        "f1_joint": res["f1"],
        "baseline_joint": base["joint"],
        "advantage": advantage(res["f1"], base["joint"]),
        "f1_linkage": dec.get("f1_linkage"),
        "q": dec.get("q"),
        "K": dec.get("K"),
        "C": dec.get("C"),
        "telemetry": tel,
    }


def _fmt(x, spec=".4f"):
    return "   undef" if x is None else format(x, spec)


def main():
    ap = argparse.ArgumentParser(
        description="Memon n-gram baseline on game J: B_stat grouping, "
                    "score_pair ordering.")
    ap.add_argument("--cell", default=os.path.join(ROOT, "results", "grid",
                                                   "pilot_reference"))
    ap.add_argument("--docs", type=int, default=7)
    ap.add_argument("--n", type=int, default=DEFAULT_N)
    ap.add_argument("--d", type=int, default=None,
                    help="boundary depth; defaults to n (the paper's d <= n)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--sweep-n", action="store_true",
                    help="n = 2..6 on DEVELOPMENT data only. The value used in "
                         "the confirmatory grid must be frozen before the grid "
                         "runs, never picked per cell against truth.")
    ap.add_argument("--max-n", type=int, default=8,
                    help="upper end of --sweep-n")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    frags, truth = _load_pool(a.cell, a.docs)
    print(f"cell {os.path.basename(a.cell)}   {len(frags)} fragments   "
          f"{len(truth)} documents")

    if a.sweep_n:
        print("\nn sweep -- DEVELOPMENT ONLY, freeze before the grid runs")
        print(f"  {'n':>3} {'d':>3} {'F1_J':>8} {'base':>8} {'A_J':>8} "
              f"{'F1_L':>8} {'q':>8} {'K':>7} {'ctx':>7}")
        rows = []
        for n in range(2, a.max_n + 1):
            r = _run_one(frags, truth, n, n, a.seed)
            rows.append({"n": n, "context_coverage":
                         r["telemetry"]["context_coverage"],
                         **{k: v for k, v in r.items() if k != "telemetry"}})
            print(f"  {n:>3} {n:>3} {r['f1_joint']:>8.4f} "
                  f"{r['baseline_joint']:>8.4f} {r['advantage']:>8.4f} "
                  f"{_fmt(r['f1_linkage']):>8} {_fmt(r['q']):>8} "
                  f"{r['K']:>7} "
                  f"{r['telemetry']['context_coverage']:>6.1%}")
        payload = {"cell": a.cell, "docs": a.docs, "sweep": rows}
    else:
        d = a.n if a.d is None else a.d
        r = _run_one(frags, truth, a.n, d, a.seed)
        t = r["telemetry"]
        print(f"\n  F1_J           {r['f1_joint']:.4f}")
        print(f"  baseline_J     {r['baseline_joint']:.4f}")
        print(f"  A_J            {r['advantage']:.4f}")
        print(f"  F1_linkage     {_fmt(r['f1_linkage'])}")
        print(f"  q = C/K        {_fmt(r['q'])}   (K={r['K']}, C={r['C']})")
        print(f"  groups         {t['grouping']['n_groups']} "
              f"(exact_n={t['grouping']['exact_n']}, "
              f"maxclust would give {t['grouping']['maxclust_n_groups']})")
        print(f"  score_pair     {t['score_pair_calls']} calls, $0.00")
        print(f"  context seen   {t['context_coverage']:.1%} of boundary steps "
              f"(the rest score the smoothing prior)")
        print(f"  orderings      connected={t['all_orderings_connected']}, "
              f"arbitrary_pairs={t['arbitrary_pairs']}, "
              f"objective {t['mean_objective_frac']:.1%} of max")
        payload = {"cell": a.cell, "docs": a.docs, **r}

    if a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        with io.open(a.out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
        print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
