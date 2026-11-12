"""Fault-injection tests for the runner. NO MODEL CALLS.

    python -I work/runner/test_runner.py

Each case runs the runner against the fake llama-server of replay_sonnet.py
(Sonnet's converted answers) with one fault injected, in its own temp directory:

  restart        crash mid-call -> rerun skips written rows, resends the interrupted
                 request as its first attempt, logs the restart; numbers unchanged
  control_token  a harmony token in the answer text -> wave stops, no row written,
                 failure recorded; rerun refused until --resume-after-check-failure
  prompt_tokens  reported prompt tokens != tokenizer count -> stop
  short_length   finish "length" below the budget -> stop
  render_hash    stored render hash differs -> stop BEFORE the call
  no_fit         prompt + budget > context -> stop BEFORE the call
  logged_prompt  server's logged prompt differs from the render -> stop
  slots_params   /slots shows a sampler value other than the one sent -> stop
  ceiling        an answer stopped at the budget -> D6: not resent, not repaired,
                 recorded in J.rbnc.jsonl
  zero_answer    empty answer (all reasoning) -> ZeroAnswerError row, resent once (D4)
  repair_transport  a repair call fails in transport -> its own -rs1 resend
"""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import replay_sonnet as RS                                       # noqa: E402
import runner as R                                               # noqa: E402
from batch_submit import _latest_rows                            # noqa: E402

SPEC = json.load(open(R.HEADLINE_SPEC, encoding="utf-8"))
P3 = SPEC["requests"][2]["prompt"]               # the third base request
CID3 = "prose__J__" + SPEC["requests"][2]["unit"].replace("_", "-")


def setup():
    tmp = tempfile.mkdtemp(prefix="runner_test_")
    cfg = RS.replay_cfg(tmp)
    return tmp, cfg


def fresh(tmp, cfg, oracle=None, **kw):
    _spec, answers, tokens, rows, _rp = oracle or RS.sonnet_oracle(cfg)
    server = RS.FakeLlamaServer(cfg, answers, tokens)
    return server, RS.make_runner(tmp, server, cfg, **kw), rows


def stops(fn):
    try:
        fn()
    except SystemExit as e:
        return str(e)
    raise AssertionError("expected the wave to stop")


def base_rows(tmp, tag="final-headlineJ"):
    return _latest_rows(os.path.join(tmp, "raw", f"{tag}.results.jsonl"))


def check_failures(tmp):
    p = os.path.join(tmp, "raw", "final-headlineJ.check_failures.jsonl")
    return [json.loads(x) for x in open(p, encoding="utf-8")] if os.path.exists(p) else []


def finish_and_match(tmp, cfg, oracle=None, **kw):
    server, runner, rows = fresh(tmp, cfg, oracle, **kw)
    verdict = runner.run()
    assert not any(verdict.values()), verdict
    RS.compare_rows(tmp, rows)
    _n, got = RS.headline_numbers(os.path.join(tmp, "results"), SPEC)
    assert (round(got["F1_J_mean"], 4), round(got["F1_L_mean"], 4), round(got["q_mean"], 4)) == \
        (0.7225, 0.8817, 0.8206), got
    return server


def tamper_once(server, prompt, fn):
    state = {"done": False}

    def t(p, resp):
        if p == prompt and not state["done"]:
            state["done"] = True
            return fn(resp)
        return resp
    server.tamper = t


def case_restart(tmp, cfg):
    oracle = RS.sonnet_oracle(cfg)          # the same answers before and after the crash
    server, runner, _ = fresh(tmp, cfg, oracle)
    server.fail_at = 10
    try:
        runner.run()
        raise AssertionError("expected the simulated crash")
    except KeyboardInterrupt:
        pass
    assert len(base_rows(tmp)) == 9, len(base_rows(tmp))
    interrupted = server.sent[-1]
    server2 = finish_and_match(tmp, cfg, oracle)
    assert server2.sent[0] == interrupted, "interrupted request not sent first on restart"
    log = open(os.path.join(tmp, "run.log"), encoding="utf-8").read()
    assert "RESTART final-headlineJ: 9 rows already present, 37 requests to send" in log
    return "crash at call 10 -> 9 rows kept, interrupted request resent as first attempt, restart logged, numbers equal"


def _stop_then_resume(tmp, cfg, mutate, expect):
    server, runner, _ = fresh(tmp, cfg)
    tamper_once(server, P3, mutate)
    msg = stops(runner.run)
    assert expect in msg, msg
    assert len(base_rows(tmp)) == 2 and CID3 not in base_rows(tmp)
    assert len(check_failures(tmp)) == 1 and "response" in check_failures(tmp)[0]
    refused = stops(lambda: fresh(tmp, cfg)[1].run())
    assert "unreviewed check failure" in refused, refused
    finish_and_match(tmp, cfg, resume_after_check_failure=True)
    log = open(os.path.join(tmp, "run.log"), encoding="utf-8").read()
    assert "resumed after 1 check failure(s) on the user's instruction" in log
    return f"stopped ({msg.split(': ', 2)[-1][:50]}...), no row, rerun refused, resumed on flag, numbers equal"


def case_control_token(tmp, cfg):
    def leak(r):
        r["choices"][0]["message"]["content"] = "<|channel|>final" + r["choices"][0]["message"]["content"]
        return r
    return _stop_then_resume(tmp, cfg, leak, "control tokens")


def case_prompt_tokens(tmp, cfg):
    def off(r):
        r["usage"] = {**r["usage"], "prompt_tokens": r["usage"]["prompt_tokens"] - 1}
        return r
    return _stop_then_resume(tmp, cfg, off, "prompt_tokens")


