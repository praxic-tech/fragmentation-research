"""
test_memon_joint.py — gate G5a: the free n-gram attacker, and the ID leak it found.

The headline test here is `test_zero_evidence_scores_at_chance`. Everything else
is contract checking; that one is the regression for a bug that produced a
PERFECT score from NO evidence.

WHAT HAPPENED
-------------
Running the n-gram joint attacker across n = 2..8 on a real cell gave a tidy,
publishable-looking monotone trend:

    n     F1_J      q        context coverage
    2    0.1706   0.5738     10.5%
    6    0.2911   0.9789      0.1%
    8    0.2974   1.0000      0.0%

Ordering accuracy rising to 100% while the statistic's context coverage falls to
zero is not a trend, it is a tell. At n = 8 all 6,543 within-cluster pairs came
back at weight exactly 0.0 -- the boundary model had never seen a single context,
so `p_char` returned the same smoothing prior in both directions and the
difference was 0 by construction. `order_cluster` then fell through to its
documented evidence-free tie rule, which orders by smallest member, and the
fragment ids were `prose_0002_frag_000`, `prose_0002_frag_001`, ...

Sorting those IS the answer key. q = 1.0000 with zero evidence.

The tie rule is not the bug: it is labelled evidence-free and it must return
something. The bug is that "evidence-free" only means "arbitrary" when the
identifiers are arbitrary. `preflight()` catches raw ids in PROMPTS, which is
exactly no protection for an offline attacker that never builds one.

Fix: `masking.assert_ids_masked` on every attacker's input, model-driven or not,
and `memon_joint.attack` masks internally so a caller cannot forget.

After the fix, across 20 alias seeds: q = 0.4959 +/- 0.0232 at n = 8. Chance.

Run:  python harness/test_memon_joint.py
"""

import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "adversaries"))

from joint_metrics import analytic_baseline, decompose, score_joint
from masking import IdLeakError, assert_ids_masked
from memon_joint import _weight, attack, group_known_n

_failures = []


def check(name, cond, detail=""):
    if not cond:
        _failures.append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  — ' + detail) if detail else ''}")


# ── a corpus whose ids spell out the answer, exactly like the real one ───────

TOPICS = {
    "cardiac": "chest pain angina troponin ecg stent coronary artery infarct",
    "renal": "creatinine dialysis nephritis kidney urea glomerular renal biopsy",
    "neuro": "seizure cortex mri lesion aphasia neurology stroke thrombolysis",
    "hepatic": "jaundice bilirubin cirrhosis hepatic ascites portal liver enzyme",
}


def make_pool(n_docs=4, frags_per_doc=6, seed=1):
    rng = random.Random(seed)
    frags, truth = [], {}
    for d, topic in enumerate(list(TOPICS)[:n_docs]):
        words = TOPICS[topic].split()
        rid = f"prose_{d:04d}"
        order = []
        for p in range(frags_per_doc):
            fid = f"{rid}_frag_{p:03d}"
            frags.append({"fragment_id": fid, "record_id": rid,
                          "text": " ".join(rng.sample(words, 5))
                                  + f" step {p} of the {topic} course"})
            order.append(fid)
        truth[rid] = order
    return frags, truth


# ── the leak ─────────────────────────────────────────────────────────────────

def test_guard_rejects_raw_ids():
    print("\nguard: raw fragment ids are refused wherever an attacker reads them")
    try:
        assert_ids_masked(["prose_0002_frag_000", "prose_0002_frag_001"])
        check("raw prose ids raise", False)
    except IdLeakError as e:
        check("raw prose ids raise IdLeakError", "raw fragment" in str(e),
              str(e)[:64] + "...")
    try:
        assert_ids_masked(["f_01326"])
        check("raw identifier ids raise", False)
    except IdLeakError:
        check("raw identifier-corpus ids raise too", True)

    check("masked aliases pass",
          assert_ids_masked(["m_0000001", "m_0000002"]) is not None)


def test_zero_evidence_scores_at_chance():
    print("\nTHE REGRESSION: no evidence must score at chance, not perfectly")
    frags, truth = make_pool()
    members = list(truth)
    base = analytic_baseline({r: truth[r] for r in members})

    # n = 12 on ~45-character fragments: no context is ever seen twice, so every
    # pair comes back at weight 0 and ordering rests entirely on the tie rule.
    qs, f1s, links, cov = [], [], [], None
    for s in range(20):
        groups, tel = attack(frags, len(members), n=12, d=12, mask_seed=900 + s)
        dec = decompose(groups, truth, members)
        cov = tel["context_coverage"]
        if dec["q"] is not None:
            qs.append(dec["q"])
        f1s.append(dec["f1_joint"])
        links.append(dec["f1_linkage"])
        if s == 0:
            check("the regime is genuinely evidence-free",
                  tel["zero_weight_pairs"] == tel["score_pair_calls"] // 2
                  and cov == 0.0,
                  f"{tel['zero_weight_pairs']} of "
                  f"{tel['score_pair_calls'] // 2} pairs at weight 0, "
                  f"context coverage {cov:.1%}")

    mean_q = statistics.mean(qs)
    check("ordering accuracy sits at chance, not at 1.0",
          abs(mean_q - 0.5) < 0.08,
          f"q = {mean_q:.4f} +/- {statistics.stdev(qs):.4f} over 20 alias seeds "
          f"(the leak read 1.0000)")
    check("no alias seed produces a suspiciously perfect ordering",
          max(qs) < 0.95, f"max q = {max(qs):.4f}")
    # NOT "F1_J near the analytic baseline": this fixture's topics are trivially
    # separable, so grouping is near-perfect and F1_J = F1_L * q rides on the
    # LINKAGE the attacker really did earn. The claim under test is that the
    # ORDERING half contributes nothing, which is F1_J ~ F1_L/2. The leak drove
    # q to 1.0 and F1_J to F1_L.
    mf1, mlink = statistics.mean(f1s), statistics.mean(links)
    check("joint F1 is half of linkage F1 -- ordering earns nothing",
          abs(mf1 - mlink / 2.0) < 0.06,
          f"F1_J = {mf1:.4f}, F1_L = {mlink:.4f}, F1_L/2 = {mlink / 2:.4f}")
    check("joint F1 is nowhere near linkage F1, which is what the leak gave",
          mf1 < mlink * 0.75,
          f"{mf1:.4f} < {mlink * 0.75:.4f}   (baseline_J {base['joint']:.4f})")


