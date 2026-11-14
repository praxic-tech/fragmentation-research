"""Headline Game J on hosted models (PREREGISTRATION.md, 2026-11-13). Post-hoc exploratory.

    python -I work/runner/api_runner.py SLUG             # run the protocol, then score
    python -I work/runner/api_runner.py SLUG --smoke     # one dummy request (no evaluation text)
    python -I work/runner/api_runner.py SLUG --score     # score from raw rows only (no requests)
    python -I work/runner/api_runner.py --balance        # OpenRouter key usage / limit

Protocol, frozen functions only (order of frozen/runs/final_run_steps123.py):

    base wave -> build_resubmit_spec (-rs1) -> build_repair_spec(..., 1, 1, "-r1") -> its -rs1
              -> score_api.score_model (frozen batch_game.score, primary rule, 41 pools)

Transport errors (408, 429, 5xx, connection, timeout, stream without a final response)
are retried in the wave, at most MAX_ATTEMPTS per request, honouring Retry-After;
still failing -> an errored row (the frozen D4 -rs1 then sends it once more).
Content-filter blocks go to <tag>.content_filter.jsonl: never a row, never resent.
Halts (auth, provider/tier/model mismatch, prompt-integrity failure, a max_tokens stop
below the budget, a cap reached before the base wave finishes, any uncovered case)
write <tag>.check_failures.jsonl and stop; resume only with --resume-after-check-failure
(the user's instruction).

Credentials are read from azure.env inside this process only and never printed or logged.
"""
import argparse
import hashlib
import json
import os
import random
import sys
import threading
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone

import httpx
from dotenv import dotenv_values

SB = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FROZEN = os.path.join(SB, "frozen")
for _d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(FROZEN, _d))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import batch_game                                                   # noqa: E402
from batch_submit import (IncompleteBatchError, TruncatedAnswerError,  # noqa: E402
                          ZeroAnswerError, _latest_rows, failed_ids, make_custom_id,
                          parse_custom_id)

HEADLINE_SPEC = os.path.join(FROZEN, "runs", "final_headlineJ.json")
SONNET_BATCHES = os.path.join(FROZEN, "results", "batches")
MAX_ATTEMPTS = 6
MAX_INFLIGHT = 16
BACKOFF_BASE_S, BACKOFF_MAX_S = 30, 900
OR_URL = "https://openrouter.ai/api/v1/chat/completions"
SMOKE_PROMPT = ('Return exactly this JSON array and nothing else: [["x1", "x2"], ["x3"]]')

OR_META = os.path.join(SB, "work", "runner", "meta")


def _or(slug, model, provider, provider_name, quant, budget, cap, extra, tag=None):
    meta = json.load(open(os.path.join(OR_META, model.replace("/", "_") + ".endpoints.json"),
                          encoding="utf-8"))["data"]["endpoints"]
    ep = [e for e in meta if e["provider_name"] == provider_name and e["quantization"] == quant
          and (tag is None or e.get("tag") == tag)]
    assert len(ep) == 1, (slug, provider_name, quant, len(ep))
    ep = ep[0]
    assert budget <= ep["max_completion_tokens"], (slug, budget, ep["max_completion_tokens"])
    return {"slug": slug, "api": "openrouter", "model": model, "provider": provider,
            "provider_name": provider_name, "quant": quant, "budget": budget, "cap": cap,
            "extra": extra, "price_in": float(ep["pricing"]["prompt"]),
            "price_out": float(ep["pricing"]["completion"]), "timeout_s": 2 * 3600,
            "endpoint_tag": ep.get("tag"), "max_completion_tokens": ep["max_completion_tokens"]}


GPTOSS_EXTRA = {"reasoning": {"effort": "high"}, "temperature": 1.0, "top_p": 1.0}
GPTOSS_BUDGET = 110000
# Fallback under the amendment (used only if AkashML fails its smoke test).
PARASAIL_FALLBACK = {
    "gpt-oss-20b": lambda: _or("gpt-oss-20b", "openai/gpt-oss-20b", "parasail", "Parasail", "fp4",
                               GPTOSS_BUDGET, 1.00, GPTOSS_EXTRA),
    "gpt-oss-120b": lambda: _or("gpt-oss-120b", "openai/gpt-oss-120b", "parasail", "Parasail", "fp4",
                                GPTOSS_BUDGET, 3.00, GPTOSS_EXTRA, tag="parasail/fp4"),
}

