"""
test_joint_metrics.py — gate G0.

Nothing downstream is trustworthy until these pass. Each test corresponds to a
claim the paper makes or an error that was actually made and caught:

  identity 1   F1_J = (1+tau)/2 under perfect membership -- NOT tau. The code
               and its docstring asserted "reduces to tau" and would have
               shipped that.
  identity 2   F1_J = F1_L * (C/K), the decomposition that replaced the
               confounded J-minus-O gap.
  identity 3   baseline_joint = baseline_linkage / 2, closed form.
  K = 0        q is undefined, never 0.
  sum(K) = 0   a bootstrap replicate over only-failed pools is undefined, not a
               ZeroDivisionError.
  pairing      the paired bootstrap shares indices across every cell.

Run:  python harness/test_joint_metrics.py
"""

import os
import sys

import numpy as np
from scipy.stats import kendalltau

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from joint_metrics import (advantage, analytic_baseline, decompose, micro_q,
                           ordered_pairs, paired_bootstrap_indices, score_joint)

TOL = 1e-9
_failures = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    if not condition:
        _failures.append(name)
    print(f"  [{status}] {name}{('  — ' + detail) if detail else ''}")


# ── identity 1: F1_J = (1+tau)/2 under perfect membership ────────────────────

def test_tau_identity():
    print("\nidentity 1: perfect membership -> F1_J = (1+tau)/2, not tau")
    rng = np.random.default_rng(0)
    worst = 0.0
    for n in (5, 12, 25, 40):
        for _ in range(25):
            truth = [f"f{i:03d}" for i in range(n)]
            guess = list(truth)
            rng.shuffle(guess)
            f1 = score_joint([guess], {"d": truth}, ["d"])["f1"]
            pos = {f: i for i, f in enumerate(truth)}
            tau = kendalltau([pos[f] for f in guess], list(range(n))).statistic
            worst = max(worst, abs(f1 - (1 + tau) / 2))
    check("F1_J == (1+tau)/2 over 100 shuffles", worst < TOL,
          f"max deviation {worst:.2e}")

    # and confirm it is NOT tau, so a future edit cannot quietly revert the claim
    truth = ["a", "b", "c", "d"]
    rev = score_joint([list(reversed(truth))], {"d": truth}, ["d"])["f1"]
    check("full reversal -> F1_J 0.0 while tau = -1.0", abs(rev - 0.0) < TOL,
          f"F1_J={rev:.4f}")


# ── identity 2: F1_J = F1_L * (C/K) ──────────────────────────────────────────

def test_decomposition_identity():
    print("\nidentity 2: F1_J = F1_L * (C/K)")
    true_order = {"d1": ["a", "b", "c", "d"], "d2": ["x", "y", "z"]}
    members = ["d1", "d2"]
    cases = {
        "perfect": [["a", "b", "c", "d"], ["x", "y", "z"]],
        "mixed membership + order": [["a", "c", "b", "x"], ["d", "z", "y"]],
        "split groups": [["b", "a"], ["c", "d"], ["y", "x", "z"]],
        "one bucket": [["a", "b", "c", "d", "x", "y", "z"]],
    }
    worst = 0.0
    for name, groups in cases.items():
        d = decompose(groups, true_order, members)
        if d["q"] is None:
            continue
        worst = max(worst, abs(d["f1_joint"] - d["f1_linkage"] * d["q"]))
    check("F1_J == F1_L * q on 4 constructed cases", worst < TOL,
          f"max deviation {worst:.2e}")


# ── identity 3: the analytic baseline ────────────────────────────────────────

def test_baseline_identity():
    print("\nidentity 3: analytic baseline, joint == linkage / 2")
    rng = np.random.default_rng(7)
    worst_half, worst_mc = 0.0, 0.0
    for _ in range(20):
        sizes = [int(x) for x in rng.integers(2, 30, size=int(rng.integers(2, 8)))]
        groups = {}
        nxt = 0
        for i, s in enumerate(sizes):
            groups[f"d{i}"] = [f"f{nxt + j:04d}" for j in range(s)]
            nxt += s
        base = analytic_baseline(groups)
        worst_half = max(worst_half, abs(base["joint"] * 2 - base["linkage"]))

        # Monte-Carlo agreement: one bucket, random order, averaged
        ids = [f for v in groups.values() for f in v]
        order = {k: list(v) for k, v in groups.items()}
        acc = 0.0
        trials = 300
        for t in range(trials):
            shuffled = list(ids)
            np.random.default_rng(t).shuffle(shuffled)
            acc += score_joint([shuffled], order, list(groups))["f1"]
        worst_mc = max(worst_mc, abs(acc / trials - base["joint"]))
    check("baseline_joint * 2 == baseline_linkage", worst_half < TOL,
          f"max deviation {worst_half:.2e}")
    check("analytic baseline matches Monte-Carlo", worst_mc < 0.01,
          f"max deviation {worst_mc:.4f}")


