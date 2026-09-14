"""
test_visible_metrics.py — score-free validation of the visible-text scorer and its
nulls on CONSTRUCTED data only (no experimental attacker output). Frozen with
the scorer in RUN_DECISIONS D16.

    python harness/test_visible_metrics.py
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np                                                    # noqa: E402

from visible_metrics import (PoolScorer, advantage, lcs_dp, lcs_len, masks_of,  # noqa: E402
                             null_rng, oracle_size_null, predicted_structure_null)

FAIL = []


def check(name, cond, detail=""):
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  -- ' + detail) if detail else ''}")
    if not cond:
        FAIL.append(name)


def make_truth(rep, docs_tokens):
    """rep='token': one fragment per token; rep='sentence': one fragment per
    4-token 'sentence' chunk. Returns truth_order, text_of."""
    truth, text = {}, {}
    for d, toks in docs_tokens.items():
        order = []
        units = [[t] for t in toks] if rep == "token" else [toks[i:i + 4] for i in range(0, len(toks), 4)]
        for j, u in enumerate(units):
            fid = f"{d}_{rep[0]}{j:03d}"
            text[fid] = " ".join(u)
            order.append(fid)
        truth[d] = order
    return truth, text


def zipf_docs(n_docs=7, length=80, vocab=60, seed=1):
    rng = random.Random(seed)
    words = [f"w{i}" for i in range(vocab)]
    weights = [1 / (i + 1) for i in range(vocab)]
    return {f"doc{d}": rng.choices(words, weights, k=length) for d in range(n_docs)}


def main():
    rng = random.Random(7)
    # LCS implementation against the reference DP
    ok = all(lcs_len(a, masks_of(b), len(b)) == lcs_dp(a, b)
             for a, b in ([[rng.randrange(6) for _ in range(rng.randrange(0, 60))] for _ in range(2)]
                          for _ in range(3000)))
    check("bit-parallel LCS equals the reference DP (3,000 random pairs)", ok)

    docs = zipf_docs()
    for rep in ("token", "sentence"):
        truth, text = make_truth(rep, docs)
        ps = PoolScorer(truth, text)
        perfect = [list(v) for v in truth.values()]
        s = ps.score(perfect)
        check(f"[{rep}] perfect reconstruction = 1", s["V_L"] == 1 and s["V_J"] == 1)
        rev = [list(reversed(v)) for v in truth.values()]
        s2 = ps.score(rev)
        check(f"[{rep}] reversal keeps V_L, lowers V_J", s2["V_L"] == 1 and s2["V_J"] < 1, f"V_J {s2['V_J']:.3f}")
        shuf = [random.Random(3).sample(v, len(v)) for v in truth.values()]
        s3 = ps.score(shuf)
        check(f"[{rep}] correct membership, wrong order: V_L = 1, V_J < 1", s3["V_L"] == 1 and s3["V_J"] < 1)
        moved = [list(v) for v in truth.values()]
        moved[0], moved[1] = moved[0][: len(moved[0]) // 2] + moved[1][len(moved[1]) // 2:], \
            moved[1][: len(moved[1]) // 2] + moved[0][len(moved[0]) // 2:]
        s4 = ps.score(moved)
        check(f"[{rep}] wrong membership lowers V_L", s4["V_L"] < 1, f"V_L {s4['V_L']:.3f}")
        perm_labels = list(reversed(perfect))
        check(f"[{rep}] predicted group-label permutation changes nothing", ps.score(perm_labels)["V_J"] == 1)
        one = [[f for v in truth.values() for f in v]]
        s5 = ps.score(one)
        check(f"[{rep}] all fragments in one group: finite, V_J <= V_L < 1", s5["V_J"] <= s5["V_L"] < 1)
        emp = [[]] + perfect[1:] + [perfect[0]]
        check(f"[{rep}] an empty predicted group is harmless", ps.score(emp)["V_J"] == 1)
        flat = [f for v in truth.values() for f in v]
        unbal = [flat[:3], flat[3:6], flat[6:]]
        s6 = ps.score(unbal)
        check(f"[{rep}] highly unbalanced groups: finite, V_J <= V_L", s6["V_J"] <= s6["V_L"])
        a, b = ps.score(unbal), ps.score(unbal)
        check(f"[{rep}] deterministic (values and assignments) on repeat", a == b)
        # V_J <= V_L on many random reconstructions
        allok = True
        r8 = random.Random(11)
        for _ in range(200):
            f = flat[:]
            r8.shuffle(f)
            k = r8.randrange(1, 12)
            cuts = sorted(r8.sample(range(1, len(f)), k - 1)) if k > 1 else []
            gs = [f[i:j] for i, j in zip([0] + cuts, cuts + [len(f)])]
            sc = ps.score(gs)
            allok &= sc["V_J"] <= sc["V_L"] + 1e-12
        check(f"[{rep}] V_J <= V_L on 200 random reconstructions", allok)

    # swapping hidden ids of identical visible tokens: visible score unchanged, id-level F1_J drops
    truth, text = make_truth("token", docs)
    ps = PoolScorer(truth, text)
    perfect = [list(v) for v in truth.values()]
    by_text = {}
    for d, v in truth.items():
        for f in v:
            by_text.setdefault(text[f], []).append((d, f))
    word, occ = next((w, o) for w, o in by_text.items() if len({d for d, _ in o}) >= 2)
    (d1, f1), (d2, f2) = next((x, y) for x in occ for y in occ if x[0] != y[0])
    swapped = [[f2 if f == f1 else f1 if f == f2 else f for f in g] for g in perfect]
    sv = ps.score(swapped)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from joint_metrics import score_joint
    idf1 = score_joint(swapped, truth, list(truth))["f1"]
    check("swapping hidden ids of identical visible tokens (across sources) changes nothing visible",
          sv["V_L"] == 1 and sv["V_J"] == 1, f"id-level F1_J would drop to {idf1:.4f}")
    check("repeated identical tokens across sources: a perfect reconstruction still scores 1",
          len(occ) >= 2 and ps.score(perfect)["V_J"] == 1, f"'{word}' occurs {len(occ)}x in {len({d for d, _ in occ})} docs")
    # Hungarian ties: two identical documents -> any pairing is optimal; value and assignment stable
    tie_docs = {"A": ["x", "y", "z"], "B": ["x", "y", "z"], "C": ["p", "q"]}
    tt, tx = make_truth("token", tie_docs)
    tps = PoolScorer(tt, tx)
    tie_groups = [tt["B"], tt["A"], tt["C"]]
    r1, r2 = tps.score(tie_groups), tps.score(tie_groups)
    check("Hungarian ties: value = 1 and the assignment is identical on repeat", r1["V_J"] == 1 and r1 == r2)
    # perfect sentence and perfect token reconstructions of the same text both score 1
    ts, xs = make_truth("sentence", docs)
    tk, xk = make_truth("token", docs)
    check("perfect sentence and perfect token reconstructions both give V_J = 1",
          PoolScorer(ts, xs).score(list(ts.values()))["V_J"] == 1 == PoolScorer(tk, xk).score(list(tk.values()))["V_J"])
    # nulls: seeded, reproducible, and the advantage algebra
    ps = PoolScorer(tk, xk)
    n1 = oracle_size_null(ps, 50, null_rng("p0", "token", "oracle"))
    n2 = oracle_size_null(ps, 50, null_rng("p0", "token", "oracle"))
    check("oracle-size null is reproducible from its seed", np.array_equal(n1, n2))
    check("null draws satisfy V_J <= V_L", bool((n1[:, 1] <= n1[:, 0] + 1e-12).all()))
    pn = predicted_structure_null(ps, [list(v) for v in tk.values()], 20, null_rng("p0", "token", "pred"))
    check("predicted-structure null runs on a given structure", pn.shape == (20, 2))
    check("advantage: V = null mean -> 0; V = 1 -> 1", advantage(0.3, 0.3) == 0 and advantage(1.0, 0.3) == 1)

    # controlled corruption on synthetic ground truth, both representations
    print("\n  controlled corruption (synthetic Zipf ground truth, 7 docs x 80 tokens; mean of 20 draws)")
    print(f"  {'representation':<10}{'corruption':<34}{'V_L':>7}{'V_J':>7}")
    for rep in ("sentence", "token"):
        truth, text = make_truth(rep, docs)
        ps = PoolScorer(truth, text)
        null = oracle_size_null(ps, 100, null_rng("synthetic", rep, "oracle")).mean(0)
        print(f"  {rep:<10}{'oracle-size null mean':<34}{null[0]:>7.3f}{null[1]:>7.3f}")
        for kind in ("membership", "order"):
            for p in (0.0, 0.1, 0.25, 0.5, 1.0):
                vs = []
                for k in range(20):
                    rr = random.Random(1000 * k + int(p * 100))
                    gs = [list(v) for v in truth.values()]
                    if kind == "membership":
                        flat = [(gi, f) for gi, g in enumerate(gs) for f in g]
                        mv = rr.sample(flat, int(p * len(flat)))
                        for gi, f in mv:
                            gs[gi].remove(f)
                            gs[rr.randrange(len(gs))].append(f)
                    else:
                        for g in gs:
                            idx = rr.sample(range(len(g)), int(p * len(g)))
                            vals = [g[i] for i in idx]
                            rr.shuffle(vals)
                            for i, v in zip(idx, vals):
                                g[i] = v
                    s = ps.score(gs)
                    vs.append((s["V_L"], s["V_J"]))
                m = np.mean(vs, 0)
                print(f"  {rep:<10}{kind + f' {p:.0%}':<34}{m[0]:>7.3f}{m[1]:>7.3f}")
    print(f"\nVISIBLE METRICS {'PASSED' if not FAIL else 'FAILED: ' + ', '.join(FAIL)}")
    if FAIL:
        sys.exit(1)


if __name__ == "__main__":
    main()