CONFIGS = {
    # Amendment 2026-11-13: AkashML fp4, fixed 110,000 output budget (CoreWeave superseded).
    "gpt-oss-20b": _or("gpt-oss-20b", "openai/gpt-oss-20b", "akashml", "AkashML", "fp4",
                       GPTOSS_BUDGET, 1.00, GPTOSS_EXTRA),
    "gpt-oss-120b": _or("gpt-oss-120b", "openai/gpt-oss-120b", "akashml", "AkashML", "fp4",
                        GPTOSS_BUDGET, 1.50, GPTOSS_EXTRA),
    "llama-4-maverick": _or("llama-4-maverick", "meta-llama/llama-4-maverick", "parasail",
                            "Parasail", "fp8", 32768, 1.50, {}),
    "deepseek-v3.2": _or("deepseek-v3.2", "deepseek/deepseek-v3.2", "gmicloud", "GMICloud", "fp8",
                         128000, 3.00, {"reasoning": {"enabled": True}}),
    "kimi-k2.5": _or("kimi-k2.5", "moonshotai/kimi-k2.5", "siliconflow", "SiliconFlow", "int4",
                     128000, None, {"reasoning": {"enabled": True}}),     # cap set by the Kimi rule
    "gpt-4.1": {"slug": "gpt-4.1", "api": "azure", "deployment_env": "AZURE_DEPLOYMENT_GPT41",
                "budget": 32768, "cap": 10.00, "tier": "default", "send_tier": None,
                "extra": {}, "price_in": 2.00e-6, "price_out": 8.00e-6, "tpm": 1_000_000,
                "timeout_s": 30 * 60, "model_prefix": "gpt-4.1"},
    "gpt-5.6-sol": {"slug": "gpt-5.6-sol", "api": "azure", "deployment_env": "AZURE_DEPLOYMENT_GPT56",
                    "budget": 128000, "cap": 50.00, "tier": "flex", "send_tier": "flex",
                    "extra": {"reasoning": {"effort": "max"}}, "price_in": 2.00e-6,
                    "price_out": 10.00e-6, "tpm": 250_000, "timeout_s": 30 * 60,
                    "model_prefix": "gpt-5.6-sol"},
}
# Reported model ids that pass the pinned-model check; filled from the smoke tests (RUNLOG).
PINNED_REPORTED_MODEL = {"gpt-4.1": {"gpt-4.1-2025-04-14", "gpt-4.1"},
                         "gpt-5.6-sol": {"gpt-5.6-sol-2026-07-09", "gpt-5.6-sol"}}


def now():
    return datetime.now(timezone.utc).isoformat()


def env():
    v = dotenv_values(os.path.join(SB, "azure.env"))
    return {k: (x or "").strip() for k, x in v.items()}


class Transport(RuntimeError):
    def __init__(self, msg, retry_after=None):
        super().__init__(msg)
        self.retry_after = retry_after


class ContentFilter(RuntimeError):
    pass


class Halt(RuntimeError):
    pass


def _retry_after(headers):
    for k in ("retry-after-ms", "retry-after"):
        v = headers.get(k)
        if v:
            try:
                return float(v) / (1000 if k.endswith("ms") else 1)
            except ValueError:
                pass
    return None


def _http_error(status, body_text, headers):
    low = body_text.lower()
    if status == 400 and ("content_filter" in low or "content management policy" in low
                          or "responsibleaipolicyviolation" in low):
        raise ContentFilter(f"HTTP 400 content filter: {body_text[:400]}")
    if status in (401, 403):
        raise Halt(f"auth failure HTTP {status}: {body_text[:300]}")
    if status == 408 or status == 429 or status >= 500:
        raise Transport(f"HTTP {status}: {body_text[:300]}", _retry_after(headers))
    if status == 403 and "moderation" in low:
        raise ContentFilter(f"HTTP 403 moderation: {body_text[:400]}")
    if status == 400 and ("context length" in low or "context_length" in low):
        raise Halt(f"HTTP 400 context length (halt per the amendment): {body_text[:400]}")
    raise Halt(f"HTTP {status} (not covered): {body_text[:400]}")


def _sse(resp, deadline):
    """Yield (event, data-dict) from an SSE stream; ':' comment lines are keep-alives."""
    ev = None
    for line in resp.iter_lines():
        if time.time() > deadline:
            raise Transport("timeout: wall-clock limit reached")
        if not line or line.startswith(":"):
            if not line:
                ev = None
            continue
        if line.startswith("event:"):
            ev = line[6:].strip()
            continue
        if line.startswith("data:"):
            d = line[5:].strip()
            if d == "[DONE]":
                return
            try:
                yield ev, json.loads(d)
            except json.JSONDecodeError:
                raise Transport(f"undecodable stream line: {d[:200]}") from None


# ── the two providers ────────────────────────────────────────────────────────

def openrouter_body(cfg, prompt):
    return {"model": cfg["model"], "messages": [{"role": "user", "content": prompt}],
            "max_tokens": cfg["budget"], "stream": True, "transforms": [],
            "usage": {"include": True},
            "provider": {"only": [cfg["provider"]], "order": [cfg["provider"]],
                         "quantizations": [cfg["quant"]], "allow_fallbacks": False,
                         "require_parameters": True},
            **cfg["extra"]}


def azure_body(cfg, prompt, deployment):
    b = {"model": deployment, "input": [{"role": "user", "content": prompt}],
         "max_output_tokens": cfg["budget"], "truncation": "disabled", "stream": True,
         **cfg["extra"]}
    if cfg["send_tier"]:
        b["service_tier"] = cfg["send_tier"]
    return b


