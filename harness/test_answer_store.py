"""
test_answer_store.py — gate G1c: a paid answer is never paid for twice, and
never lost.

The test run and the real run ask many identical questions. Every succeeded
answer is filed under its exact (model, prompt); a later identical request is
filled from the store for $0 instead of being sent. Driven through the same fake
provider as G1, so it exercises the real submit / fetch / merge / score path:

    identical request     reused, not submitted, scores identically, costs 0
    partial overlap       only the new requests are sent
    different prompt      never reused (a changed seed changes every prompt)
    failed request        never filed -- a hole is asked again, not "reused"

Run:  python harness/test_answer_store.py
"""

import io
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "adversaries"))

from answer_store import AnswerStore, harvest, split_by_store
from batch_game import build_resubmit_spec, build_spec, merge_waves, score
from batch_submit import fetch, results_cost, results_path, submit
from joint_game import build_units, score_row
from run_ledger import Ledger
from test_batch_rehearsal import FakeClient, Oracle

_failures = []


def check(name, cond, detail=""):
    if not cond:
        _failures.append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  — ' + detail) if detail else ''}")


CELL_A = os.path.join(ROOT, "results", "o_probe", "random__sentence")
CELL_B = os.path.join(ROOT, "results", "o_probe", "llm-cut__llm-decides")


def wave(client, oracle, store, spec, state_dir, led, tmp):
    """split -> submit what is left -> fetch -> harvest. Returns (files, n_sent)."""
    oracle.learn(spec)
    reused_path = os.path.join(tmp, f"{spec['tag']}_reused.jsonl")
    to_send, _n = split_by_store(store, spec, reused_path)
    files = [reused_path]
    if to_send["requests"]:
        state = submit(to_send, state_dir=state_dir, client=client, ledger=led)
        fetch(state, state_dir=state_dir, client=client, ledger=led)
        files.append(results_path(state_dir, spec["tag"]))
    harvest(store, spec, files)
    return files, len(to_send["requests"])


def f1s(out_root, cell_dir):
    cell = os.path.basename(cell_dir)
    _, _, key, pool_truth = build_units(cell_dir, 8, 7, 42)
    vals = []
    for g in ("O", "J"):
        p = os.path.join(out_root, cell, f"{g}.jsonl")
        for line in io.open(p, encoding="utf-8"):
            if line.strip():
                r = score_row(json.loads(line), key, pool_truth)
                vals.append(round(r.get("tau", r.get("joint_f1", -9)), 12))
    return vals


def main():
    print("=" * 70)
    print(" G1c — the answer store: never pay twice, never lose an answer")
    print("=" * 70)
    tmp = tempfile.mkdtemp(prefix="g1c_")
    try:
        state_dir = os.path.join(tmp, "batches")
        led = Ledger(os.path.join(tmp, "ledger.json"), max_spend=120.0)
        store = AnswerStore(os.path.join(tmp, "answer_store.jsonl"))

        print("\nthe test run: one cell, everything sent and filed")
        spec_t = build_spec([CELL_A], ["O", "J"], 8, 7, 42, tag="test-w0")
        oracle = Oracle(spec_t["build"])
        client = FakeClient(oracle)
        files_t, sent_t = wave(client, oracle, store, spec_t, state_dir, led, tmp)
        n = len(spec_t["requests"])
        check("every answer the test paid for is filed",
              sent_t == n and len(store) == n, f"{len(store)} of {n} filed")
        score([(spec_t, files_t)], os.path.join(tmp, "s_test"))
        cost_t = results_cost(files_t)

        print("\nthe real run asks the same questions under different ids")
        spec_r = build_spec([CELL_A], ["O", "J"], 8, 7, 42, tag="real-w0")
        files_r, sent_r = wave(client, oracle, store, spec_r, state_dir, led, tmp)
        check("identical requests are filled from the store, none sent",
              sent_r == 0, f"{sent_r} sent")
        check("reused answers cost nothing", results_cost(files_r) == 0.0,
              f"test paid ${cost_t:.4f}, real run paid ${results_cost(files_r):.4f}")
        score([(spec_r, files_r)], os.path.join(tmp, "s_real"))
        check("and score exactly as the originals did",
              f1s(os.path.join(tmp, "s_real"), CELL_A)
              == f1s(os.path.join(tmp, "s_test"), CELL_A))
        rows = [json.loads(l) for l in io.open(files_r[0], encoding="utf-8") if l.strip()]
        check("every reused row says where it came from",
              rows and all(r["reused_from"].startswith("test-w0/") for r in rows))

        print("\npartial overlap: a bigger run sends only what is new")
        spec_b = build_spec([CELL_A, CELL_B], ["O", "J"], 8, 7, 42, tag="big-w0")
        _, sent_b = wave(client, oracle, store, spec_b, state_dir, led, tmp)
        check("only the new cell's requests are sent",
              sent_b == len(spec_b["requests"]) - n,
              f"{sent_b} sent of {len(spec_b['requests'])}")

        print("\na different prompt is never reused")
        spec_s = build_spec([CELL_A], ["O", "J"], 8, 7, 43, tag="seed43-w0")
        to_send, reused = split_by_store(
            store, spec_s, os.path.join(tmp, "seed43_reused.jsonl"))
        check("a changed masking seed changes every prompt, so nothing matches",
              reused == 0 and len(to_send["requests"]) == len(spec_s["requests"]))

        print("\na failed request is never filed as an answer")
        store2 = AnswerStore(os.path.join(tmp, "store2.jsonl"))
        spec_f = build_spec([CELL_B], ["O"], 8, 7, 42, tag="fail-w0")
        o2 = Oracle(spec_f["build"])
        c2 = FakeClient(o2)
        bad = sorted(spec_f["sidecar"])[:2]
        for cid in bad:
            o2.faults[(cid, 0)] = "errored"
        files_f, _ = wave(c2, o2, store2, spec_f, state_dir, led, tmp)
        check("only the answered requests are filed",
              len(store2) == len(spec_f["requests"]) - 2,
              f"{len(store2)} filed, 2 errored")
        rs = build_resubmit_spec(spec_f, files_f, "fail-w0-rs1")
        check("the errored requests are the ones asked again",
              sorted(rs["sidecar"]) == bad)
        try:
            merge_waves([(spec_f, files_f)])
            check("the wave is still refused until they are", False)
        except Exception as e:
            check("the wave is still refused until they are",
                  type(e).__name__ == "IncompleteBatchError")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 70)
    if _failures:
        print(f" FAILED — {len(_failures)}: {', '.join(_failures)}")
        raise SystemExit(1)
    print(" G1c PASSED")
    print("=" * 70)


if __name__ == "__main__":
    main()
