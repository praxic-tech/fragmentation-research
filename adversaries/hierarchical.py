"""
hierarchical.py — the attacker that never puts a whole pool in one prompt.

One-shot J hands an entire pool to the model in a single call. As pools grow it
starts dropping fragments — 96% placed at N=3, 78% at N=7 — and that makes a
security result ambiguous: did fragmentation resist, or did the model run out of
room? A reviewer takes the second reading, and coverage reporting does not cure
it. This attacker removes the explanation entirely by asking only about PAIRS.

    1. candidate generation   cheap TF-IDF similarity, keep each fragment's
                              top-k neighbours. Also the blocker.
    2. pairwise scoring       for candidate pairs only, one small prompt asking
                              two things. Many pairs packed per call.
    3. clustering             exactly-N over the observed membership graph.
    4. ordering               rank aggregation over the observed precedence
                              graph, per cluster.
    5. output                 a partition with an order inside each group --
                              THE SAME SHAPE one-shot J emits, scored by the
                              same code with no attacker-specific branch.

ONE QUERY PER UNORDERED PAIR; THE ALGEBRA IS DERIVED
----------------------------------------------------
A probability cannot be antisymmetric, so the model is never asked for both
directions. It is asked once:

    m     = P(same document)                 symmetric      M_ij = M_ji = m
    p     = P(shown-first precedes shown-second | same document)
    W     = 2p - 1                           antisymmetric  W_ji = -W_ij

Asking twice would let it return P(A<B)=0.8 and P(B<A)=0.6, and nothing about
averaging those is principled. Deriving guarantees the algebra.

WHICH FRAGMENT IS SHOWN FIRST IS RANDOMISED
-------------------------------------------
From a stored seed, per pair. Models carry a positional bias -- a tendency to
say the first thing precedes the second -- and alias assignment is itself
ordered. Without randomisation those two could align, and a systematic bias
would masquerade as evidence. The orientation actually used is recorded with
every score, so `W` can be re-derived from the raw response later.

SEPARATE CHANNELS, NOT ONE MATRIX
---------------------------------
"Same document?" and "which comes first?" are different questions. An earlier
design kept one asymmetric matrix and recovered direction by subtraction, with
max(S, S.T) for clustering. That is only safe if S has one precise meaning, and
it does not. Cluster on M, order on W.
"""