def call_openrouter(cfg, body, key):
    deadline = time.time() + cfg["timeout_s"]
    content, reasoning, usage, finish, native, provider, model, gen_id = [], [], None, None, None, None, None, None
    t0 = time.time()
    try:
        with httpx.stream("POST", OR_URL, json=body,
                          headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                   "X-Title": "cross-model-sandbox"},
                          timeout=httpx.Timeout(connect=60, read=900, write=120, pool=60)) as r:
            if r.status_code != 200:
                r.read()
                _http_error(r.status_code, r.text, r.headers)
            for _ev, d in _sse(r, deadline):
                if d.get("error"):
                    err = d["error"]
                    msg = json.dumps(err)[:400]
                    if "moderation" in msg.lower() or "content_filter" in msg.lower():
                        raise ContentFilter(f"in-stream: {msg}")
                    code = err.get("code") if isinstance(err, dict) else None
                    if code in (401, 403):
                        raise Halt(f"auth failure in stream: {msg}")
                    raise Transport(f"error in stream: {msg}")
                provider = d.get("provider") or provider
                model = d.get("model") or model
                gen_id = d.get("id") or gen_id
                usage = d.get("usage") or usage
                for ch in d.get("choices", []):
                    dl = ch.get("delta") or {}
                    content.append(dl.get("content") or "")
                    reasoning.append(dl.get("reasoning") or "")
                    finish = ch.get("finish_reason") or finish
                    native = ch.get("native_finish_reason") or native
    except (Transport, ContentFilter, Halt):
        raise
    except (httpx.TimeoutException, httpx.TransportError, OSError) as e:
        raise Transport(f"{type(e).__name__}: {e}") from None
    if finish == "content_filter":
        raise ContentFilter(f"finish_reason content_filter (native {native})")
    if finish == "error":
        raise Transport(f"finish_reason error (native {native})")
    if usage is None or finish is None:
        raise Transport("stream ended without usage or finish_reason")
    if finish not in ("stop", "length"):
        raise Halt(f"finish_reason {finish!r} (native {native!r}) not covered")
    return {"text": "".join(content), "reasoning": "".join(reasoning), "finish": finish,
            "native_finish_reason": native,
            "input_tokens": usage.get("prompt_tokens"), "output_tokens": usage.get("completion_tokens"),
            "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "cost": usage.get("cost"), "usage_raw": usage, "provider": provider,
            "reported_model": model, "generation_id": gen_id, "service_tier": None,
            "wall_s": round(time.time() - t0, 1)}


def call_azure(cfg, body, endpoint, key):
    deadline = time.time() + cfg["timeout_s"]
    base = endpoint.rstrip("/")
    if base.endswith("/openai/v1"):          # the endpoint may already carry the v1 path
        base = base[: -len("/openai/v1")]
    url = base + "/openai/v1/responses"
    final, t0 = None, time.time()
    try:
        with httpx.stream("POST", url, json=body,
                          headers={"api-key": key, "Content-Type": "application/json"},
                          timeout=httpx.Timeout(connect=60, read=900, write=120, pool=60)) as r:
            if r.status_code != 200:
                r.read()
                _http_error(r.status_code, r.text, r.headers)
            for ev, d in _sse(r, deadline):
                typ = d.get("type") or ev
                if typ in ("response.completed", "response.incomplete", "response.failed"):
                    final = d.get("response")
                elif typ == "error":
                    msg = json.dumps(d)[:400]
                    if "content_filter" in msg.lower():
                        raise ContentFilter(f"in-stream: {msg}")
                    raise Transport(f"error in stream: {msg}")
    except (Transport, ContentFilter, Halt):
        raise
    except (httpx.TimeoutException, httpx.TransportError, OSError) as e:
        raise Transport(f"{type(e).__name__}: {e}") from None
    if final is None:
        raise Transport("stream ended without a final response")
    status = final.get("status")
    reason = (final.get("incomplete_details") or {}).get("reason")
    if status == "failed":
        err = json.dumps(final.get("error"))[:400]
        if "content_filter" in err.lower():
            raise ContentFilter(f"response failed: {err}")
        if "server_error" in err.lower() or "rate_limit" in err.lower():
            raise Transport(f"response failed: {err}")
        raise Halt(f"response failed (not covered): {err}")
    if status == "incomplete" and reason == "content_filter":
        raise ContentFilter("response incomplete: content_filter")
    if status == "completed":
        finish = "stop"
    elif status == "incomplete" and reason == "max_output_tokens":
        finish = "length"
    else:
        raise Halt(f"status {status!r} reason {reason!r} not covered")
    text = "".join(c.get("text", "") for o in final.get("output", []) if o.get("type") == "message"
                   for c in o.get("content", []) if c.get("type") == "output_text")
    refusal = [c.get("refusal") for o in final.get("output", []) if o.get("type") == "message"
               for c in o.get("content", []) if c.get("type") == "refusal"]
    u = final.get("usage") or {}
    return {"text": text, "reasoning": "", "finish": finish, "refusal": refusal or None,
            "input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
            "reasoning_tokens": (u.get("output_tokens_details") or {}).get("reasoning_tokens"),
            "cached_tokens": (u.get("input_tokens_details") or {}).get("cached_tokens"),
            "cost": None, "usage_raw": u, "provider": "azure", "reported_model": final.get("model"),
            "service_tier": final.get("service_tier"), "response_id": final.get("id"),
            "echo_reasoning": final.get("reasoning"), "echo_max_output_tokens": final.get("max_output_tokens"),
            "echo_truncation": final.get("truncation"), "wall_s": round(time.time() - t0, 1)}


