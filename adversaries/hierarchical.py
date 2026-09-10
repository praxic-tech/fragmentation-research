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
import io
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

from masking import (assert_ids_masked, mask_fragment_ids,          # noqa: E402
                     preflight)
from repair import NoModelAnswer                                       # noqa: E402
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


# Mirrors joint_game.POLICY_CAP. Past this share of the REQUESTED pair evidence
# having no model answer, the partition rests too heavily on the clusterer's
# evidence-free completion to be scored as the attacker's work.
HOLE_CAP = 0.25


def pair_reservation(n_pairs, prompt, tpm_limit=None):
    """Output budget for one pair batch, sized from MEASUREMENT.

    A reasoning model spends most of its output thinking, not answering. On
    gpt-oss-120b, measured:

        3 pairs  -> 489 completion tokens   (163/pair)
        8 pairs  -> 894                     (112/pair)
       15 pairs  -> 1258                    ( 84/pair)

    which is roughly 250 tokens of fixed overhead plus ~70 per pair -- so per
    pair, BIGGER BATCHES ARE CHEAPER. An earlier version reserved 40/pair with
    no fixed term and every single batch came back empty: the model burned the
    whole budget reasoning and emitted nothing, which surfaced as "Model did not
    return valid JSON" and looked like a parser bug.

    400 + 100/pair is that fit with margin. Shrunk to fit tpm_limit when given,
    since providers count the reservation against tokens-per-minute.
    """
    want = 400 + 100 * n_pairs
    if not tpm_limit:
        return want
    room = tpm_limit - (len(prompt) // 4) - 200
    return max(256, min(want, room))


QUOTA_MARKER = "Too many transient failures"


def _call_with_cooldown(call, client, prompt, model, temperature, max_tokens,
                        cooldown, retries, where):
    """call_model, riding out provider rate limits instead of dying on them.

    call_model already backs off inside one call; when it gives up it raises
    QUOTA_MARKER. That is usually a per-minute burst, not an exhausted daily
    budget, so the batch waits and is asked again. Only after `retries`
    cool-downs does the error propagate -- and by then every earlier answer is
    already on disk, so the stop is resumable rather than a loss.
    """
    for k in range(retries + 1):
        try:
            return call(client, prompt, model, temperature=temperature,
                        max_tokens=max_tokens)
        except Exception as err:                            # noqa: BLE001
            if QUOTA_MARKER not in str(err) or k == retries:
                raise
            print(f"  [QUOTA] {where}: provider limit -- cooling down "
                  f"{cooldown:.0f}s ({k + 1}/{retries})")
            time.sleep(cooldown)


class PairCache:
    """Every answered pair, appended and flushed the moment it is derived.

    The free-tier rehearsal lost ~570 answered pairs -- 38 of 41 batches -- to
    a quota stop near the end, because answers were only written after the
    whole pool finished. On the paid run this attacker calls the model directly
    at full price, so that would have been real money thrown away.
    """

    def __init__(self, path=None):
        self.path = path
        self.rows = {}
        if path and os.path.exists(path):
            with io.open(path, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        r = json.loads(line)
                        self.rows[tuple(r["pair"])] = r

    def get(self, i, j):
        return self.rows.get((i, j))

    def add(self, row):
        self.rows[tuple(row["pair"])] = row
        if self.path:
            with io.open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
                fh.flush()


def check_run_meta(out_dir, meta):
    """Refuse to resume into a folder holding a DIFFERENT run's answers.

    Returns True for a fresh folder (meta written), False for a genuine resume.
    """
    path = os.path.join(out_dir, "run_meta.json")
    if os.path.exists(path):
        with io.open(path, encoding="utf-8") as fh:
            old = json.load(fh)
        diff = sorted(k for k in meta if old.get(k) != meta[k])
        if diff:
            raise ValueError(
                f"{out_dir} holds answers from a different run (differs in "
                f"{', '.join(diff)}). Use a fresh --out: mixing runs would "
                "score one pool with another pool's evidence.")
        return False
    os.makedirs(out_dir, exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    return True


def score_pairs_llm(client, pairs, text_by_id, model, seed=0,
                    pairs_per_call=DEFAULT_PAIRS_PER_CALL, temperature=None,
                    pause=0.0, on_call=None, tpm_limit=None, cache=None,
                    call=None, quota_cooldown=90.0, quota_retries=6):
    """Score pairs with a model, batched, every prompt through preflight.

    Returns (m_edges, w_edges, rows, telemetry). A batch that fails is recorded
    and skipped rather than aborting the pool — one bad response must not cost
    the other 88 calls.
    """
    from llm_adversary import call_model

    oriented = orient(pairs, seed)
    m_edges, w_edges, rows = {}, {}, []
    calls = failed = malformed = unanswered = truncated = 0

    # RESUME. A pair answered in an earlier run of this pool is taken from the
    # cache, not asked again. Its stored M and W already carry the orientation
    # it was asked under, so nothing is re-derived.
    resumed = 0
    if cache is not None:
        todo = []
        for (i, j, flip) in oriented:
            hit = cache.get(i, j)
            if hit is None:
                todo.append((i, j, flip))
                continue
            m_edges[(i, j)] = hit["M"]
            w_edges[(i, j)] = hit["W"]
            rows.append(hit)
            resumed += 1
        oriented = todo

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
        # Reasoning length is VARIABLE, so a fixed margin is not enough: at
        # 15 pairs the measured need was 1258 tokens, the reservation 1900, and
        # one batch in fourteen still truncated mid-JSON. A truncation is not a
        # model failure, it is a budget failure, so retry once with double the
        # room before giving the batch up.
        answer = None
        for attempt in (1, 2):
            budget = pair_reservation(len(chunk), prompt, tpm_limit) * attempt
            if tpm_limit:
                budget = min(budget, max(256, tpm_limit - len(prompt) // 4 - 200))
            try:
                answer = _call_with_cooldown(
                    call or call_model, client, prompt, model, temperature,
                    budget, quota_cooldown, quota_retries,
                    f"pair batch {start}")
                break
            except Exception as err:                            # noqa: BLE001
                last = str(err)
                # ONLY a truncation is worth retrying. call_model already
                # handles transient/429 conditions internally with backoff, so
                # if it raises one of those the quota is genuinely gone --
                # retrying at DOUBLE the budget then spends more of the quota
                # that just ran out and provokes further limiting. Measured:
                # a run that retried indiscriminately turned 1 failed batch in
                # 14 into 10 failed in 17, and F1_J fell 0.4214 -> 0.2738 for
                # reasons that had nothing to do with the defence.
                retryable = "did not return valid JSON" in last
                if attempt == 1 and retryable:
                    truncated += 1
                    if pause:
                        time.sleep(pause)
                    continue
                if "Too many transient failures" in last:
                    # The provider quota is gone. Every remaining batch would
                    # fail the same way, leaving the clusterer to fill the
                    # holes with evidence-free merges and the pool to be scored
                    # as if the attacker had tried. Stop instead of carrying on.
                    raise NoModelAnswer(
                        f"pair batch {start}: provider limit persisted through "
                        f"{quota_retries} cool-downs -- {last[:80]}")
                failed += 1
                reason = "after retry" if attempt > 1 else "not retryable"
                print(f"  [skip] pair batch {start} ({reason}): {last[:70]}")
                break
        if answer is None:
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
            row = {"pair": [i, j], "pair_id": pid, "flipped": flip,
                   "same": same, "before": before, **d}
            rows.append(row)
            if cache is not None:
                cache.add(row)          # durable before the next batch is asked

        unanswered += len(by_pair_id) - len(seen_ids)
        if on_call:
            on_call(calls)
        if pause:
            time.sleep(pause)

    return m_edges, w_edges, rows, {
        "pair_calls": calls, "failed_batches": failed,
        "malformed_pairs": malformed, "unanswered_pairs": unanswered,
        "retried_batches": truncated,
        "scored_pairs": len(rows), "requested_pairs": len(oriented) + resumed,
        "resumed_pairs": resumed,
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
    # "ALREADY MASKED" was a docstring promise; now it is checked. preflight
    # guards prompts, and every id here reaches a sort, a seeded hash and a
    # tie-break before any prompt is built.
    assert_ids_masked(frag_ids, where="hierarchical.attack")
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
                    pairs_per_call=DEFAULT_PAIRS_PER_CALL, pause=0.0,
                    tpm_limit=None, cache=None, quota_cooldown=90.0,
                    quota_retries=6):
    """attack() wired to a model, keeping every raw response re-scorable."""
    text_by_id = {f["fragment_id"]: f["text"] for f in fragments}
    captured = {"rows": [], "telemetry": []}

    def score_fn(pairs):
        m, w, rows, tel = score_pairs_llm(
            client, pairs, text_by_id, model, seed=seed,
            pairs_per_call=pairs_per_call, pause=pause, tpm_limit=tpm_limit,
            cache=cache, quota_cooldown=quota_cooldown,
            quota_retries=quota_retries)
        captured["rows"].extend(rows)
        captured["telemetry"].append(tel)
        return m, w, rows

    groups, telemetry = attack(fragments, n_records, score_fn, k=k, seed=seed)
    telemetry["llm"] = {
        "pair_calls": sum(t["pair_calls"] for t in captured["telemetry"]),
        "failed_batches": sum(t["failed_batches"] for t in captured["telemetry"]),
        "malformed_pairs": sum(t["malformed_pairs"] for t in captured["telemetry"]),
        "retried_batches": sum(t["retried_batches"] for t in captured["telemetry"]),
        "unanswered_pairs": sum(t["unanswered_pairs"] for t in captured["telemetry"]),
        "requested_pairs": sum(t["requested_pairs"] for t in captured["telemetry"]),
        "scored_pairs": sum(t["scored_pairs"] for t in captured["telemetry"]),
        "resumed_pairs": sum(t.get("resumed_pairs", 0)
                             for t in captured["telemetry"]),
        "model": model,
    }
    return groups, telemetry, captured["rows"]


# ── CLI: real-model smoke test ───────────────────────────────────────────────

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


def parse_args():
    ap = argparse.ArgumentParser(
        description="Smoke-test the hierarchical attacker against a real model.")
    ap.add_argument("--cell", default=os.path.join(ROOT, "results", "grid",
                                                   "pilot_reference"))
    ap.add_argument("--docs", type=int, default=3)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--provider", default="groq")
    ap.add_argument("--model", default=None)
    ap.add_argument("--pairs-per-call", type=int, default=15)
    ap.add_argument("--pause", type=float, default=3.0)
    ap.add_argument("--tpm-limit", type=int, default=8000,
                    help="provider tokens-per-minute ceiling; the output "
                         "reservation is shrunk to fit under it")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--quota-cooldown", type=float, default=90.0,
                    help="seconds to wait when the provider rate-limits")
    ap.add_argument("--quota-retries", type=int, default=6,
                    help="cool-downs per batch before stopping (resumable)")
    ap.add_argument("--out", default=os.path.join(ROOT, "results",
                                                  "hierarchical_smoke"))
    return ap.parse_args()


def main():
    a = parse_args()
    sys.path.insert(0, os.path.join(ROOT, "harness"))
    from joint_metrics import analytic_baseline, decompose, score_joint
    from llm_adversary import PROVIDERS, make_client

    model = a.model or PROVIDERS[a.provider][1]
    fragments, truth = _load_pool(a.cell, a.docs)
    members = list(truth)

    # MASK before anything reaches a prompt. preflight refuses raw ids, but the
    # masking has to happen here or every pair prompt would be blocked.
    masked, id_map = mask_fragment_ids(fragments, seed=a.seed)
    back = {m: o for m, o in id_map.items()}

    print(f"pool   : {len(members)} documents, {len(masked)} fragments")
    print(f"model  : {model} via {a.provider}   k={a.k}  "
          f"pairs/call={a.pairs_per_call}")

    # Every answered pair lands in <out>/pairs.jsonl as it arrives; run_meta
    # stops a resume from mixing two different runs' evidence.
    meta = {"cell": os.path.normpath(a.cell), "docs": a.docs, "seed": a.seed,
            "k": a.k, "model": model,
            "alias_sha": hashlib.sha256(json.dumps(id_map, sort_keys=True)
                                        .encode("utf-8")).hexdigest()[:16]}
    fresh = check_run_meta(a.out, meta)
    cache = PairCache(os.path.join(a.out, "pairs.jsonl"))
    if not fresh:
        print(f"resume : {len(cache.rows)} pairs already answered in {a.out}")

    client = make_client(a.provider)
    try:
        groups, tel, rows = attack_pool_llm(
            client, masked, len(members), model, k=a.k, seed=a.seed,
            pairs_per_call=a.pairs_per_call, pause=a.pause,
            tpm_limit=a.tpm_limit, cache=cache,
            quota_cooldown=a.quota_cooldown, quota_retries=a.quota_retries)
    except NoModelAnswer as err:
        print(f"REFUSED: {err}")
        print(f"{len(cache.rows)} answered pairs are saved in {a.out}. The pool "
              "is not scored with its evidence incomplete; re-run the same "
              "command to resume from where it stopped.")
        sys.exit(1)

    unmasked = [[back[m] for m in g if m in back] for g in groups]

    os.makedirs(a.out, exist_ok=True)
    with io.open(os.path.join(a.out, "rows.jsonl"), "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    with io.open(os.path.join(a.out, "result.json"), "w", encoding="utf-8") as fh:
        json.dump({"groups": unmasked, "telemetry": tel,
                   "alias_map": id_map, "model": model,
                   "at": datetime.now(timezone.utc).isoformat()}, fh, indent=2)

    c = tel["candidates"]
    llm = tel["llm"]
    print(f"\ncandidates : {c['candidate_pairs']} pairs from "
          f"{c['possible_pairs']} possible ({c['reduction_ratio']:.1%} skipped), "
          f"{c['fragments_tied_at_k']} fragments tied at k")
    print(f"scoring    : {llm['pair_calls']} calls, "
          f"{llm['retried_batches']} retried, "
          f"{llm['failed_batches']} failed, "
          f"{llm['malformed_pairs']} malformed, "
          f"{llm['unanswered_pairs']} unanswered")
    print(f"             {len(rows)} of {c['candidate_pairs']} candidate pairs "
          f"scored ({len(rows) / max(1, c['candidate_pairs']):.1%})")
    print(f"clustering : {tel['n_clusters']} clusters "
          f"(exactly N: {tel['exact_n']}), "
          f"{tel['clustering']['evidence_free_merges']} evidence-free merges, "
          f"{tel['bridge_rounds']} bridge rounds")
    print(f"ordering   : {tel['clusters_disconnected']} disconnected clusters, "
          f"{tel['arbitrary_pairs_total']} arbitrary pairs")

    # INTEGRITY. A pair batch with no model answer leaves its pairs unobserved
    # and the clusterer completes to N with evidence-free merges -- a partition
    # that is partly ours, scored as the attacker's. The smoke run that lost 10
    # of 17 batches to rate limiting and "scored" F1_J 0.2738 would stop here.
    hole = 1.0 - llm["scored_pairs"] / max(1, llm["requested_pairs"])
    print(f"integrity  : {llm['scored_pairs']} of {llm['requested_pairs']} "
          f"requested pairs answered ({hole:.1%} without a model answer)")
    if hole > HOLE_CAP:
        print(f"REFUSED: {hole:.0%} of the requested pair evidence has no model "
              f"answer (cap {HOLE_CAP:.0%}). F1 withheld.")
        sys.exit(1)

    res = score_joint(unmasked, truth, members)
    dec = decompose(unmasked, truth, members)
    base = analytic_baseline({r: truth[r] for r in members})
    q = dec["q"]
    print(f"\nF1_J       : {res['f1']:.4f}   baseline {base['joint']:.4f}")
    print(f"J-linkage  : {dec['f1_linkage']:.4f}")
    print(f"q (C/K)    : {('%.4f' % q) if q is not None else 'undefined (K=0)'}")
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