def case_short_length(tmp, cfg):
    def short(r):
        r["choices"][0]["finish_reason"] = "length"
        r["usage"] = {**r["usage"], "completion_tokens": 5000}
        return r
    return _stop_then_resume(tmp, cfg, short, "not at the budget")


def case_slots_params(tmp, cfg):
    server, runner, _ = fresh(tmp, cfg)
    orig = server.slots
    server.slots = lambda: [{**orig()[0], "params": {**orig()[0]["params"], "min_p": 0.05}}]
    msg = stops(runner.run)
    assert "/slots params differ" in msg and len(base_rows(tmp)) == 0, msg
    return "server-side min_p 0.05 vs sent 0.0 -> stopped after the first call, no row"


def case_logged_prompt(tmp, cfg):
    server, runner, _ = fresh(tmp, cfg)
    chat = server.chat

    def chat2(body):
        resp = chat(body)
        with open(os.path.join(cfg["log_prompts_dir"], f"{server.n_log:012d}.txt"), "a",
                  encoding="utf-8") as fh:
            fh.write("x")
        return resp
    server.chat = chat2
    msg = stops(runner.run)
    assert "differs from the render" in msg and len(base_rows(tmp)) == 0, msg
    return "logged prompt one char longer -> stopped, no row"


def case_render_hash(tmp, cfg):
    h = json.load(open(cfg["render_hashes"], encoding="utf-8"))
    h["rows"][2]["sha256"] = "0" * 64
    json.dump(h, open(cfg["render_hashes"], "w", encoding="utf-8"))
    server, runner, _ = fresh(tmp, cfg)
    msg = stops(runner.run)
    assert "render SHA-256" in msg and len(server.sent) == 2, (msg, len(server.sent))
    return "third render hash wrong -> stopped before its call (2 calls made)"


def case_no_fit(tmp, cfg):
    server, runner, _ = fresh(tmp, cfg)
    tok = server.tokens
    server.tokens = lambda p: 40000 if p == P3 else tok(p)
    msg = stops(runner.run)
    assert "does not fit" in msg and len(server.sent) == 2, msg
    return "40,000 + 128,000 > 163,840 -> stopped before the call"


def case_ceiling(tmp, cfg):
    server, runner, _ = fresh(tmp, cfg)

    def at_budget(r):
        r["choices"][0]["finish_reason"] = "length"
        r["choices"][0]["message"]["content"] = ""
        r["usage"] = {**r["usage"], "completion_tokens": cfg["budget"]}
        return r
    tamper_once(server, P3, at_budget)
    verdict = runner.run()
    row = base_rows(tmp)[CID3]
    assert row["stop_reason"] == "max_tokens" and row["error"] == "TruncatedAnswerError"
    assert server.sent.count(P3) == 1, "a D6 non-completion was re-asked"
    rs = json.load(open(os.path.join(tmp, "raw", "final-headlineJ-rs1.spec.json"), encoding="utf-8"))
    assert rs["at_ceiling"] == [CID3], rs["at_ceiling"]
    rp = json.load(open(os.path.join(tmp, "raw", "final-headlineJ-r1.spec.json"), encoding="utf-8"))
    assert not any(r["unit"].startswith(SPEC["requests"][2]["unit"].replace("_", "-")) or
                   r["unit"].startswith(SPEC["requests"][2]["unit"]) for r in rp["requests"])
    rb = [json.loads(x) for x in open(os.path.join(tmp, "results", "final_headlineJ", "prose", "J.rbnc.jsonl"),
                                      encoding="utf-8")]
    assert [x["unit"] for x in rb] == [SPEC["requests"][2]["unit"]], rb
    second = os.path.exists(os.path.join(tmp, "results", "final_headlineJ_answered_units_only", "REPORT.txt"))
    return (f"D6: recorded at_ceiling, not resent, not repaired, in J.rbnc.jsonl; gate verdict {verdict}; "
            f"answered-units-only copy written: {second}")


def case_zero_answer(tmp, cfg):
    server, runner, _ = fresh(tmp, cfg)

    def empty(r):
        r["choices"][0]["message"]["content"] = ""
        r["choices"][0]["message"]["reasoning_content"] = "thinking..."
        return r
    tamper_once(server, P3, empty)
    verdict = runner.run()
    assert base_rows(tmp)[CID3]["error"] == "ZeroAnswerError"
    assert CID3 in base_rows(tmp, "final-headlineJ-rs1") and server.sent.count(P3) == 2
    assert not any(verdict.values()), verdict
    return "ZeroAnswerError row, resent once in -rs1 (D4), then scored"


def case_repair_transport(tmp, cfg):
    _spec, _a, _t, _rows, rp = RS.sonnet_oracle(cfg)
    rprompt = rp["requests"][0]["prompt"]
    server, runner, _ = fresh(tmp, cfg)

    def boom(r):
        raise R.TransportError("connection reset")
    tamper_once(server, rprompt, boom)
    verdict = runner.run()
    rrs = base_rows(tmp, "final-headlineJ-r1-rs1")
    assert len(rrs) == 1 and server.sent.count(rprompt) == 2, rrs
    assert not any(verdict.values()), verdict
    return "repair transport failure -> errored row, resent once in -r1-rs1, then scored"


CASES = [case_restart, case_control_token, case_prompt_tokens, case_short_length, case_slots_params,
         case_logged_prompt, case_render_hash, case_no_fit, case_ceiling, case_zero_answer,
         case_repair_transport]


def main():
    failed = 0
    for case in CASES:
        tmp, cfg = setup()
        try:
            print(f"PASS {case.__name__[5:]}: {case(tmp, cfg)}")
        except Exception as e:                                  # noqa: BLE001
            failed += 1
            print(f"FAIL {case.__name__[5:]}: {type(e).__name__}: {e}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"{len(CASES) - failed}/{len(CASES)} cases passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