# ── rows: the format batch_submit.fetch wrote for Sonnet ─────────────────────

STOP_REASON = {"stop": "end_turn", "length": "max_tokens"}


def row_from_result(cid, res, attempts):
    row = {"custom_id": cid, **parse_custom_id(cid), "fetched_at": now(), "result_type": "succeeded",
           "usage": {"input_tokens": res["input_tokens"], "output_tokens": res["output_tokens"],
                     "reasoning_tokens": res.get("reasoning_tokens"), "raw": res["usage_raw"]},
           "stop_reason": STOP_REASON[res["finish"]]}
    text = res["text"] or ""
    if row["stop_reason"] == "max_tokens":
        row["error"] = TruncatedAnswerError.__name__
        row["detail"] = f"stopped at max_tokens after {res['output_tokens']} output tokens"
        if text.strip():
            row["partial_text"] = text
    elif not text.strip():
        row["error"] = ZeroAnswerError.__name__
        row["detail"] = f"empty answer after {res['output_tokens']} output tokens"
    else:
        row["text"] = text
    row["reasoning"] = res.get("reasoning") or ""
    for k in ("provider", "service_tier", "reported_model", "cost", "generation_id", "response_id",
              "native_finish_reason", "refusal", "cached_tokens", "echo_reasoning",
              "echo_max_output_tokens", "wall_s"):
        if res.get(k) is not None:
            row[k] = res[k]
    row["finish_reason"] = res["finish"]
    row["attempts"] = attempts
    return row


def errored_row(cid, err, attempts):
    return {"custom_id": cid, **parse_custom_id(cid), "fetched_at": now(), "result_type": "errored",
            "error": f"{type(err).__name__}: {err}", "attempts": attempts}


def sonnet_input_tokens():
    """unit -> Sonnet's reported input tokens on the base prompt (latest row with usage)."""
    out = {}
    for f in ("final-headlineJ.results.jsonl", "final-headlineJ-rs1.results.jsonl"):
        for ln in open(os.path.join(SONNET_BATCHES, f), encoding="utf-8"):
            r = json.loads(ln)
            n = (r.get("usage") or {}).get("input_tokens")
            if n:
                out[r["unit"].replace("-", "_")] = n          # row slug pool-001 -> sidecar unit pool_001
    return out


def base_unit(unit_slug):
    return unit_slug.split("-r")[0] if "-r" in unit_slug else unit_slug


# ── the run ──────────────────────────────────────────────────────────────────

class Ledger:
    """Spent cost plus the worst case of every in-flight request; never past the cap."""

    def __init__(self, cap, spent=0.0):
        self.cap, self.spent, self.reserved = cap, spent, {}
        self.lock = threading.Lock()

    def try_reserve(self, cid, worst):
        with self.lock:
            if self.spent + sum(self.reserved.values()) + worst > self.cap + 1e-12:
                return False
            self.reserved[cid] = worst
            return True

    def settle(self, cid, cost):
        with self.lock:
            self.reserved.pop(cid, None)
            self.spent += cost or 0.0


class TPMBucket:
    def __init__(self, tpm):
        self.tpm, self.win, self.lock = tpm, deque(), threading.Lock()

    def acquire(self, n, stop):
        while not stop.is_set():
            with self.lock:
                t = time.time()
                while self.win and t - self.win[0][0] > 60:
                    self.win.popleft()
                if sum(x for _, x in self.win) + n <= self.tpm or not self.win:
                    self.win.append((t, n))
                    return True
            time.sleep(1)
        return False


