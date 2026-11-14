"""Offline tests of api_runner.py + score_api.py. NO MODEL CALLS (the provider is a fake).

    python -I work/runner/test_api_runner.py

1. Replay: Sonnet's headline answers served through the runner (base, a transport error
   retried in-wave, one unit errored at the attempt limit -> frozen -rs1, the frozen repair)
   reproduce Sonnet's 46 final answers and F1_J 0.7225 / F1_L 0.8817 / q 0.8206, verdict PASS.
2. Content filter on one pool: never resent, never a row; the unit is excluded and the
   primary verdict is REFUSED (unit without an answer).
3. Provider mismatch: halts the wave; a check_failures record; rerun without the flag refuses.
4. Cost cap during the base wave: halts.
5. A max_tokens stop below the budget: halts.
6. Amendment 2, Azure: a content-filter block is resent once in -rs1 (answered there -> scored,
   PASS); blocked again -> "not completed", REFUSED.
Writes only raw/_t*/, results/_t*/, logs/_t*/ and removes them.
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import api_runner as A                                            # noqa: E402
import score_api as S                                             # noqa: E402

A.BACKOFF_BASE_S = 0
A.MAX_INFLIGHT = 4
B = A.SONNET_BATCHES


def sonnet_answers():
    base = {}
    for f in ("final-headlineJ.results.jsonl", "final-headlineJ-rs1.results.jsonl"):
        for ln in open(os.path.join(B, f), encoding="utf-8"):
            r = json.loads(ln)
            if r.get("result_type") == "succeeded" and r.get("text"):
                base[r["unit"]] = r
    rep = {json.loads(ln)["unit"]: json.loads(ln)
           for ln in open(os.path.join(B, "final-headlineJ-r1.results.jsonl"), encoding="utf-8")}
    return base, rep


SPEC = json.load(open(A.HEADLINE_SPEC, encoding="utf-8"))
PROMPT_UNIT = {r["prompt"]: r["unit"] for r in SPEC["requests"]}
BASE, REP = sonnet_answers()


class Fake:
    def __init__(self, mode=None):
        self.mode, self.calls, self.errs = mode, [], {}

    def __call__(self, body):
        prompt = (body.get("messages") or body.get("input"))[0]["content"]
        unit = PROMPT_UNIT.get(prompt)
        rep = unit is None
        if rep:
            unit = next(u for p, u in PROMPT_UNIT.items() if prompt.startswith(p))
        slug = unit.replace("_", "-")
        self.calls.append(unit + ("-r1" if rep else ""))
        if not rep and unit == "pool_003":                 # one transient error, then fine
            self.errs[unit] = self.errs.get(unit, 0) + 1
            if self.errs[unit] == 1:
                raise A.Transport("HTTP 429: busy", retry_after=0)
        if not rep and unit == "pool_007" and self.mode in (None, "cf"):   # errored at the limit, ok in -rs1
            self.errs[unit] = self.errs.get(unit, 0) + 1
            if self.errs[unit] <= A.MAX_ATTEMPTS:
                raise A.Transport("HTTP 503: down", retry_after=0)
        if self.mode == "cf" and unit == "pool_010" and not rep:
            raise A.ContentFilter("finish_reason content_filter")
        if self.mode in ("azcf1", "azcf2") and unit == "pool_010" and not rep:
            self.errs["cf"] = self.errs.get("cf", 0) + 1
            if self.mode == "azcf2" or self.errs["cf"] == 1:
                raise A.ContentFilter("response incomplete: content_filter", detail={"x": 1})
        r = REP[slug + "-r1"] if rep else BASE[slug]
        provider = "Other" if (self.mode == "provider" and unit == "pool_005") else "TestProv"
        n_out = r["usage"]["output_tokens"]
        finish = "stop"
        if self.mode == "short" and unit == "pool_006":
            finish, n_out = "length", 100
        if self.mode in ("azcf1", "azcf2"):
            return {"text": r["text"], "reasoning": "", "finish": finish, "input_tokens": r["usage"]["input_tokens"],
                    "output_tokens": n_out, "reasoning_tokens": None, "cost": 0.001, "usage_raw": r["usage"],
                    "provider": "azure", "reported_model": "gpt-4.1", "service_tier": "default",
                    "echo_max_output_tokens": 128000, "echo_truncation": "disabled", "echo_reasoning": None,
                    "wall_s": 0.0}
        return {"text": r["text"], "reasoning": "", "finish": finish, "input_tokens": r["usage"]["input_tokens"],
                "output_tokens": n_out, "reasoning_tokens": None, "cost": 0.001, "usage_raw": r["usage"],
                "provider": provider, "reported_model": "test/model", "service_tier": None, "wall_s": 0.0}


def cfg(slug, cap=10.0):
    c = {"slug": slug, "api": "openrouter", "model": "test/model", "provider": "testprov",
         "provider_name": "TestProv", "quant": "fp4", "budget": 128000, "cap": cap, "extra": {},
         "price_in": 1e-7, "price_out": 1e-7, "timeout_s": 60}
    A.CONFIGS[slug] = c
    return c


def azcfg(slug):
    c = {"slug": slug, "api": "azure", "deployment_env": "AZURE_DEPLOYMENT_GPT41", "budget": 128000, "cap": 10.0,
         "tier": "default", "send_tier": None, "extra": {}, "price_in": 1e-7, "price_out": 1e-7,
         "tpm": 10**9, "timeout_s": 60, "model_prefix": "gpt-4.1", "guardrail": "Default"}
    A.CONFIGS[slug] = c
    A.PINNED_REPORTED_MODEL[slug] = {"gpt-4.1"}
    return c


def runner(slug, fake, cap=10.0, c=None, **kw):
    r = A.ApiRunner(c or cfg(slug, cap), out=lambda *_: None, **kw)
    r.key = "x"
    r.send = fake
    return r


def clean(slug):
    for d in ("raw", "results", "logs"):
        shutil.rmtree(os.path.join(A.SB, d, slug), ignore_errors=True)


def expect_exit(fn, word):
    try:
        fn()
    except SystemExit as e:
        assert word in str(e), (word, str(e))
        return str(e)
    raise AssertionError(f"expected a stop containing {word!r}")


def main():
    ok = 0
    # 1 replay
    slug = "_t1"
    clean(slug)
    try:
        f = Fake()
        s = runner(slug, f).run()
        r46 = s["pools46"]
        assert r46["PRIMARY_verdict"] == "PASS", r46
        m = r46["PRIMARY_means"]
        assert abs(m["F1_J"] - 0.7225) < 5e-5 and abs(m["F1_L"] - 0.8817) < 5e-5 and abs(m["q"] - 0.8206) < 5e-5, m
        mine = {r["unit"]: r for r in map(json.loads, open(os.path.join(
            A.SB, "results", slug, "final_headlineJ", "prose", "J.jsonl"), encoding="utf-8"))}
        ref = {r["unit"]: r for r in map(json.loads, open(os.path.join(
            A.FROZEN, "results", "final", "headlineJ", "prose", "J.jsonl"), encoding="utf-8"))}
        assert set(mine) == set(ref) and all(mine[u]["raw_response"] == ref[u]["raw_response"] for u in ref)
        assert f.calls.count("pool_007") == A.MAX_ATTEMPTS + 1, f.calls.count("pool_007")
        assert os.path.exists(os.path.join(A.SB, "raw", slug, "final-headlineJ-rs1.results.jsonl"))
        n_rep = sum(1 for c in f.calls if c.endswith("-r1"))
        print(f"1. replay PASS: F1_J {m['F1_J']:.4f} F1_L {m['F1_L']:.4f} q {m['q']:.4f}; 46 answers equal "
              f"Sonnet's; pool_007 errored x{A.MAX_ATTEMPTS} then answered in -rs1; {n_rep} repairs")
        ok += 1
    finally:
        clean(slug)
    # 2 content filter
    slug = "_t2"
    clean(slug)
    try:
        f = Fake("cf")
        s = runner(slug, f).run()
        r46 = s["pools46"]
        assert f.calls.count("pool_010") == 1, f.calls.count("pool_010")
        assert r46["PRIMARY_verdict"] == "REFUSED" and r46["refusal_reasons"]["units_without_answer"] == ["pool_010"], r46
        assert r46["excluded_units"]["content_filter"] == ["pool_010"]
        assert s["pools41"]["PRIMARY_verdict"] == "REFUSED"
        print("2. content filter PASS: sent once, never resent, excluded, primary REFUSED (pool_010 no answer)")
        ok += 1
    finally:
        clean(slug)
    # 3 provider mismatch
    slug = "_t3"
    clean(slug)
    try:
        expect_exit(lambda: runner(slug, Fake("provider")).run(), "provider mismatch")
        expect_exit(lambda: runner(slug, Fake()).run(), "unreviewed halt")
        print("3. provider mismatch PASS: halted; rerun refused without --resume-after-check-failure")
        ok += 1
    finally:
        clean(slug)
    # 4 cap in the base wave
    slug = "_t4"
    clean(slug)
    try:
        expect_exit(lambda: runner(slug, Fake(), cap=0.05).run(), "cost cap")
        print("4. cost cap in base wave PASS: halted")
        ok += 1
    finally:
        clean(slug)
    # 5 length below budget
    slug = "_t5"
    clean(slug)
    try:
        expect_exit(lambda: runner(slug, Fake("short")).run(), "below the budget")
        print("5. max_tokens stop below the budget PASS: halted")
        ok += 1
    finally:
        clean(slug)
    # 6 amendment 2: Azure content filter resent once
    for mode, want in (("azcf1", "PASS"), ("azcf2", "REFUSED")):
        slug = "_t6"
        clean(slug)
        try:
            f = Fake(mode)
            r = runner(slug, f, c=azcfg(slug))
            r.bucket = None   # no rate limit offline
            s = r.run()
            r46 = s["pools46"]
            assert f.calls.count("pool_010") == 2, f.calls.count("pool_010")
            assert r46["PRIMARY_verdict"] == want, (mode, r46["PRIMARY_verdict"], r46.get("refusal_reasons"))
            if want == "REFUSED":
                assert r46["excluded_units"]["not_completed"] == ["pool_010"], r46["excluded_units"]
                assert r46["excluded_units"]["content_filter"] == []
            g = [json.loads(x) for x in open(os.path.join(A.SB, "raw", slug, "guardrail.jsonl"), encoding="utf-8")]
            assert g and all(x["guardrail"] == "Default" for x in g)
        finally:
            clean(slug)
    print("6. Azure content filter (amendment 2) PASS: resent once in -rs1; answered -> PASS; "
          "blocked twice -> not completed, REFUSED; guardrail recorded per row")
    ok += 1
    print(f"{ok}/6 passed")


if __name__ == "__main__":
    main()
