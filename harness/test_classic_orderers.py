"""
test_classic_orderers.py — gate G5b: the classic Jaccard orderers can only
score what their evidence supports, and give the same answer in every process.

Two defects, both measured on the prose corpus before this gate existed
(docs/RUN_DECISIONS.md D1):

  leakage       Game O handed Greedy and MST the raw fragment ids in true
                order. Word-bigram Jaccard is 0 for 86.7% of pairs, so ties
                decided almost everything, and ties went to the raw id or the
                list position. Greedy +0.3232 and MST +0.7044 as run; -0.0304 and
                -0.0175 masked and shuffled.
  hash seeds    MST iterated Python sets, whose order changes per process:
                0.704416 / 0.704440 / 0.704190 for three PYTHONHASHSEEDs.

Run:  python harness/test_classic_orderers.py
"""

import json
import os
import random
import re
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import harness as H
from orderers import greedy_nn_order, mst_order
from scoring import score_ordering

_failures = []


def check(name, cond, detail=""):
    if not cond:
        _failures.append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  — ' + detail) if detail else ''}")


def evidence_free(n_docs=150, n_frag=10):
    """Every fragment is made of unique words: Jaccard is 0 for EVERY pair.

    An orderer with no evidence must score at chance here. Ids are written in
    true order, exactly as the real fragment file is.
    """
    docs, text = {}, {}
    for d in range(n_docs):
        order = []
        for p in range(n_frag):
            fid = f"prose_{d:04d}_frag_{p:03d}"
            text[fid] = " ".join(f"w{d}x{p}x{k}" for k in range(8))
            order.append(fid)
        docs[f"prose_{d:04d}"] = order
    return docs, text


def mean_tau(docs, text, order_fn):
    taus = [score_ordering(order_fn(ids, text), ids)["tau"] for ids in docs.values()]
    return statistics.mean(t for t in taus if t == t)


def test_leak_and_fix():
    print("\nevidence-free input: no evidence must mean no ordering")
    docs, text = evidence_free()
    for name, fn in (("Greedy", greedy_nn_order), ("MST", mst_order)):
        legacy = mean_tau(docs, text, fn)
        fixed = mean_tau(docs, text,
                         lambda ids, t, fn=fn: H._masked_shuffled_order(fn, ids, t, 42))
        check(f"{name}: the superseded path scores from ids alone (documents the leak)",
              legacy > 0.5, f"tau {legacy:+.3f} with zero evidence")
        check(f"{name}: masked and shuffled, it scores at chance",
              abs(fixed) < 0.1, f"tau {fixed:+.3f}")


def test_only_masked_labels_reach_the_orderer():
    print("\nthe orderer never sees a raw id or the true order")
    docs, text = evidence_free(n_docs=40)
    seen, in_true_order = [], 0
    for ids in docs.values():
        def spy(shown, ltext):
            seen.extend(shown)
            return list(shown)
        guess = H._masked_shuffled_order(spy, ids, text, 42)
        in_true_order += guess == ids
    check("every label passed in is a mask, never a fragment id",
          all(re.fullmatch(r"m_\d{7}", x) for x in seen), f"{len(seen)} labels")
    check("presentation order is shuffled, not the file's true order",
          in_true_order <= 1, f"{in_true_order} of {len(docs)} came back in true order")


def test_determinism():
    print("\nsame input, same answer -- across seeds and across processes")
    docs, text = evidence_free(n_docs=20)
    a = [H._masked_shuffled_order(mst_order, ids, text, 42) for ids in docs.values()]
    b = [H._masked_shuffled_order(mst_order, ids, text, 42) for ids in docs.values()]
    c = [H._masked_shuffled_order(mst_order, ids, text, 43) for ids in docs.values()]
    check("the same run seed gives identical orders", a == b)
    check("a different run seed changes the presentation", a != c)

    code = (
        "import json, sys; sys.path.insert(0, r'" + HERE + "');"
        "import harness as H; from orderers import mst_order, greedy_nn_order;"
        "from test_classic_orderers import evidence_free;"
        "d, t = evidence_free(n_docs=30);"
        "print(json.dumps([[H._masked_shuffled_order(f, i, t, 42) for i in d.values()]"
        " + [f(i, t) for i in d.values()] for f in (mst_order, greedy_nn_order)]))"
    )
    outs = []
    for s in ("0", "1", "2"):
        env = dict(os.environ, PYTHONHASHSEED=s)
        r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                           text=True, env=env, cwd=HERE)
        outs.append(r.stdout.strip() if r.returncode == 0 else f"ERR {r.stderr[-200:]}")
    check("identical output under PYTHONHASHSEED 0, 1 and 2",
          outs[0] == outs[1] == outs[2] and not outs[0].startswith("ERR"),
          outs[0][:40] if outs[0].startswith("ERR") else "MST and Greedy, masked and legacy")


def test_real_corpus():
    print("\nreal corpus: masked orderers sit at chance on the first 100 prose documents")
    frags = [json.loads(l) for l in open(os.path.join(ROOT, "data", "prose", "prose_fragments.jsonl"),
                                         encoding="utf-8") if l.strip()]
    key = {json.loads(l)["record_id"]: json.loads(l)["order"]
           for l in open(os.path.join(ROOT, "data", "prose", "prose_answer_key.jsonl"),
                         encoding="utf-8") if l.strip()}
    text = {f["fragment_id"]: f["text"] for f in frags}
    by = {}
    for f in frags:
        by.setdefault(f["record_id"], []).append(f["fragment_id"])
    rids = list(by)[:100]
    for name, fn in (("Jaccard-Greedy", greedy_nn_order), ("Jaccard-MST", mst_order)):
        taus = [score_ordering(H._masked_shuffled_order(fn, by[r], text, 42), key[r])["tau"]
                for r in rids]
        m = statistics.mean(t for t in taus if t == t)
        check(f"{name}: mean tau near 0", abs(m) < 0.1, f"{m:+.4f}")


def main():
    print("=" * 70)
    print(" G5b — classic Jaccard orderers: no leakage, no hash-seed drift")
    print("=" * 70)
    test_leak_and_fix()
    test_only_masked_labels_reach_the_orderer()
    test_determinism()
    test_real_corpus()
    print("\n" + "=" * 70)
    if _failures:
        print(f" FAILED — {len(_failures)}: {', '.join(_failures)}")
        raise SystemExit(1)
    print(" G5b PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()
