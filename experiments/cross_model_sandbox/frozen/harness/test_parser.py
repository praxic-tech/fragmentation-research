"""
test_parser.py — gate G1f: a complete answer is never scored as unparseable.

Grid pool 1, random__token-window, prose_0383: the model returned all 56 labels
in a ```json fence, after prose that said "Case 1 [35-year-old with TTTS/band
complication]". The old parser took the first "[" to the last "]", hit the
prose bracket, and the unit was scored as having no model answer -- its cell
was refused, and the protocol would have paid to re-ask a question already
answered. A scoring bug, so it is fixed in the scorer and nothing is re-bought.

Run:  python harness/test_parser.py
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "adversaries"))

from llm_adversary import extract_json_array

_failures = []


def check(name, cond, detail=""):
    if not cond:
        _failures.append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  — ' + detail) if detail else ''}")


def parses_to(text, want):
    try:
        return extract_json_array(text) == want
    except ValueError:
        return False


def refuses(text):
    try:
        extract_json_array(text)
        return False
    except ValueError:
        return True


def main():
    print("=" * 70)
    print(" G1f — the answer parser")
    print("=" * 70)
    ans = ["m_0000002", "m_0000000", "m_0000001"]
    check("a bare array", parses_to('["m_0000002", "m_0000000", "m_0000001"]', ans))
    check("a fenced array", parses_to('```json\n["m_0000002","m_0000000","m_0000001"]\n```', ans))
    check("THE POOL-1 CASE: bracketed prose before a fenced answer",
          parses_to('Case 1 [35-year-old with TTTS] -> Case 2 [32-year-old].\n\n'
                    '```json\n["m_0000002", "m_0000000", "m_0000001"]\n```', ans))
    check("a stray citation before an unfenced answer",
          parses_to('Fragment [1] opens it. Order: ["m_0000002", "m_0000000", "m_0000001"]', ans))
    check("prose after the answer",
          parses_to('["m_0000002", "m_0000000", "m_0000001"]\nThe [intro] comes first.', ans))
    groups = [["m_0000001", "m_0000000"], ["m_0000002"]]
    check("a J answer: the outer list, not an inner group",
          parses_to('Two records:\n[["m_0000001", "m_0000000"], ["m_0000002"]]', groups))
    check("no array at all is refused", refuses("I would put the history first."))
    check("an answer cut off mid-list is refused",
          refuses('```json\n["m_0000002", "m_0000000", "m_00'))
    check("empty and None are refused", refuses("") and refuses(None))
    print("\n" + "=" * 70)
    if _failures:
        print(f" FAILED — {len(_failures)}: {', '.join(_failures)}")
        raise SystemExit(1)
    print(" G1f PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()
