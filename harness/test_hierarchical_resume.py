"""
test_hierarchical_resume.py — gate G2b: a quota stop costs time, never evidence.

The free-tier rehearsal of the hierarchical attacker ran 38 of its ~41 pair
batches, hit the provider limit, correctly refused to score the pool -- and
threw away every one of the ~570 pairs it had already paid (in quota) to have
answered, because answers were only written once the whole pool finished. It
had also given up on the first quota message, which is usually a per-minute
burst rather than an exhausted budget.

On the paid run this attacker calls the model directly at full price, so both
behaviours would have cost real money. This gate drives score_pairs_llm with a
fake model that fails on command:

    a burst          the batch cools down and is asked again; nothing lost
    a hard stop      NoModelAnswer after the cool-down budget, with every
                     answer so far already on disk
    a resume         only the unanswered pairs are asked; the finished
                     evidence is IDENTICAL to an uninterrupted run
    a wrong folder   resuming into another run's answers is refused

Run:  python harness/test_hierarchical_resume.py
"""

import os
import random
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "adversaries"))

from hierarchical import (PairCache, check_run_meta, score_pairs_llm,
                          top_k_candidates)
from repair import NoModelAnswer

_failures = []


def check(name, cond, detail=""):
    if not cond:
        _failures.append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  — ' + detail) if detail else ''}")


TOPICS = {
    "cardiac": "chest pain angina troponin ecg stent coronary artery infarct",
    "renal": "creatinine dialysis nephritis kidney urea glomerular renal biopsy",
    "neuro": "seizure cortex mri lesion aphasia neurology stroke thrombolysis",
    "hepatic": "jaundice bilirubin cirrhosis hepatic ascites portal liver enzyme",
}


def make_pool(frags_per_doc=6, seed=1):
    rng = random.Random(seed)
    texts, n = {}, 0
    for topic, words in TOPICS.items():
        for p in range(frags_per_doc):
            n += 1
            texts[f"m_{n:07d}"] = (" ".join(rng.sample(words.split(), 5))
                                   + f" step {p} of the {topic} course")
    return texts


class FakeCall:
    """Stands in for call_model. Raises the quota message on command."""

    def __init__(self, fail_from=None, fail_times=0):
        self.n = 0
        self.fail_from = fail_from
        self.fail_times = fail_times
        self.failed = 0
        self.pairs_asked = 0

    def __call__(self, client, prompt, model, temperature=None, max_tokens=None):
        self.n += 1
        if (self.fail_from is not None and self.n >= self.fail_from
                and self.failed < self.fail_times):
            self.failed += 1
            raise RuntimeError("Too many transient failures - try again later.")
        ids = [int(x) for x in re.findall(r"pair_id (\d+)", prompt)]
        self.pairs_asked += len(ids)
        return [{"pair_id": i, "same": 0.9, "before": 0.7} for i in ids]


def run(pairs, texts, cache, call, retries=6):
    return score_pairs_llm(None, pairs, texts, "fake-model", seed=7,
                           pairs_per_call=5, cache=cache, call=call,
                           quota_cooldown=0.0, quota_retries=retries)


def main():
    print("=" * 70)
    print(" G2b — hierarchical attacker: a quota stop costs time, never evidence")
    print("=" * 70)
    texts = make_pool()
    pairs, _ = top_k_candidates(sorted(texts), texts, k=4)
    n = len(pairs)
    tmp = tempfile.mkdtemp(prefix="g2b_")
    try:
        print(f"\n{len(texts)} fragments, {n} candidate pairs, 5 pairs per call")

        print("\nuninterrupted reference run")
        path_a = os.path.join(tmp, "a", "pairs.jsonl")
        os.makedirs(os.path.dirname(path_a))
        m_a, w_a, rows_a, tel_a = run(pairs, texts, PairCache(path_a), FakeCall())
        on_disk = sum(1 for l in open(path_a, encoding="utf-8") if l.strip())
        check("every answered pair is on disk as it arrives",
              len(rows_a) == n and on_disk == n, f"{on_disk} of {n} written")

        print("\na rate-limit burst is ridden out, not fatal")
        burst = FakeCall(fail_from=2, fail_times=2)
        _, _, rows_b, _ = run(pairs, texts, PairCache(), burst, retries=3)
        check("two quota errors on one batch are cooled down and retried",
              len(rows_b) == n and burst.failed == 2,
              f"{len(rows_b)} of {n} answered, {burst.failed} cool-downs")

        print("\na hard stop keeps everything answered so far")
        path_c = os.path.join(tmp, "c", "pairs.jsonl")
        os.makedirs(os.path.dirname(path_c))
        dead = FakeCall(fail_from=3, fail_times=10 ** 6)
        try:
            run(pairs, texts, PairCache(path_c), dead, retries=2)
            check("a persistent quota stop raises NoModelAnswer", False,
                  "the run scored anyway")
        except NoModelAnswer as e:
            check("a persistent quota stop raises NoModelAnswer",
                  "cool-downs" in str(e), str(e)[:60] + "...")
        saved = len(PairCache(path_c).rows)
        check("the two batches answered before the stop are saved, not lost",
              saved == 10, f"{saved} pairs saved")

        print("\nresume: only the missing pairs are asked")
        again = FakeCall()
        m_r, w_r, rows_r, tel_r = run(pairs, texts, PairCache(path_c), again)
        check("the resumed run asks exactly the unanswered pairs",
              again.pairs_asked == n - saved,
              f"asked {again.pairs_asked}, skipped {tel_r['resumed_pairs']}")
        check("the finished evidence is identical to an uninterrupted run",
              m_r == m_a and w_r == w_a and len(rows_r) == n)
        check("the integrity count covers resumed pairs",
              tel_r["requested_pairs"] == n and tel_r["scored_pairs"] == n,
              f"{tel_r['scored_pairs']} of {tel_r['requested_pairs']}")

        print("\nresuming into a different run's folder is refused")
        out = os.path.join(tmp, "meta")
        meta = {"cell": "c", "docs": 7, "seed": 42, "k": 5, "model": "x",
                "alias_sha": "abc"}
        check("a fresh folder records its run", check_run_meta(out, meta))
        check("the same run resumes", check_run_meta(out, dict(meta)) is False)
        try:
            check_run_meta(out, dict(meta, seed=43))
            check("a different run is refused", False, "it resumed")
        except ValueError as e:
            check("a different run is refused", "seed" in str(e),
                  str(e)[:60] + "...")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 70)
    if _failures:
        print(f" FAILED — {len(_failures)}: {', '.join(_failures)}")
        raise SystemExit(1)
    print(" G2b PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()
