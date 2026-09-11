"""
test_headline_guard.py — gate G1d: the 46 headline pools cannot be requested.

docs/RUN_DECISIONS.md D2 keeps the headline pools completely untouched until the
headline run, and predeclared check #1 of the first paid slice requires that no
request contains a headline document. A promise is not a check, so build_spec
refuses to build such a request.

Run:  python harness/test_headline_guard.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "adversaries"))

from batch_game import build_spec, headline_docs, load_frame

_failures = []


def check(name, cond, detail=""):
    if not cond:
        _failures.append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  — ' + detail) if detail else ''}")


def main():
    print("=" * 70)
    print(" G1d — the untouched headline pools cannot be requested")
    print("=" * 70)
    pools = os.path.join(ROOT, "data", "pools", "pools.json")
    grid_ids = os.path.join(ROOT, "data", "pools", "linkage_grid.json")
    head = headline_docs()
    grid = {m for _p, ms in load_frame(pools, grid_ids) for m in ms}
    print("\nthe two sets")
    check("46 headline pools = 322 documents", len(head) == 322, str(len(head)))
    check("25 grid pools = 175 documents", len(grid) == 175, str(len(grid)))
    check("headline and grid documents are disjoint", not (head & grid))

    print("\nthe guard refuses, and only when it should")
    probe = os.path.join(ROOT, "results", "o_probe", "random__sentence")
    try:
        build_spec([probe], ["O", "J"], 8, 7, 42, "g", forbid_docs=head)
        check("a spec touching headline documents is refused", False, "it built")
    except ValueError as e:
        check("a spec touching headline documents is refused",
              "headline" in str(e), str(e)[:60] + "...")
    spec = build_spec([probe], ["O", "J"], 8, 7, 42, "g", forbid_docs={"prose_9999"})
    check("an unrelated forbidden set does not block the build",
          len(spec["requests"]) > 0, f"{len(spec['requests'])} requests")
    check("the guard is recorded in the spec",
          spec["build"]["forbidden_docs"] == 1)

    print("\n" + "=" * 70)
    if _failures:
        print(f" FAILED — {len(_failures)}: {', '.join(_failures)}")
        raise SystemExit(1)
    print(" G1d PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()
