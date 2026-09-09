"""
test_repair_ledger.py — gate G1a: the attack harness behaves under failure.

These cover the cases that produce plausible-looking wrong numbers rather than
crashes, plus the two safety properties the run depends on.

Run:  python harness/test_repair_ledger.py
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from joint_metrics import ordered_pairs, score_joint
from repair import (finalise, pair_agreement, repair_report_text, validate,
                    run_with_repair, select_medoid)
from run_ledger import Ledger

_failures = []


def check(name, cond, detail=""):
    if not cond:
        _failures.append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  — ' + detail) if detail else ''}")


ALL = {"a", "b", "c", "d", "e"}


# ── validation and exhaustion ────────────────────────────────────────────────

def test_validate():
    print("\nvalidator: a deterministic function of the attacker's own view")
    r = validate([["a", "b"], ["c"]], ALL)
    check("missing detected", r["missing"] == ["d", "e"], str(r["missing"]))
    r = validate([["a", "a", "b"], ["c", "d", "e"]], ALL)
    check("duplicate detected", r["duplicated"] == ["a"])
    r = validate([["a", "b", "zz"], ["c", "d", "e"]], ALL)
    check("invented label detected", r["invalid"] == ["zz"])
    r = validate([["a", "b"], ["c", "d", "e"]], ALL)
    check("a clean answer validates", r["valid"])

    msg = repair_report_text(validate([["a"]], ALL))
    leaks = [w for w in ("cluster", "document", "belongs", "adjacent", "same record")
             if w in msg.lower()]
    check("repair message carries bookkeeping only, no ground truth",
          not leaks and "absent from your answer" in msg, msg[:60] + "...")


def test_finalise():
    print("\nexhaustion: discard invalid, first occurrence wins, then singletons")
    groups, act = finalise([["a", "b", "zz"], ["b", "c"]], ALL)
    flat = [x for g in groups for x in g]
    check("every id present exactly once", sorted(flat) == sorted(ALL),
          str(sorted(flat)))
    check("invalid discarded", act["discarded_invalid"] == 1)
    check("duplicate dropped, first occurrence kept",
          act["dropped_duplicates"] == 1 and ["a", "b"] in groups)
    check("unplaced ids became singletons", act["singletons_added"] == 2)
    check("final-attempt coverage reported under an honest name",
          abs(act["final_attempt_coverage"] - 3 / 5) < 1e-9,
          f"{act['final_attempt_coverage']:.2f}")

    # a dropped fragment must cost recall, not be invisible
    true_order = {"d1": ["a", "b", "c"], "d2": ["d", "e"]}
    members = list(true_order)
    full = score_joint([["a", "b", "c"], ["d", "e"]], true_order, members)["f1"]
    dropped, _ = finalise([["a", "b"], ["d", "e"]], ALL)      # c omitted
    part = score_joint(dropped, true_order, members)["f1"]
    check("omitting a fragment lowers the score rather than hiding",
          part < full, f"{part:.4f} < {full:.4f}")


def test_repair_loop():
    print("\nrepair loop: retries are bounded and counted as attack cost")
    calls = {"n": 0}

    def flaky(feedback):
        calls["n"] += 1
        if calls["n"] == 1:
            return [["a", "b"]]                      # drops c, d, e
        return [["a", "b", "c"], ["d", "e"]]         # corrected

    groups, rec = run_with_repair(flaky, ALL, max_retries=2)
    check("second attempt accepted", rec["calls"] == 2)
    check("a first-try failure that succeeds on retry is recorded as REPAIRED",
          rec["repair_attempted"] and rec["final_attempt_valid"]
          and not rec["forced_finalise"],
          "the old single `repaired` flag called this not-repaired")
    check("corrected answer is a valid partition",
          sorted(x for g in groups for x in g) == sorted(ALL))

    def never(feedback):
        return [["a"]]

    groups, rec = run_with_repair(never, ALL, max_retries=2)
    check("budget is bounded", rec["calls"] == 3, f"calls={rec['calls']}")
    check("exhaustion still yields a full partition",
          sorted(x for g in groups for x in g) == sorted(ALL))
    check("exhaustion recorded, not silent",
          rec["forced_finalise"] and not rec["final_attempt_valid"]
          and rec["singletons_added"] == 4)

    singles = [[x] for x in sorted(ALL)]
    r_no_n = validate(singles, ALL)
    r_with_n = validate(singles, ALL, expected_n=2)
    check("without expected_n an all-singleton partition validates",
          r_no_n["valid"])
    check("WITH expected_n it does not -- the known-N attacker must use N",
          not r_with_n["valid"] and r_with_n["group_count_error"],
          f"returned {r_with_n['n_groups']} groups, expected 2")
    msg = repair_report_text(r_with_n)
    check("group-count feedback is bookkeeping, not truth",
          "5 groups" in msg and "specifies 2" in msg
          and "belongs" not in msg.lower(), msg[:70] + "...")

    def explodes(feedback):
        raise ValueError("malformed JSON")

    groups, rec = run_with_repair(explodes, ALL, max_retries=1)
    check("a raising attacker consumes budget and still returns a partition",
          rec["calls"] == 2 and sorted(x for g in groups for x in g) == sorted(ALL))
    check("the error is recorded", rec["attempts"][0]["error"] is not None)


# ── medoid selection ─────────────────────────────────────────────────────────

def test_medoid():
    print("\nmedoid-of-k: truth-free, and repair must precede it")
    good = [["a", "b", "c"], ["d", "e"]]
    also = [["a", "b", "c"], ["d", "e"]]
    odd = [["a", "d"], ["b", "e"], ["c"]]
    idx, scores = select_medoid([good, also, odd])
    check("the answer agreeing with the others is chosen", idx in (0, 1),
          f"idx={idx} scores={[round(s,3) for s in scores]}")

    check("identical inputs give a deterministic index",
          select_medoid([good, also])[0] == select_medoid([good, also])[0])

    # the reason repair runs first: two near-empty answers agree trivially
    sparse_a, sparse_b = [["a", "b"]], [["a", "b"]]
    real = [["a", "b", "c"], ["d", "e"]]
    idx_raw, _ = select_medoid([sparse_a, sparse_b, real])
    rep_a, _ = finalise(sparse_a, ALL)
    rep_b, _ = finalise(sparse_b, ALL)
    rep_r, _ = finalise(real, ALL)
    idx_rep, _ = select_medoid([rep_a, rep_b, rep_r])
    check("sparse answers win on agreement BEFORE repair (the trap)",
          idx_raw in (0, 1), f"idx={idx_raw}")
    check("still resolvable after repair, and every candidate is complete",
          all(sorted(x for g in c for x in g) == sorted(ALL)
              for c in (rep_a, rep_b, rep_r)), f"idx={idx_rep}")

    check("agreement uses no ground truth (identical answers -> 1.0)",
          abs(pair_agreement(good, also) - 1.0) < 1e-9)


# ── ledger ───────────────────────────────────────────────────────────────────

def test_ledger():
    print("\nledger: durable state and the spend cap")
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "ledger.json")
        led = Ledger(path, max_spend=100.0)

        check("unknown step is pending", led.state("step2") == "pending")
        led.reserve("step2", projected_usd=20.0, n_requests=571)
        led.attach_batch("step2", "batch_abc")
        check("batch id persisted immediately",
              led.step("step2")["batch_id"] == "batch_abc")

        reopened = Ledger(path, max_spend=100.0)
        check("survives a process restart",
              reopened.state("step2") == "submitted"
              and reopened.step("step2")["batch_id"] == "batch_abc")

        reopened.mark("step2", "scored")
        check("completed steps are skippable", reopened.is_done("step2"))

        led2 = Ledger(path, max_spend=100.0)
        ok, msg = led2.check_spend(30.0)
        check("a submission under the cap is allowed", ok, msg.split("(")[0].strip())

        ok, msg = led2.check_spend(95.0)
        check("a submission over the cap is refused", not ok)
        check("refusal prints the documented cut order",
              "cut order" in msg and "repeats" in msg and "clause row" in msg)

        led3 = Ledger(os.path.join(td, "l3.json"), max_spend=100.0)
        led3.reserve("step4", 30.0, 100)
        check("reservation commits spend BEFORE the provider call",
              abs(led3.committed - 30.0) < 1e-9
              and led3.state("step4") == "submitted")
        check("a dangling reservation is detectable after a crash",
              led3.dangling_reservations() == ["step4"])
        led3.attach_batch("step4", "batch_xyz")
        check("attaching the id clears the dangling state",
              led3.dangling_reservations() == []
              and led3.step("step4")["batch_id"] == "batch_xyz")

        led4 = Ledger(os.path.join(td, "l4.json"), max_spend=100.0)
        led4.reserve("step5", 25.0, 10)
        led4.release("step5", 25.0, reason="create() failed")
        check("a failed create() releases the reservation",
              abs(led4.committed) < 1e-9 and led4.state("step5") == "failed")

        led2.observe(45.0)
        check("projection uses max(committed, observed), not just one",
              abs(led2.projected_total(0.0) - 45.0) < 1e-9,
              f"committed 20, observed 45 -> {led2.projected_total(0.0):.2f}")


def main():
    print("=" * 70)
    print(" G1a — repair protocol, medoid selection, spend ledger")
    print("=" * 70)
    test_validate()
    test_finalise()
    test_repair_loop()
    test_medoid()
    test_ledger()
    print("\n" + "=" * 70)
    if _failures:
        print(f" FAILED — {len(_failures)}: {', '.join(_failures)}")
        raise SystemExit(1)
    print(" G1a PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()