class ApiRunner:
    def __init__(self, cfg, resume_after_check_failure=False, out=print):
        self.cfg, self.out, self.resume = cfg, out, resume_after_check_failure
        slug = cfg["slug"]
        self.raw_dir = os.path.join(SB, "raw", slug)
        self.log_dir = os.path.join(SB, "logs", slug)
        self.req_dir = os.path.join(self.log_dir, "requests")       # full bodies: not committed
        for d in (self.raw_dir, self.log_dir, self.req_dir):
            os.makedirs(d, exist_ok=True)
        self.log_path = os.path.join(self.log_dir, "run.log")
        self.lock = threading.Lock()
        e = env()
        if cfg["api"] == "openrouter":
            self.key = e.get("OPENROUTER_API_KEY")
            assert self.key, "OPENROUTER_API_KEY missing"
        else:
            self.key, self.endpoint = e.get("AZURE_OPENAI_API_KEY"), e.get("AZURE_OPENAI_ENDPOINT")
            self.deployment = e.get(cfg["deployment_env"])
            assert self.key and self.endpoint and self.deployment, "Azure settings missing"
        self.sonnet_in = sonnet_input_tokens()
        self.ledger = Ledger(cfg["cap"] if cfg["cap"] is not None else 0.0, self.spent_so_far())
        self.bucket = TPMBucket(cfg["tpm"]) if cfg["api"] == "azure" else None
        self.stop = threading.Event()

    # ---- bookkeeping -------------------------------------------------------

    def log(self, msg):
        line = f"{now()} {msg}"
        with self.lock:
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        self.out(line)

    def path(self, tag, kind="results.jsonl"):
        return os.path.join(self.raw_dir, f"{tag}.{kind}")

    def append(self, path, obj):
        with self.lock:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(obj) + "\n")
                fh.flush()
                os.fsync(fh.fileno())

    def cost_of(self, res):
        if res.get("cost") is not None:
            return float(res["cost"])
        return (res.get("input_tokens") or 0) * self.cfg["price_in"] + \
            (res.get("output_tokens") or 0) * self.cfg["price_out"]

    def spent_so_far(self):
        """Cost already recorded in this model's attempt logs (a restart keeps counting)."""
        total = 0.0
        if os.path.isdir(self.raw_dir):
            for f in os.listdir(self.raw_dir):
                if f.endswith(".attempts.jsonl"):
                    for ln in open(os.path.join(self.raw_dir, f), encoding="utf-8"):
                        total += json.loads(ln).get("cost_usd") or 0.0
        return total

    def body(self, prompt):
        if self.cfg["api"] == "openrouter":
            return openrouter_body(self.cfg, prompt)
        return azure_body(self.cfg, prompt, self.deployment)

    def send(self, body):
        if self.cfg["api"] == "openrouter":
            return call_openrouter(self.cfg, body, self.key)
        return call_azure(self.cfg, body, self.endpoint, self.key)

    def est_prompt_tokens(self, side):
        return int(1.2 * self.sonnet_in.get(side["unit"], 30000)) + 2048

    def worst(self, side):
        return self.est_prompt_tokens(side) * self.cfg["price_in"] + self.cfg["budget"] * self.cfg["price_out"]

    # ---- per-response checks -------------------------------------------------

    def check(self, res, side, prompt):
        cfg = self.cfg
        if cfg["api"] == "openrouter":
            if res.get("provider") != cfg["provider_name"]:
                raise Halt(f"provider mismatch: reported {res.get('provider')!r}, pinned {cfg['provider_name']!r}")
            if res.get("reported_model") and not str(res["reported_model"]).startswith(cfg["model"]):
                raise Halt(f"model mismatch: reported {res.get('reported_model')!r}, pinned {cfg['model']!r}")
        else:
            if res.get("service_tier") != cfg["tier"]:
                raise Halt(f"service_tier mismatch: reported {res.get('service_tier')!r}, pinned {cfg['tier']!r}")
            if res.get("reported_model") not in PINNED_REPORTED_MODEL[cfg["slug"]]:
                raise Halt(f"model mismatch: reported {res.get('reported_model')!r}")
            if res.get("echo_max_output_tokens") != cfg["budget"]:
                raise Halt(f"max_output_tokens echoed {res.get('echo_max_output_tokens')!r} != {cfg['budget']}")
            if res.get("echo_truncation") != "disabled":
                raise Halt(f"truncation echoed {res.get('echo_truncation')!r}")
            want = (cfg["extra"].get("reasoning") or {}).get("effort")
            if want and (res.get("echo_reasoning") or {}).get("effort") != want:
                raise Halt(f"reasoning effort echoed {res.get('echo_reasoning')!r} != {want!r}")
        if side is not None:
            ref = self.sonnet_in.get(side["unit"])
            n = res.get("input_tokens") or 0
            if ref is None or n < 0.5 * ref:
                raise Halt(f"prompt integrity: reported prompt tokens {n} < 0.5 x Sonnet's {ref}")
        if res["finish"] == "length" and (res.get("output_tokens") or 0) < cfg["budget"]:
            raise Halt(f"stopped at length after {res.get('output_tokens')} tokens, below the budget "
                       f"{cfg['budget']} (not covered by D6)")
        if res.get("output_tokens") is None or res.get("input_tokens") is None:
            raise Halt("response without token usage")

    # ---- one request, all its attempts -------------------------------------

    def one(self, tag, cid, side, prompt):
        body = self.body(prompt)
        logged = {**body}
        logged["messages" if "messages" in body else "input"] = [
            {"role": "user", "content_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
             "content_chars": len(prompt)}]
        logged.pop("model", None) if self.cfg["api"] == "azure" else None
        attempts = []
        for k in range(1, MAX_ATTEMPTS + 1):
            if self.stop.is_set():
                return ("stopped", None)
            if self.bucket is not None:
                if not self.bucket.acquire(self.est_prompt_tokens(side) + self.cfg["budget"], self.stop):
                    return ("stopped", None)
            with open(os.path.join(self.req_dir, f"{tag}.{cid}.a{k}.json"), "w", encoding="utf-8") as fh:
                json.dump(body, fh)
            t0, rec = time.time(), {"custom_id": cid, "attempt": k, "sent_at": now(), "body": logged}
            try:
                res = self.send(body)
            except Transport as e:
                rec.update({"outcome": "transport", "error": str(e), "s": round(time.time() - t0, 1),
                            "cost_usd": 0.0})
                self.append(self.path(tag, "attempts.jsonl"), rec)
                attempts.append({"attempt": k, "outcome": "transport", "error": str(e)[:200]})
                if "timeout" in str(e).lower():
                    self.log(f"TIMEOUT {tag} {cid} attempt {k} after {rec['s']} s; logged before the resend")
                if k == MAX_ATTEMPTS:
                    return ("errored", e, attempts)
                delay = e.retry_after if e.retry_after is not None else min(BACKOFF_BASE_S * 2 ** (k - 1), BACKOFF_MAX_S)
                delay = delay + random.uniform(0, 0.25 * delay + 1)
                self.log(f"{tag} {cid} attempt {k} transport error: {str(e)[:120]}; retry in {delay:.0f} s")
                if self.stop.wait(delay):
                    return ("stopped", None)
                continue
            except ContentFilter as e:
                rec.update({"outcome": "content_filter", "error": str(e), "cost_usd": 0.0})
                self.append(self.path(tag, "attempts.jsonl"), rec)
                return ("content_filter", e, attempts)
            except Halt as e:
                rec.update({"outcome": "halt", "error": str(e), "cost_usd": 0.0})
                self.append(self.path(tag, "attempts.jsonl"), rec)
                return ("halt", e, attempts)
            cost = self.cost_of(res)
            rec.update({"outcome": "response", "s": res["wall_s"], "cost_usd": cost,
                        "provider": res.get("provider"), "service_tier": res.get("service_tier"),
                        "reported_model": res.get("reported_model"), "finish": res["finish"],
                        "input_tokens": res.get("input_tokens"), "output_tokens": res.get("output_tokens"),
                        "reasoning_tokens": res.get("reasoning_tokens")})
            self.append(self.path(tag, "attempts.jsonl"), rec)
            attempts.append({"attempt": k, "outcome": "response"})
            try:
                self.check(res, side, prompt)
            except Halt as e:
                return ("halt", e, attempts, res, cost)
            return ("ok", res, attempts, cost)
        raise AssertionError("unreachable")

    # ---- one wave ------------------------------------------------------------

    def pending_halts(self, tag):
        f, a = self.path(tag, "check_failures.jsonl"), self.path(tag, "check_failures.resumed.jsonl")
        n = sum(1 for ln in open(f, encoding="utf-8") if ln.strip()) if os.path.exists(f) else 0
        m = sum(1 for ln in open(a, encoding="utf-8") if ln.strip()) if os.path.exists(a) else 0
        return n - m

    def done_ids(self, tag):
        out = set(_latest_rows(self.path(tag))) if os.path.exists(self.path(tag)) else set()
        cf = self.path(tag, "content_filter.jsonl")
        if os.path.exists(cf):
            out |= {json.loads(ln)["custom_id"] for ln in open(cf, encoding="utf-8") if ln.strip()}
        return out

    def run_wave(self, spec, base_wave):
        tag = spec["tag"]
        pend = self.pending_halts(tag)
        if pend:
            if not self.resume:
                raise SystemExit(f"STOP: {tag} has {pend} unreviewed halt(s) in "
                                 f"{self.path(tag, 'check_failures.jsonl')}; resume only on the user's "
                                 "instruction (--resume-after-check-failure).")
            for _ in range(pend):
                self.append(self.path(tag, "check_failures.resumed.jsonl"),
                            {"resumed_at": now(), "by": "user instruction"})
            self.log(f"{tag}: resumed after {pend} halt(s) on the user's instruction")
        done = self.done_ids(tag)
        todo = [r for r in spec["requests"] if make_custom_id(r["cell"], r["game"], r["unit"]) not in done]
        if done and todo:
            self.log(f"RESTART {tag}: {len(done)} done, {len(todo)} to send")
        self.log(f"{tag}: {len(spec['requests'])} requests, {len(todo)} to send; "
                 f"spent ${self.ledger.spent:.4f} of cap ${self.ledger.cap:.2f}")
        queue = deque(todo)
        not_run, halt = [], None
        futs = {}
        self.stop.clear()
        with ThreadPoolExecutor(max_workers=MAX_INFLIGHT) as ex:
            while queue or futs:
                while queue and len(futs) < MAX_INFLIGHT and not self.stop.is_set():
                    r = queue[0]
                    cid = make_custom_id(r["cell"], r["game"], r["unit"])
                    side = spec["sidecar"][cid]
                    if not self.ledger.try_reserve(cid, self.worst(side)):
                        if not futs:          # nothing will free budget: the rest is not run
                            not_run = list(queue)
                            queue.clear()
                        break
                    queue.popleft()
                    futs[ex.submit(self.one, tag, cid, side, r["prompt"])] = (cid, side, r)
                if not futs:
                    break
                fin, _ = wait(list(futs), timeout=5, return_when=FIRST_COMPLETED)
                for f in fin:
                    cid, side, r = futs.pop(f)
                    try:
                        out = f.result()
                    except Exception as e:                              # noqa: BLE001
                        out = ("halt", Halt(f"runner exception {type(e).__name__}: {e}"), [])
                    kind = out[0]
                    if kind == "ok":
                        _, res, atts, cost = out
                        self.ledger.settle(cid, cost)
                        row = row_from_result(cid, res, atts)
                        row["sonnet_input_tokens"] = self.sonnet_in.get(side["unit"])
                        row["prompt_chars"] = len(r["prompt"])
                        self.append(self.path(tag), row)
                        self.log(f"{tag} {cid}: {row['stop_reason']} in {row['usage']['input_tokens']} "
                                 f"out {row['usage']['output_tokens']} ${cost:.4f} {row.get('error', '')} "
                                 f"({res['wall_s']} s) total ${self.ledger.spent:.4f}")
                    elif kind == "errored":
                        self.ledger.settle(cid, 0.0)
                        self.append(self.path(tag), errored_row(cid, out[1], out[2]))
                        self.log(f"{tag} {cid}: ERRORED after {MAX_ATTEMPTS} attempts: {str(out[1])[:150]}")
                    elif kind == "content_filter":
                        self.ledger.settle(cid, 0.0)
                        self.append(self.path(tag, "content_filter.jsonl"),
                                    {"custom_id": cid, "at": now(), "error": str(out[1])})
                        self.log(f"{tag} {cid}: CONTENT FILTER (own outcome; never resent): {str(out[1])[:150]}")
                    elif kind == "halt":
                        cost = out[4] if len(out) > 4 else 0.0
                        self.ledger.settle(cid, cost)
                        rec = {"custom_id": cid, "at": now(), "check": str(out[1])}
                        if len(out) > 3:
                            rec["response"] = {k: v for k, v in out[3].items() if k != "usage_raw"}
                        self.append(self.path(tag, "check_failures.jsonl"), rec)
                        self.log(f"HALT {tag} {cid}: {out[1]}")
                        halt = halt or f"{cid}: {out[1]}"
                        self.stop.set()
                    else:                                               # stopped by a halt
                        self.ledger.settle(cid, 0.0)
        if halt:
            raise SystemExit(f"HALT in {tag}: {halt}")
        if not_run:
            ids = [make_custom_id(r["cell"], r["game"], r["unit"]) for r in not_run]
            for c in ids:
                self.append(self.path(tag, "not_run.jsonl"), {"custom_id": c, "at": now(),
                                                              "why": "cost cap", "spent": self.ledger.spent})
            self.log(f"{tag}: COST CAP: {len(ids)} requests not run (spent ${self.ledger.spent:.4f})")
            if base_wave:
                self.append(self.path(tag, "check_failures.jsonl"),
                            {"custom_id": ids[0], "at": now(),
                             "check": f"cost cap reached before the base wave finished ({len(ids)} not run)"})
                raise SystemExit(f"HALT: cost cap reached before {tag} finished; {len(ids)} not run")
        self.ratio_check(tag)
        return self.path(tag)

    def ratio_check(self, tag):
        rows = [r for r in _latest_rows(self.path(tag)).values()
                if r.get("result_type") == "succeeded" and r.get("prompt_chars")]
        if len(rows) < 2:
            return
        rat = [r["usage"]["input_tokens"] / r["prompt_chars"] for r in rows]
        spread = max(rat) / min(rat)
        self.log(f"{tag}: prompt tokens/char min {min(rat):.4f} max {max(rat):.4f} spread {spread:.3f}")
        if spread > 1.25:
            self.append(self.path(tag, "check_failures.jsonl"),
                        {"custom_id": "*", "at": now(), "check": f"tokens/char spread {spread:.3f} > 1.25"})
            raise SystemExit(f"HALT: {tag} prompt tokens/char spread {spread:.3f} > 1.25")

    def save_spec(self, spec):
        p = self.path(spec["tag"], "spec.json")
        if os.path.exists(p):
            if json.load(open(p, encoding="utf-8")) != json.loads(json.dumps(spec)):
                raise SystemExit(f"HALT: rebuilt {spec['tag']} differs from the saved spec {p}")
        else:
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(spec, fh, indent=1)

    # ---- the protocol ----------------------------------------------------------

    def ids_in(self, tag, kind):
        p = self.path(tag, kind)
        return {json.loads(ln)["custom_id"] for ln in open(p, encoding="utf-8") if ln.strip()} \
            if os.path.exists(p) else set()

    def run(self):
        import score_api
        cfg = self.cfg
        batch_game.MODEL_MAX_OUTPUT = cfg["budget"]
        self.log(f"=== start {cfg['slug']} headline J: budget {cfg['budget']}, cap ${cfg['cap']}, "
                 f"MODEL_MAX_OUTPUT {batch_game.MODEL_MAX_OUTPUT}")
        spec = json.load(open(HEADLINE_SPEC, encoding="utf-8"))
        tag = spec["tag"]
        files = [self.run_wave(spec, base_wave=True)]
        cf = self.ids_in(tag, "content_filter.jsonl")
        spec_s = score_api.subset(spec, drop_cids=cf)
        rs = batch_game.build_resubmit_spec(spec_s, files, tag + "-rs1")
        self.save_spec(rs)
        if rs["at_ceiling"]:
            self.log(f"{tag}: {len(rs['at_ceiling'])} D6 non-completions at the budget: {rs['at_ceiling']}")
        if rs["requests"]:
            files.append(self.run_wave(rs, base_wave=False))
        cf |= self.ids_in(tag + "-rs1", "content_filter.jsonl")
        nr = self.ids_in(tag + "-rs1", "not_run.jsonl")
        holes = {c for c in failed_ids(files) if c in spec["sidecar"]
                 and not batch_game.at_ceiling(_latest_rows(files)[c])}
        if holes:
            self.log(f"{tag}: {len(holes)} units not completed after the resend: {sorted(holes)}")
        spec_s = score_api.subset(spec, drop_cids=cf | nr | holes)
        rp = batch_game.build_repair_spec([(spec_s, files)], 1, 1, tag + "-r1")
        self.save_spec(rp)
        waves = [(spec_s, files)]
        if rp["requests"]:
            rfiles = [self.run_wave(rp, base_wave=False)]
            rcf = self.ids_in(rp["tag"], "content_filter.jsonl")
            rrs = batch_game.build_resubmit_spec(score_api.subset(rp, drop_cids=rcf | self.ids_in(
                rp["tag"], "not_run.jsonl")), rfiles, rp["tag"] + "-rs1")
            self.save_spec(rrs)
            if rrs["requests"]:
                rfiles.append(self.run_wave(rrs, base_wave=False))
            waves.append((rp, rfiles))
        self.log(f"=== waves done; spent ${self.ledger.spent:.4f}")
        return score_api.score_model(cfg["slug"])


