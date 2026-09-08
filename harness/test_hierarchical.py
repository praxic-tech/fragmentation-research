"""
test_hierarchical.py — the hierarchical attacker end to end, offline.

Driven by a synthetic oracle instead of a model, so the pipeline is verified
without a network or a cent. The oracle's accuracy is a dial: at 1.0 the
attacker should reconstruct nearly everything, at 0.5 it should collapse toward
the analytic baseline. An attacker that scores well on a coin-flip oracle is
reading something other than its evidence, which is the failure this catches.

Run:  python harness/test_hierarchical.py
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "adversaries"))

from hierarchical import (attack, derive, orient, score_pairs_offline,
                          top_k_candidates)
from joint_metrics import analytic_baseline, decompose, score_joint

_failures = []


def check(name, cond, detail=""):
    if not cond:
        _failures.append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  — ' + detail) if detail else ''}")


# ── a synthetic corpus with real lexical structure ───────────────────────────

TOPICS = {
    "cardiac": "chest pain angina troponin ecg stent coronary artery infarct",
    "renal": "creatinine dialysis nephritis kidney urea glomerular renal biopsy",
    "neuro": "seizure cortex mri lesion aphasia neurology stroke thrombolysis",
    "hepatic": "jaundice bilirubin cirrhosis hepatic ascites portal liver enzyme",
    "pulmo": "dyspnoea spirometry pneumonia alveolar oxygen pleural lung effusion",
}


def make_pool(n_docs, frags_per_doc, seed=1):
    """Documents whose fragments share topic vocabulary, so TF-IDF can block."""
    rng = random.Random(seed)
    topics = list(TOPICS)[:n_docs]
    frags, truth = [], {}
    for d, topic in enumerate(topics):
        words = TOPICS[topic].split()
        rid = f"doc{d}"
        order = []
        for p in range(frags_per_doc):
            body = " ".join(rng.sample(words, 5))
            fid = f"m_{d}{p:02d}"
            frags.append({"fragment_id": fid,
                          "text": f"{body} step {p} of the {topic} course"})
            order.append(fid)
        truth[rid] = order
    return frags, truth


def oracle_factory(truth, accuracy, seed=3):
    """(same, p_before) with a controllable error rate.

    accuracy=1.0 -> perfect evidence. 0.5 -> pure noise.
    """
    owner = {f: r for r, order in truth.items() for f in order}
    pos = {f: k for order in truth.values() for k, f in enumerate(order)}
    rng = random.Random(seed)

    def oracle(i, j):
        same_truth = owner[i] == owner[j]
        before_truth = pos[i] < pos[j]
        same = (1.0 if same_truth else 0.0) if rng.random() < accuracy \
            else (0.0 if same_truth else 1.0)
        before = (1.0 if before_truth else 0.0) if rng.random() < accuracy \
            else (0.0 if before_truth else 1.0)
        return same, before
    return oracle


# ── derivation ───────────────────────────────────────────────────────────────

def test_derivation():
    print("\nderivation: one query per pair, both directions derived")
    d = derive("a", "b", flipped=False, same=0.9, before=0.8)
    check("unflipped: W = 2p - 1", abs(d["W"] - 0.6) < 1e-9, f"W={d['W']:.2f}")
    d = derive("a", "b", flipped=True, same=0.9, before=0.8)
    check("flipped: the answer refers to b preceding a, so W inverts",
          abs(d["W"] - (-0.6)) < 1e-9, f"W={d['W']:.2f}")
    d = derive("a", "b", flipped=False, same=0.5, before=0.5)
    check("total uncertainty gives W = 0", abs(d["W"]) < 1e-9)

    pairs = [(f"f{i}", f"f{i+1}") for i in range(200)]
    flips = [f for _, _, f in orient(pairs, seed=42)]
    frac = sum(flips) / len(flips)
    check("orientation is randomised, not fixed", 0.35 < frac < 0.65,
          f"{frac:.0%} flipped")
    check("orientation is reproducible from the seed",
          [f for _, _, f in orient(pairs, 42)] == flips)


# ── candidate generation ─────────────────────────────────────────────────────

def test_candidates():
    print("\ncandidate generation: union-kNN, deduplicated")
    frags, truth = make_pool(4, 6, seed=1)
    ids = [f["fragment_id"] for f in frags]
    texts = {f["fragment_id"]: f["text"] for f in frags}
    pairs, info = top_k_candidates(ids, texts, k=5)

    check("edges are undirected and deduplicated",
          all(a <= b for a, b in pairs) and len(pairs) == len(set(pairs)))
    check("count is well below n*k — reciprocal choices collapse",
          info["candidate_pairs"] < len(ids) * 5,
          f"{info['candidate_pairs']} pairs vs n*k = {len(ids) * 5}")
    check("reduction ratio reported", 0.0 < info["reduction_ratio"] < 1.0,
          f"{info['reduction_ratio']:.1%} of all pairs skipped")

    owner = {f: r for r, o in truth.items() for f in o}
    same_doc = sum(1 for a, b in pairs if owner[a] == owner[b])
    check("candidates are enriched for true co-members",
          same_doc / len(pairs) > 0.5,
          f"{same_doc}/{len(pairs)} = {same_doc/len(pairs):.0%} same-document")


# ── the pipeline ─────────────────────────────────────────────────────────────

def test_pipeline_perfect_oracle():
    print("\npipeline: perfect evidence -> near-perfect reconstruction")
    frags, truth = make_pool(4, 6, seed=1)
    members = list(truth)
    oracle = oracle_factory(truth, accuracy=1.0)

    groups, tel = attack(frags, len(members),
                         lambda p: score_pairs_offline(p, oracle, seed=5), k=6)

    ids = [f["fragment_id"] for f in frags]
    placed = [x for g in groups for x in g]
    check("every fragment placed exactly once",
          sorted(placed) == sorted(ids), f"{len(placed)} placed")
    check("exactly N clusters", tel["exact_n"], f"{tel['n_clusters']} clusters")

    res = score_joint(groups, truth, members)
    base = analytic_baseline({r: truth[r] for r in members})
    check("reconstruction far above the analytic baseline",
          res["f1"] > base["joint"] + 0.3,
          f"F1_J={res['f1']:.4f} vs baseline {base['joint']:.4f}")
    print(f"        F1_J {res['f1']:.4f}   baseline {base['joint']:.4f}   "
          f"pairs scored {tel['scored_edges']}")


def test_pipeline_degrades_with_noise():
    print("\npipeline: a coin-flip oracle must collapse toward the baseline")
    frags, truth = make_pool(4, 6, seed=1)
    members = list(truth)
    base = analytic_baseline({r: truth[r] for r in members})

    scores = {}
    for acc in (1.0, 0.75, 0.5):
        oracle = oracle_factory(truth, accuracy=acc, seed=11)
        groups, _ = attack(frags, len(members),
                           lambda p: score_pairs_offline(p, oracle, seed=5), k=6)
        scores[acc] = score_joint(groups, truth, members)["f1"]
        print(f"        oracle {acc:.0%} -> F1_J {scores[acc]:.4f}")

    check("perfect evidence beats noisy evidence",
          scores[1.0] > scores[0.75], f"{scores[1.0]:.3f} > {scores[0.75]:.3f}")
    check("noisy beats coin-flip", scores[0.75] > scores[0.5],
          f"{scores[0.75]:.3f} > {scores[0.5]:.3f}")
    check("a coin-flip oracle does NOT beat the baseline by much",
          scores[0.5] < base["joint"] + 0.25,
          f"{scores[0.5]:.3f} vs baseline {base['joint']:.3f}")


def test_output_shape_matches_one_shot():
    print("\noutput contract: identical shape to one-shot J, same scorer")
    frags, truth = make_pool(3, 5, seed=2)
    members = list(truth)
    oracle = oracle_factory(truth, accuracy=0.9)
    groups, tel = attack(frags, len(members),
                         lambda p: score_pairs_offline(p, oracle, seed=1), k=5)

    check("a list of lists of fragment ids",
          isinstance(groups, list) and all(isinstance(g, list) for g in groups))
    dec = decompose(groups, truth, members)
    check("the shared scorer accepts it with no special-casing",
          "f1_joint" in dec and "q" in dec,
          f"F1_J={dec['f1_joint']:.4f}  q={dec['q'] if dec['q'] is None else round(dec['q'],4)}")
    check("telemetry records what the order rests on",
          "arbitrary_pairs_total" in tel and "clusters_disconnected" in tel,
          f"disconnected clusters {tel['clusters_disconnected']}, "
          f"arbitrary pairs {tel['arbitrary_pairs_total']}")


def test_bridges():
    print("\nbridge repair: too-sparse evidence asks for more, never invents")
    frags, truth = make_pool(4, 5, seed=4)
    members = list(truth)
    oracle = oracle_factory(truth, accuracy=1.0)

    # k=1 leaves the membership graph badly fragmented
    groups, tel = attack(frags, len(members),
                         lambda p: score_pairs_offline(p, oracle, seed=2), k=1)
    ids = [f["fragment_id"] for f in frags]
    check("still covers every fragment under a starved k",
          sorted(x for g in groups for x in g) == sorted(ids))
    check("bridge rounds recorded", "bridge_rounds" in tel,
          f"rounds={tel['bridge_rounds']} extra pairs={tel['bridge_pairs_scored']}")
    check("no cluster was merged without an observed edge",
          tel["clustering"]["forced_merges"] == 0)


def main():
    print("=" * 70)
    print(" Hierarchical attacker — end to end, offline, no spend")
    print("=" * 70)
    test_derivation()
    test_candidates()
    test_pipeline_perfect_oracle()
    test_pipeline_degrades_with_noise()
    test_output_shape_matches_one_shot()
    test_bridges()
    print("\n" + "=" * 70)
    if _failures:
        print(f" FAILED — {len(_failures)}: {', '.join(_failures)}")
        raise SystemExit(1)
    print(" HIERARCHICAL ATTACKER PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()