def test_masking_is_not_optional():
    print("\nmasking happens inside the attacker, so a caller cannot skip it")
    frags, truth = make_pool()
    groups, tel = attack(frags, len(truth), n=3, d=3)
    ids = [f["fragment_id"] for f in frags]
    placed = [x for g in groups for x in g]
    check("output comes back in the caller's id space",
          sorted(placed) == sorted(ids), f"{len(placed)} placed")
    check("the alias seed is recorded for reproduction",
          tel["mask_seed"] is not None, str(tel["mask_seed"]))

    a, _ = attack(frags, len(truth), n=3, d=3, mask_seed=7)
    b, _ = attack(frags, len(truth), n=3, d=3, mask_seed=7)
    check("identical alias seed gives identical output", a == b)


# ── contracts ────────────────────────────────────────────────────────────────

def test_weight_algebra():
    print("\nweight: antisymmetric by construction, bounded, -inf handled")
    check("W_ji = -W_ij exactly",
          all(abs(_weight(a, b) + _weight(b, a)) < 1e-12
              for a, b in ((-1.0, -2.0), (0.5, 0.5), (-8.0, -3.2), (2.0, -9.0))))
    check("equal scores give no preference", _weight(-3.0, -3.0) == 0.0)
    check("bounded in [-1, 1]",
          all(-1.0 <= _weight(a, b) <= 1.0
              for a, b in ((-1e9, 0.0), (0.0, -1e9), (500.0, -500.0))))
    check("both directions unevaluable is absence of evidence, weight 0",
          _weight(float("-inf"), float("-inf")) == 0.0)
    check("one direction unevaluable is a definite preference",
          _weight(float("-inf"), -2.0) == -1.0
          and _weight(-2.0, float("-inf")) == 1.0)


def test_exactly_n():
    print("\ngrouping: exactly N, and what maxclust would have given")
    frags, truth = make_pool()
    ids = [f["fragment_id"] for f in frags]
    texts = {f["fragment_id"]: f["text"] for f in frags}
    for n in (2, 3, 4, 6):
        clusters, info = group_known_n(ids, texts, n)
        if len(clusters) != n or not info["exact_n"]:
            check(f"exactly N at N={n}", False, f"got {len(clusters)}")
            break
    else:
        check("cut_tree gives exactly N at N = 2, 3, 4, 6", True)

    clusters, info = group_known_n(ids, texts, 4)
    check("every fragment placed exactly once",
          sorted(x for c in clusters for x in c) == sorted(ids))
    check("the legacy maxclust count is reported beside it, not assumed",
          "maxclust_n_groups" in info,
          f"cut_tree {info['n_groups']}, maxclust {info['maxclust_n_groups']}")


def test_output_contract():
    print("\noutput contract: the shared scorer takes it with no special case")
    frags, truth = make_pool()
    members = list(truth)
    groups, tel = attack(frags, len(members), n=4, d=4)
    check("a list of lists of fragment ids",
          isinstance(groups, list) and all(isinstance(g, list) for g in groups))
    res = score_joint(groups, truth, members)
    check("scored by joint_metrics directly",
          0.0 <= res["f1"] <= 1.0, f"F1_J={res['f1']:.4f}")
    check("telemetry says what the ordering rests on",
          "context_coverage" in tel and "zero_weight_pairs" in tel
          and "arbitrary_pairs" in tel,
          f"coverage {tel['context_coverage']:.1%}, "
          f"zero-weight {tel['zero_weight_pairs']}")
    check("the attack is free", tel["attacker"] == "memon-joint")


def main():
    print("=" * 70)
    print(" G5a — n-gram joint attacker, and the evidence-free-score regression")
    print("=" * 70)
    test_guard_rejects_raw_ids()
    test_zero_evidence_scores_at_chance()
    test_masking_is_not_optional()
    test_weight_algebra()
    test_exactly_n()
    test_output_contract()
    print("\n" + "=" * 70)
    if _failures:
        print(f" FAILED — {len(_failures)}: {', '.join(_failures)}")
        raise SystemExit(1)
    print(" G5a PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()
