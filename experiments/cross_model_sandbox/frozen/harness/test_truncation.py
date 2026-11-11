"""
test_truncation.py — gate G1e: an answer cut off at max_tokens is a hole.

Grid pool 1 came back with 30 of 88 answers cut off at their cap: 29 empty, and
one "succeeded" O answer whose JSON list ended mid-label. The empties were
refused by the completeness gate, as designed; the cut-off one was not caught
by anything, had already been filed in the answer store, and a plain
resubmission of the empties would have been cut off in the same place. This
gate covers every piece of that:

    sizing     J at the model ceiling, O never below the floor
    fetch      records stop_reason; a max_tokens stop is an error row
    scoring    refuses a cut-off answer, including an old row with text
    store      never files a cut-off answer
    resubmit   same prompt, larger cap; nothing past the ceiling
    repair     never below the current sizing
    ledger     tripwire on the forecast, hard limit on the worst case

Run:  python harness/test_truncation.py
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
sys.path.insert(0, os.path.join(ROOT, "analysis"))

from answer_store import AnswerStore, harvest
from batch_game import (build_repair_spec, build_resubmit_spec, build_spec,
                        merge_waves, score)
from batch_submit import (IncompleteBatchError, RESERVE_MARGIN, failed_ids,
                          fetch, submit)
from cost_model_v2 import MODEL_MAX_OUTPUT, max_tokens_for
from run_ledger import HARD_LIMIT, Ledger

CELL = os.path.join(ROOT, "results", "o_probe", "random__sentence")
_failures = []


def check(name, cond, detail=""):
    if not cond:
        _failures.append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{('  — ' + detail) if detail else ''}")


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Client:
    """messages.batches with scripted results: {custom_id: (stop, text, out)}."""

    def __init__(self, script=None):
        self.script = script or {}
        self.created = []
        b = _Obj(create=self._create, retrieve=self._retrieve,
                 results=self._results)
        self.messages = _Obj(batches=b)

    def _create(self, requests):
        self.created.append(requests)
        return _Obj(id=f"fake_{len(self.created)}")

    def _retrieve(self, bid):
        return _Obj(processing_status="ended")

    def _results(self, bid):
        for cid, (stop, text, out) in self.script.items():
            msg = _Obj(content=[_Obj(type="text", text=text)], stop_reason=stop,
                       usage=_Obj(input_tokens=100, output_tokens=out))
            yield _Obj(custom_id=cid, result=_Obj(type="succeeded", message=msg))


def _row(cid, text="[]", out=100, **kw):
    return {"custom_id": cid, "result_type": "succeeded", "text": text,
            "usage": {"input_tokens": 100, "output_tokens": out}, **kw}


def _write(path, rows):
    with io.open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return path


def main():
    print("=" * 70)
    print(" G1e — an answer cut off at max_tokens is a hole, never an answer")
    print("=" * 70)
    tmp = tempfile.mkdtemp(prefix="g1e_")
    try:
        _run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n" + "=" * 70)
    if _failures:
        print(f" FAILED — {len(_failures)}: {', '.join(_failures)}")
        raise SystemExit(1)
    print(" G1e PASSED")
    print("=" * 70)


def _run(tmp):
    print("\nsizing")
    spec = build_spec([CELL], ["J", "O"], 8, 7, 42, "g1e-w0")
    side = spec["sidecar"]
    o = sorted(c for c, s in side.items() if s["game"] == "O")
    j = sorted(c for c, s in side.items() if s["game"] == "J")
    check("every J request is at the model ceiling",
          all(side[c]["max_tokens"] == MODEL_MAX_OUTPUT for c in j), f"{len(j)} pools")
    check("every O request is at the model ceiling too (D6; five were stuck at 2,048)",
          all(side[c]["max_tokens"] == MODEL_MAX_OUTPUT for c in o), f"{len(o)} documents")
    check("sizing is the ceiling at any size", max_tokens_for("O", 12) == MODEL_MAX_OUTPUT)
    check("the spec carries its forecast", spec["expected_usd"] > 0,
          f"${spec['expected_usd']:.4f}")

    print("\nfetch records why an answer stopped")
    state = {"tag": "g1e-fetch", "batch_id": "fake_x", "custom_ids": o[:3]}
    client = _Client({o[0]: ("max_tokens", '["m_0000001", "m_00', 5000),
                      o[1]: ("max_tokens", "", 5000),
                      o[2]: ("end_turn", '["m_0000001"]', 300)})
    res = fetch(state, state_dir=tmp, client=client)
    rows = {json.loads(l)["custom_id"]: json.loads(l)
            for l in io.open(os.path.join(tmp, "g1e-fetch.results.jsonl"),
                             encoding="utf-8") if l.strip()}
    check("a cut-off answer WITH text is an error row, text kept aside",
          rows[o[0]].get("error") == "TruncatedAnswerError"
          and "text" not in rows[o[0]] and rows[o[0]].get("partial_text"))
    check("both cut-off answers count as failed; the finished one does not",
          set(failed_ids(os.path.join(tmp, "g1e-fetch.results.jsonl")))
          == {o[0], o[1]} and res["counts"]["truncated"] == 2)
    check("stop_reason is on every row",
          all("stop_reason" in r for r in rows.values()))

    print("\nscoring refuses an OLD row that ran into its cap with text")
    clean = [_row(c) for c in side]
    legacy = [dict(r) for r in clean]
    legacy[[r["custom_id"] for r in legacy].index(o[0])].update(
        text='["m_000', usage={"input_tokens": 1, "output_tokens": side[o[0]]["max_tokens"]})
    f_legacy = _write(os.path.join(tmp, "legacy.jsonl"), legacy)
    try:
        merge_waves([(spec, [f_legacy])])
        check("a cut-off 'succeeded' answer is refused", False, "it merged")
    except IncompleteBatchError as e:
        check("a cut-off 'succeeded' answer is refused", "cut off" in str(e))

    print("\nthe answer store never files a cut-off answer")
    store = AnswerStore(path=None)
    added = harvest(store, spec, [f_legacy])
    check("everything but the cut-off answer is filed",
          added == len(side) - 1, f"{added} of {len(side)}")
    store2 = AnswerStore(os.path.join(tmp, "store.jsonl"))
    harvest(store2, spec, [_write(os.path.join(tmp, "clean.jsonl"), clean)])
    k = next(iter(store2.rows))
    check("drop() removes an entry and records why",
          store2.drop(k, "test") and k not in AnswerStore(store2.path).rows
          and os.path.exists(store2.path + ".removed.jsonl"))

    print("\nresubmit: same prompt, larger cap, nothing past the ceiling")
    mixed = [dict(r) for r in clean]
    idx = {r["custom_id"]: i for i, r in enumerate(mixed)}
    mixed[idx[o[1]]] = _row(o[1], text="", out=2048, error="ZeroAnswerError")
    side_small = {**side, o[1]: {**side[o[1]], "max_tokens": 2048},
                  o[0]: {**side[o[0]], "max_tokens": 5000}}
    spec_small = {**spec, "sidecar": side_small}
    mixed[idx[o[2]]] = {"custom_id": o[2], "result_type": "errored",
                        "error": "overloaded"}
    mixed[idx[j[0]]] = _row(j[0], text="", out=MODEL_MAX_OUTPUT,
                            error="TruncatedAnswerError", stop_reason="max_tokens")
    mixed[idx[o[0]]] = _row(o[0], text='["m_000', out=5000)     # old row, cut at a 5k cap
    f_mixed = _write(os.path.join(tmp, "mixed.jsonl"), mixed)
    rs = build_resubmit_spec(spec_small, [f_mixed], "g1e-rs1")
    got = set(rs["sidecar"])
    check("the cut-off, empty and errored requests are resubmitted",
          got == {o[0], o[1], o[2]}, str(sorted(got)))
    check("one cut off AT the ceiling is not sent again",
          rs["at_ceiling"] == [j[0]])
    by = {r["unit"]: r for r in rs["requests"]}
    orig = {r["unit"]: r for r in spec["requests"]}
    check("every resubmitted prompt is byte-identical",
          all(by[u]["prompt"] == orig[u]["prompt"] for u in by))
    check("a cut-off request gets a larger cap than the one it hit",
          rs["sidecar"][o[1]]["max_tokens"] > 2048
          and rs["sidecar"][o[1]]["cut_off_at"] == 2048,
          f"2,048 -> {rs['sidecar'][o[1]]['max_tokens']:,}")
    check("an errored request keeps its cap",
          rs["sidecar"][o[2]]["max_tokens"] == side[o[2]]["max_tokens"])
    again = _row(o[0], text="", out=MODEL_MAX_OUTPUT, error="TruncatedAnswerError",
                 stop_reason="max_tokens")
    rs2 = build_resubmit_spec(spec, [_write(os.path.join(tmp, "again.jsonl"),
                                            [again])], "g1e-rs2")
    check("an answer that exhausted 128k is never re-asked (D6)",
          o[0] not in rs2["sidecar"] and o[0] in rs2["at_ceiling"])

    print("\nD6: a call that exhausts 128k is a non-completion, not a hole")

    def valid_answer(s):
        labs = list(s["alias_map"])
        if s["game"] == "O":
            return json.dumps(labs)
        return json.dumps([labs[i::s["n_records"]] for i in range(s["n_records"])])

    good = [_row(c, text=valid_answer(s), stop_reason="end_turn") for c, s in side.items()]
    gi = {r["custom_id"]: i for i, r in enumerate(good)}
    good[gi[j[0]]] = _row(j[0], text="", out=MODEL_MAX_OUTPUT,
                          error="TruncatedAnswerError", stop_reason="max_tokens")
    verdict = score([(spec, [_write(os.path.join(tmp, "rbnc.jsonl"), good)])],
                    os.path.join(tmp, "scored_rb"))
    cell = side[j[0]]["cell"]
    rb_path = os.path.join(tmp, "scored_rb", cell, "J.rbnc.jsonl")
    rb = [json.loads(l) for l in io.open(rb_path, encoding="utf-8") if l.strip()]
    written = [json.loads(l)["unit"] for l in io.open(
        os.path.join(tmp, "scored_rb", cell, "J.jsonl"), encoding="utf-8") if l.strip()]
    check("scoring accepts it and the cell is NOT refused for it",
          "J" not in verdict[cell], str(sorted(verdict[cell])))
    check("it is recorded as a resource-bounded non-completion",
          [r["unit"] for r in rb] == [side[j[0]]["unit"]])
    check("it is not scored: no F1 = 0 row is written",
          side[j[0]]["unit"] not in written)
    bad = list(good)
    bad[gi[o[3]]] = _row(o[3], text="no list here", stop_reason="end_turn")
    rp2 = build_repair_spec([(spec, [_write(os.path.join(tmp, "rb2.jsonl"), bad)])],
                            1, 1, "g1e-r2")
    bases = {s["base_cid"] for s in rp2["sidecar"].values()}
    check("the repair round never re-asks it; a malformed, unexhausted answer is re-asked",
          j[0] not in bases and o[3] in bases, str(sorted(bases)))

    print("\nrepair always goes out at the model ceiling")
    garbage = [_row(c, text="no list here") for c in side]
    f_g = _write(os.path.join(tmp, "garbage.jsonl"), garbage)
    rp = build_repair_spec([(spec_small, [f_g])], 1, 1, "g1e-r1")
    check("every repair request is at the model ceiling, whatever its round-0 cap",
          rp["requests"] and all(r["max_tokens"] == MODEL_MAX_OUTPUT
                                 for r in rp["requests"]),
          f"{len(rp['requests'])} requests")

    print("\nledger: tripwire on the forecast, hard limit on the worst case")
    led = Ledger(os.path.join(tmp, "ledger.json"), max_spend=120.0)
    ok, msg = led.check_spend(5.0, worst_usd=HARD_LIMIT + 1)
    check("a submission that could breach the hard limit is refused",
          not ok and "hard limit" in msg)
    ok, _ = led.check_spend(5.0, worst_usd=50.0)
    check("the same forecast with a survivable worst case is allowed", ok)
    sub = {"tag": "g1e-sub", "model": "m",
           "requests": [{"cell": "c", "game": "O", "unit": "u1",
                         "prompt": "x" * 400, "max_tokens": 128000}]}
    submit(sub, state_dir=tmp, client=_Client(), ledger=led, expected_usd=0.01)
    check("the tripwire reserves RESERVE_MARGIN x the forecast, not the worst case",
          abs(led.step("g1e-sub")["projected_usd"] - RESERVE_MARGIN * 0.01) < 1e-9,
          f"${led.step('g1e-sub')['projected_usd']:.4f}")


if __name__ == "__main__":
    main()