# ── behaviour on known inputs ────────────────────────────────────────────────

def test_known_values():
    print("\nbehaviour on constructed answers (3 docs x 25 fragments)")
    true_order = {f"d{i}": [f"d{i}_f{j:02d}" for j in range(25)] for i in range(3)}
    members = list(true_order)

    perfect = [true_order[r] for r in members]
    check("perfect -> 1.000",
          abs(score_joint(perfect, true_order, members)["f1"] - 1.0) < TOL)

    swapped = [list(true_order[r]) for r in members]
    for g in swapped:
        g[0], g[1] = g[1], g[0]
    f1_swap = score_joint(swapped, true_order, members)["f1"]
    check("one adjacent swap per document -> ~0.997, degrades gracefully",
          0.99 < f1_swap < 1.0, f"F1_J={f1_swap:.4f}")

    base = analytic_baseline(true_order)
    bucket = [[f for r in members for f in true_order[r]]]
    f1_bucket_true = score_joint(bucket, true_order, members)["f1"]
    check("one bucket in TRUE order beats the arbitrary-order baseline",
          f1_bucket_true > base["joint"],
          f"{f1_bucket_true:.4f} vs baseline {base['joint']:.4f}")

    check("advantage() is 0 at the baseline and 1 at perfect",
          abs(advantage(base["joint"], base["joint"])) < TOL
          and abs(advantage(1.0, base["joint"]) - 1.0) < TOL)


# ── K = 0 and sum(K) = 0 ─────────────────────────────────────────────────────

def test_k_zero_policy():
    print("\nK = 0 policy: undefined, never 0")
    # every guessed pair is wrong AND no true pair is co-clustered
    true_order = {"d1": ["a", "b"], "d2": ["x", "y"]}
    members = ["d1", "d2"]
    d = decompose([["a", "x"], ["b", "y"]], true_order, members)
    check("K == 0 -> q is None, not 0.0", d["K"] == 0 and d["q"] is None,
          f"K={d['K']} q={d['q']!r}")
    check("K == 0 -> a_order is None, not -1.0", d["a_order"] is None)

    q, undef = micro_q([d, d, d])
    check("micro_q over only-failed pools -> None, no ZeroDivisionError",
          q is None and undef == 3, f"q={q!r} undefined={undef}")

    good = decompose([["a", "b"], ["x", "y"]], true_order, members)
    q2, undef2 = micro_q([d, good])
    check("micro_q mixes defined and undefined pools correctly",
          q2 is not None and undef2 == 1, f"q={q2:.4f} undefined={undef2}")


# ── the paired bootstrap ─────────────────────────────────────────────────────

def test_paired_bootstrap():
    print("\npaired bootstrap: every cell resampled with the SAME indices")
    rng = np.random.default_rng(3)
    n_pools = 25
    strategies = ["semantic", "random", "token-window"]
    attackers = ["one-shot", "hierarchical"]
    cells = {s: {a: list(range(n_pools)) for a in attackers} for s in strategies}

    shared = True
    for idx in paired_bootstrap_indices(n_pools, 50, rng):
        drawn = {s: {a: [cells[s][a][i] for i in idx] for a in attackers}
                 for s in strategies}
        first = drawn[strategies[0]][attackers[0]]
        for s in strategies:
            for a in attackers:
                if drawn[s][a] != first:
                    shared = False
        if len(idx) != n_pools:
            shared = False
    check("indices identical across 3 strategies x 2 attackers, 50 replicates",
          shared)

    rng2 = np.random.default_rng(3)
    again = list(paired_bootstrap_indices(n_pools, 5, rng2))
    rng3 = np.random.default_rng(3)
    check("same seed reproduces the same index vectors",
          again == list(paired_bootstrap_indices(n_pools, 5, rng3)))


def main():
    print("=" * 70)
    print(" G0 — metric identities. Nothing downstream is trustworthy until")
    print(" these pass.")
    print("=" * 70)
    test_tau_identity()
    test_decomposition_identity()
    test_baseline_identity()
    test_known_values()
    test_k_zero_policy()
    test_paired_bootstrap()

    print("\n" + "=" * 70)
    if _failures:
        print(f" G0 FAILED — {len(_failures)} check(s): {', '.join(_failures)}")
        raise SystemExit(1)
    print(" G0 PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()
