"""
test_integrity.py — gate G1b: a run with holes in it must refuse to report.

The free-tier grid printed clean-looking, wrong means in five of twelve cells.
The Groq daily quota ran out; every attempt on a unit raised; repair treated the
raise as an empty answer; the completion policy then supplied the whole order.
74-85% of the fragments in four cells were ours, not the model's, and those four
cells topped the ranking. Separately, a wall-clock timeout killed processes
mid-cell and silently dropped each cell's trailing documents.

Nothing crashed. Every number looked reasonable. That is the failure this gate
exists for, on both paths a run can take:

    interactive   joint_game never writes a NoModelAnswer unit, and
                  cell_integrity refuses any cell with a missing or
                  mostly-policy unit
    batch (paid)  batch_submit.require_complete refuses a result set with any
                  errored, expired, canceled, empty or missing request

Run:  python harness/test_integrity.py
"""

import glob
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "adversaries"))

from batch_submit import IncompleteBatchError, failed_ids, require_complete
from joint_game import (POLICY_CAP, _no_model_answer, _policy_share,
                        cell_integrity)

_failures = []


def check(name, cond, detail=""):
    if not cond:
        _failures.append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  — ' + detail) if detail else ''}")


def _write(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + chr(10))


def _ok(cid):
    return {"custom_id": cid, "result_type": "succeeded",
            "text": '[["m_0000001", "m_0000002"]]'}


# ── the paid path ────────────────────────────────────────────────────────────

def test_batch_gate():
    print("\nbatch gate: scoring refuses any result set with a hole in it")
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "results.jsonl")

        _write(out, [_ok("a"), _ok("b"), _ok("c")])
        rows = require_complete(out, ["a", "b", "c"])
        check("a complete, all-succeeded set passes", set(rows) == {"a", "b", "c"})

        try:
            require_complete(out, ["a", "b", "c", "d"])
            check("a request that never came back is refused", False)
        except IncompleteBatchError as e:
            check("a request that never came back is refused",
                  "never came back" in str(e), str(e)[:60] + "...")

        holes = {
            "errored": {"custom_id": "c", "result_type": "errored",
                        "error": "overloaded_error"},
            "expired": {"custom_id": "c", "result_type": "expired",
                        "error": "expired"},
            "canceled": {"custom_id": "c", "result_type": "canceled",
                         "error": "canceled"},
            "empty (all reasoning)": {"custom_id": "c",
                                      "result_type": "succeeded",
                                      "error": "ZeroAnswerError"},
            "empty text, no error flag": {"custom_id": "c",
                                          "result_type": "succeeded",
                                          "text": "   "},
        }
        for kind, bad in holes.items():
            _write(out, [_ok("a"), _ok("b"), bad])
            try:
                require_complete(out, ["a", "b", "c"])
                check(f"a {kind} result is refused", False, "was accepted")
            except IncompleteBatchError:
                check(f"a {kind} result is refused", True)

        _write(out, [_ok("a"), _ok("b"),
                     {"custom_id": "c", "result_type": "errored", "error": "x"},
                     _ok("c")])
        check("a resubmitted id that later succeeds is accepted",
              set(require_complete(out, ["a", "b", "c"])) == {"a", "b", "c"})
        check("failed_ids reads the LATEST row per id", failed_ids(out) == [])


# ── the interactive path ─────────────────────────────────────────────────────

def _scored(unit, share=0.0, no_answer=False):
    return {"unit": unit, "policy_share": share, "no_model_answer": no_answer}


def test_cell_gate():
    print("\ncell gate: a mean is withheld for any cell with a hole in it")
    exp = ["d1", "d2", "d3"]

    v = cell_integrity([_scored("d1"), _scored("d2"), _scored("d3", 0.10)], exp)
    check("a complete cell under the cap passes", v["ok"],
          f"policy share {v['policy_share']:.1%}")

    v = cell_integrity([_scored("d1"), _scored("d2")], exp)
    check("a missing unit refuses the cell",
          not v["ok"] and v["missing"] == ["d3"], f"missing {v['missing']}")

    v = cell_integrity([_scored("d1"), _scored("d2"),
                        _scored("d3", 1.0, no_answer=True)], exp)
    check("a stored row with no model answer counts as MISSING, not as a score",
          not v["ok"] and v["missing"] == ["d3"],
          "the pre-fix code wrote these; they must not look answered")

    v = cell_integrity([_scored("d1"), _scored("d2"),
                        _scored("d3", POLICY_CAP + 0.01)], exp)
    check("a mostly-policy unit refuses the cell",
          not v["ok"] and v["policy_heavy"] == ["d3"],
          f"cap {POLICY_CAP:.0%}")

    v = cell_integrity([_scored("d1"), _scored("d2"),
                        _scored("d3", POLICY_CAP)], exp)
    check("exactly at the cap is allowed; only above it is refused", v["ok"])


def test_quarantined_fixture():
    print("\nthe real regression: the quarantined free-tier cells")
    qdir = os.path.join(ROOT, "results", "o_probe",
                        "_quarantine_quota_2026-09-10")
    paths = sorted(glob.glob(os.path.join(qdir, "run_*", "O.jsonl")))
    if not paths:
        check("quarantined fixture present", False, f"nothing under {qdir}")
        return
    rows = [json.loads(l) for p in paths
            for l in open(p, encoding="utf-8") if l.strip()]
    fabricated = [r for r in rows if _no_model_answer(r)]
    check("fabricated rows are detected from the stored attempt log",
          len(fabricated) > 0,
          f"{len(fabricated)} of {len(rows)} rows had no model answer at all")
    check("every one of them is 100% completion policy",
          all(abs(_policy_share(r) - 1.0) < 1e-9 for r in fabricated),
          "the order in these rows is entirely ours")
    heavy = [r for r in rows
             if not _no_model_answer(r) and _policy_share(r) > POLICY_CAP]
    print(f"        plus {len(heavy)} answered rows over the "
          f"{POLICY_CAP:.0%} policy cap")


def main():
    print("=" * 70)
    print(" G1b — integrity: a run with holes in it refuses to report")
    print("=" * 70)
    test_batch_gate()
    test_cell_gate()
    test_quarantined_fixture()
    print("\n" + "=" * 70)
    if _failures:
        print(f" FAILED — {len(_failures)}: {', '.join(_failures)}")
        raise SystemExit(1)
    print(" G1b PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()