import argparse
import hashlib
import json
import os
import random
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE_DIR)
for _p in (os.path.join(ROOT, "harness"), os.path.join(ROOT, "datagen"), BASE_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from masking import mask_fragment_ids, preflight                    # noqa: E402
from memon_linkage import build_tfidf                               # noqa: E402
from order_from_sim import order_cluster                            # noqa: E402
from sparse_cluster import (bridge_candidates, cluster_known_n,     # noqa: E402
                            connected_components)

DEFAULT_K = 10
DEFAULT_PAIRS_PER_CALL = 20
MAX_BRIDGE_ROUNDS = 3


# ── 1. candidate generation ──────────────────────────────────────────────────

def top_k_candidates(frag_ids, text_by_id, k=DEFAULT_K, tie_seed=42):
    """Each fragment's k most similar neighbours, as UNDIRECTED pairs.

    Union-kNN: an edge exists when EITHER endpoint selects the other. Reciprocal
    choices collapse to one pair, so the edge count is well below n*k — which is
    why the cost model must count deduplicated edges rather than n*k.

    Dense O(n^2) on purpose. Within a pool that is ~178 fragments, about 15k
    comparisons, trivial. Exact top-k from a pairwise similarity CLOSURE is
    O(n^2) regardless of how few results are kept, so pretending otherwise at
    this scale would buy nothing. Full-corpus blocking (16,524 fragments, ~136M
    pairs) is a different problem and needs an inverted index over TF-IDF terms;
    that is Phase 3, not this function.
    """
    sim = build_tfidf(frag_ids, text_by_id)
    n = len(frag_ids)
    comparisons = 0
    ties_at_k = 0
    pairs = set()

    # Ties broken by a SEEDED HASH, not by fragment id. Clinical prose produces
    # many equal (often zero) similarities, and breaking those lexicographically
    # would make candidate membership partly an artifact of alias assignment
    # order rather than of the text.
    def tiebreak(fid):
        return int(hashlib.sha256(f"{tie_seed}:{fid}".encode()).hexdigest()[:8], 16)

    for i, a in enumerate(frag_ids):
        scored = []
        for j, b in enumerate(frag_ids):
            if i == j:
                continue
            scored.append((sim(a, b), b))
            comparisons += 1
        scored.sort(key=lambda t: (-t[0], tiebreak(t[1])))
        if len(scored) > k and abs(scored[k - 1][0] - scored[k][0]) < 1e-12:
            ties_at_k += 1
        for _s, b in scored[:k]:
            pairs.add((a, b) if a <= b else (b, a))
    return sorted(pairs), {
        "n_fragments": n,
        "k": k,
        "comparisons": comparisons,
        "possible_pairs": n * (n - 1) // 2,
        "candidate_pairs": len(pairs),
        "reduction_ratio": (1 - len(pairs) / (n * (n - 1) / 2)) if n > 1 else 0.0,
        "fragments_tied_at_k": ties_at_k,
        "tied_at_k_fraction": ties_at_k / n if n else 0.0,
    }


# ── 2. pairwise scoring ──────────────────────────────────────────────────────

def pair_prompt(shown):
    """One prompt covering many pairs. `shown` is [(idx, a_text, b_text), ...].

    Deliberately asks for ONE precedence number, not two -- the reverse is
    derived. And it requires pair_id on every returned object: mapping answers
    back by ARRAY POSITION would silently attach valid-looking probabilities to
    the wrong fragments if the model reordered two objects while returning the
    right array length. Nothing downstream could detect that.
    """
    blocks = []
    for idx, a_text, b_text in shown:
        blocks.append(f"pair_id {idx}\n  A: {a_text}\n  B: {b_text}")
    return (
        "Each item below is a PAIR of text fragments taken from a collection "
        "of documents that were split up and mixed together." "\n\n"
        "For each pair, judge two things independently:" "\n"
        "  same   - the probability the two fragments came from the SAME "
        "document, from 0.0 to 1.0" "\n"
        "  before - ASSUMING they are from the same document, the probability "
        "that A appeared BEFORE B in it, from 0.0 to 1.0" "\n\n"
        + "\n\n".join(blocks) +
        f"\n\nReturn ONLY a JSON array of {len(shown)} objects, each "
        '{"pair_id": <the number shown above>, "same": <number>, '
        '"before": <number>}. Include pair_id on every object so the answers '
        'can be matched up. No explanation, no markdown.'
    )

def orient(pairs, seed):
    """Decide, per pair, which fragment is shown as A. Deterministic from seed.

    Returns [(i, j, flipped)] where flipped=True means j was shown first, so a
    returned `before` probability refers to j preceding i and must be inverted
    when deriving W_ij.
    """
    rng = random.Random(seed)
    return [(i, j, rng.random() < 0.5) for (i, j) in pairs]


def derive(i, j, flipped, same, before):
    """Turn one raw answer into symmetric M and antisymmetric W for (i, j).

    `before` is P(shown-first precedes shown-second). When the pair was flipped
    that is P(j precedes i), so P(i precedes j) = 1 - before.
    """
    p_ij = (1.0 - before) if flipped else before
    return {"M": float(same), "W": 2.0 * float(p_ij) - 1.0, "p_ij": p_ij}


def score_pairs_offline(pairs, oracle, seed=0):
    """Score pairs with a supplied function instead of a model.

    oracle(i, j) -> (same, p_i_before_j). Used by the tests and by any
    non-LLM attacker that wants this pipeline; keeps the pipeline testable
    without spending money or requiring a network.
    """
    m_edges, w_edges, rows = {}, {}, []
    for i, j, flipped in orient(pairs, seed):
        same, p = oracle(i, j)
        shown_before = (1.0 - p) if flipped else p
        d = derive(i, j, flipped, same, shown_before)
        m_edges[(i, j)] = d["M"]
        w_edges[(i, j)] = d["W"]
        rows.append({"pair": [i, j], "flipped": flipped,
                     "same": same, "before": shown_before, **d})
    return m_edges, w_edges, rows


def score_pairs_llm(client, pairs, text_by_id, model, seed=0,
                    pairs_per_call=DEFAULT_PAIRS_PER_CALL, temperature=None,
                    pause=0.0, on_call=None):
    """Score pairs with a model, batched, every prompt through preflight.

    Returns (m_edges, w_edges, rows, telemetry). A batch that fails is recorded
    and skipped rather than aborting the pool — one bad response must not cost
    the other 88 calls.
    """
    from llm_adversary import call_model

    oriented = orient(pairs, seed)
    m_edges, w_edges, rows = {}, {}, []
    calls = failed = malformed = unanswered = 0

    for start in range(0, len(oriented), pairs_per_call):
        chunk = oriented[start:start + pairs_per_call]
        by_pair_id = {n + 1: (i, j, flip) for n, (i, j, flip) in enumerate(chunk)}
        shown = [(n + 1,
                  text_by_id[j if flip else i],
                  text_by_id[i if flip else j])
                 for n, (i, j, flip) in enumerate(chunk)]
        prompt = pair_prompt(shown)
        preflight(prompt, where=f"hierarchical pair batch {start}")
        calls += 1
        try:
            answer = call_model(client, prompt, model, temperature=temperature,
                                max_tokens=max(256, len(chunk) * 40 + 200))
        except Exception as err:                                # noqa: BLE001
            failed += 1
            print(f"  [skip] pair batch {start}: {str(err)[:90]}")
            if pause:
                time.sleep(pause)
            continue

        # MAP BY pair_id, NEVER BY POSITION. A model that reorders two objects
        # while returning the right array length would otherwise attach
        # valid-looking probabilities to the wrong fragments -- silent, and
        # expensive because nothing downstream can detect it.
        seen_ids = set()
        for item in (answer if isinstance(answer, list) else []):
            try:
                pid = int(item["pair_id"])
                same = float(item["same"])
                before = float(item["before"])
            except (KeyError, TypeError, ValueError):
                malformed += 1
                continue
            if pid not in by_pair_id or pid in seen_ids:
                malformed += 1          # unknown or duplicated pair_id
                continue
            if not (0.0 <= same <= 1.0 and 0.0 <= before <= 1.0):
                malformed += 1          # out of range
                continue
            seen_ids.add(pid)
            i, j, flip = by_pair_id[pid]
            d = derive(i, j, flip, same, before)
            m_edges[(i, j)] = d["M"]
            w_edges[(i, j)] = d["W"]
            rows.append({"pair": [i, j], "pair_id": pid, "flipped": flip,
                         "same": same, "before": before, **d})

        unanswered += len(by_pair_id) - len(seen_ids)
        if on_call:
            on_call(calls)
        if pause:
            time.sleep(pause)

    return m_edges, w_edges, rows, {
        "pair_calls": calls, "failed_batches": failed,
        "malformed_pairs": malformed, "unanswered_pairs": unanswered,
        "scored_pairs": len(rows), "requested_pairs": len(oriented),
    }


# ── 3-5. the pipeline ────────────────────────────────────────────────────────

def attack(fragments, n_records, score_fn, k=DEFAULT_K, seed=42,
           max_bridge_rounds=MAX_BRIDGE_ROUNDS):
    """Full hierarchical attack over one pool.

    fragments  : [{"fragment_id": ..., "text": ...}] — ALREADY MASKED
    n_records  : oracle document count (known-N, the primary condition)
    score_fn   : pairs -> (m_edges, w_edges, rows). Injected so the LLM scorer,
                 a statistical scorer, or a test oracle all drive the same
                 pipeline.

    Returns (groups, telemetry). `groups` is a list of ordered lists covering
    every fragment exactly once — the same shape one-shot J emits.
    """
    frag_ids = [f["fragment_id"] for f in fragments]
    text_by_id = {f["fragment_id"]: f["text"] for f in fragments}

    pairs, cand_info = top_k_candidates(frag_ids, text_by_id, k=k)
    m_edges, w_edges, rows = score_fn(pairs)

    # Clustering may report that the observed graph is too fragmented to reach
    # N. Rather than invent links, ask for bridge comparisons and retry.
    bridge_rounds = 0
    bridge_pairs_scored = 0
    clusters, cinfo = cluster_known_n(frag_ids, m_edges, n_records)
    while cinfo["needs_bridges"] and bridge_rounds < max_bridge_rounds:
        comps = connected_components(frag_ids, m_edges)
        sim = build_tfidf(frag_ids, text_by_id)
        new_pairs = [p for p in bridge_candidates(comps, sim=sim,
                                                  n_target=n_records)
                     if p not in m_edges]
        if not new_pairs:
            break
        bm, bw, brows = score_fn(new_pairs)
        m_edges.update(bm)
        w_edges.update(bw)
        rows.extend(brows)
        bridge_pairs_scored += len(brows)
        bridge_rounds += 1
        clusters, cinfo = cluster_known_n(frag_ids, m_edges, n_records)

    groups, order_info = [], []
    for cl in clusters:
        inner = {kk: v for kk, v in w_edges.items()
                 if kk[0] in set(cl) and kk[1] in set(cl)}
        ordered, oinfo = order_cluster(cl, inner)
        groups.append(ordered)
        order_info.append(oinfo)

    placed = [x for g in groups for x in g]
    telemetry = {
        "candidates": cand_info,
        "clustering": cinfo,
        "bridge_rounds": bridge_rounds,
        "bridge_pairs_scored": bridge_pairs_scored,
        "n_clusters": len(groups),
        "n_records_asked": n_records,
        "exact_n": len(groups) == n_records,
        "coverage": len(set(placed)) / len(frag_ids) if frag_ids else 0.0,
        "clusters_disconnected": sum(1 for o in order_info
                                     if not o["fully_connected"]),
        "arbitrary_pairs_total": sum(o["arbitrary_pairs"] for o in order_info),
        "observed_pairs_total": sum(o["observed_pairs"] for o in order_info),
        "order_info": order_info,
        "scored_edges": len(m_edges),
    }
    return groups, telemetry


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def attack_pool_llm(client, fragments, n_records, model, k=DEFAULT_K, seed=42,
                    pairs_per_call=DEFAULT_PAIRS_PER_CALL, pause=0.0):
    """attack() wired to a model, keeping every raw response re-scorable."""
    text_by_id = {f["fragment_id"]: f["text"] for f in fragments}
    captured = {"rows": [], "telemetry": []}

    def score_fn(pairs):
        m, w, rows, tel = score_pairs_llm(
            client, pairs, text_by_id, model, seed=seed,
            pairs_per_call=pairs_per_call, pause=pause)
        captured["rows"].extend(rows)
        captured["telemetry"].append(tel)
        return m, w, rows

    groups, telemetry = attack(fragments, n_records, score_fn, k=k, seed=seed)
    telemetry["llm"] = {
        "pair_calls": sum(t["pair_calls"] for t in captured["telemetry"]),
        "failed_batches": sum(t["failed_batches"] for t in captured["telemetry"]),
        "malformed_pairs": sum(t["malformed_pairs"] for t in captured["telemetry"]),
        "model": model,
    }
    return groups, telemetry, captured["rows"]