# ── smoke test and balance ───────────────────────────────────────────────────

def long_dummy_prompt(target_chars=76000):
    """A neutral dummy prompt as long (in chars) as the longest headline prompt, pool_037 (75,956 chars); OpenRouter sizes prompts by chars (~3.97 chars/token) before routing.
    Not a headline prompt; used only for the amendment's provider smoke test."""
    words = ("river stone lantern meadow copper harbor violet thunder orchard ember canyon willow "
             "glacier saffron pebble falcon marble cedar drizzle quartz").split()
    lines, i = [], 0
    while sum(len(x) + 1 for x in lines) < target_chars:
        lines.append(f"Line {i:05d}: " + " ".join(words[(i * 7 + k) % len(words)] for k in range(9)) + ".")
        i += 1
    return "\n".join(lines) + "\n\nIgnore the list above. Reply with exactly the word OK and nothing else."


def smoke(cfg, long=False):
    r = ApiRunner(cfg)
    prompt = long_dummy_prompt() if long else SMOKE_PROMPT
    body = r.body(prompt)
    t0 = time.time()
    rec = {"slug": cfg["slug"], "at": now(), "long_prompt_chars": len(prompt) if long else None,
           "provider_pinned": cfg.get("provider_name"), "budget": cfg["budget"],
           "body_sent": {k: (v if k not in ("messages", "input") else "<dummy prompt>")
                         for k, v in body.items() if k not in ("model",) or cfg["api"] != "azure"}}
    try:
        res = r.send(body)
        rec["result"] = {k: v for k, v in res.items()}
        try:
            r.check(res, None, prompt)
            rec["checks"] = "pass"
        except Halt as e:
            rec["checks"] = f"FAIL: {e}"
        rec["cost_usd"] = r.cost_of(res)
    except Exception as e:                                              # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {e}"
    rec["s"] = round(time.time() - t0, 1)
    with open(os.path.join(SB, "logs", "smoke_tests.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
    show = {k: rec.get(k) for k in ("checks", "error", "cost_usd", "s")}
    if "result" in rec:
        show.update({k: rec["result"].get(k) for k in ("provider", "service_tier", "reported_model", "finish",
                                                       "input_tokens", "output_tokens", "reasoning_tokens")})
        show["text"] = (rec["result"].get("text") or "")[:120]
        show["reasoning_chars"] = len(rec["result"].get("reasoning") or "")
    print(json.dumps(show, indent=1))


def balance():
    key = env().get("OPENROUTER_API_KEY")
    r = httpx.get("https://openrouter.ai/api/v1/key", headers={"Authorization": f"Bearer {key}"}, timeout=60)
    d = r.json().get("data", {})
    out = {k: d.get(k) for k in ("usage", "limit", "limit_remaining", "is_free_tier")}
    out["at"] = now()
    with open(os.path.join(SB, "logs", "openrouter_balance.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(out) + "\n")
    print(json.dumps(out))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", nargs="?", choices=sorted(CONFIGS))
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--smoke-long", action="store_true", help="amendment smoke test: ~76k-char dummy prompt")
    ap.add_argument("--parasail-fallback", action="store_true", help="gpt-oss only: the amendment's fallback")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--balance", action="store_true")
    ap.add_argument("--cap", type=float, help="Kimi only: cap from the Kimi rule")
    ap.add_argument("--resume-after-check-failure", action="store_true")
    a = ap.parse_args()
    if a.balance:
        balance()
        return
    cfg = dict(CONFIGS[a.model])
    if a.cap is not None:
        assert a.model == "kimi-k2.5", "--cap is only for the Kimi rule"
        cfg["cap"] = a.cap
    if a.parasail_fallback:
        cfg = PARASAIL_FALLBACK[a.model]()
    if a.smoke or a.smoke_long:
        smoke(cfg, long=a.smoke_long)
    elif a.score:
        import score_api
        score_api.score_model(a.model)
    else:
        assert cfg["cap"] is not None, "no cap"
        ApiRunner(cfg, resume_after_check_failure=a.resume_after_check_failure).run()


if __name__ == "__main__":
    main()
