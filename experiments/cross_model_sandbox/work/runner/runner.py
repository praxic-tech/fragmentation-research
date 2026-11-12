"""Headline Game J runner for a local llama-server model (post-hoc exploratory).

    python -I work/runner/runner.py MODEL_SLUG [--resume-after-check-failure]

MODEL_SLUG is a key of CONFIGS ("gemma-4-12b", "gpt-oss-20b"). The server must
already be running with the preregistered flags (work/probes/server_ctl.py).

Protocol (PREREGISTRATION.md), frozen functions only, in the order of
frozen/runs/final_run_steps123.py:

    base wave -> build_resubmit_spec (-rs1, transport holes once)
              -> build_repair_spec(..., 1, 1, tag + "-r1") -> its -rs1
              -> batch_game.score (+ allow_partial=True copy only if refused)

with batch_game.MODEL_MAX_OUTPUT set to the model's budget, so a call that stops
at max_tokens having used the whole budget is a D6 non-completion.

Rows are written in the format batch_submit.fetch wrote for Sonnet (row_from_response
mirrors it line by line), one appended row per request, flushed before the next call.

Restarts: a restarted runner skips every custom_id already in the wave's results
file; a request with no row is sent again as its first attempt; every restart is
logged. A failed per-call check stops the wave, writes NO results row, records the
failure in <tag>.check_failures.jsonl, and the runner refuses to continue until it
is started with --resume-after-check-failure (the user's instruction; logged).

The provider is anything with the LlamaServer interface; tests pass a fake.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

SB = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FROZEN = os.path.join(SB, "frozen")
for _d in ("adversaries", "harness", "analysis"):
    sys.path.insert(0, os.path.join(FROZEN, _d))

import batch_game                                                   # noqa: E402
from batch_submit import (IncompleteBatchError, TruncatedAnswerError,  # noqa: E402
                          ZeroAnswerError, _latest_rows, make_custom_id,
                          parse_custom_id)

HEADLINE_SPEC = os.path.join(FROZEN, "runs", "final_headlineJ.json")
REQUEST_TIMEOUT_S = 4 * 3600          # D4: a call still running after 4 h is a transport failure
SOCKET_TIMEOUT_S = 900

GEMMA_SAMPLING = {"temperature": 1.0, "top_p": 0.95, "top_k": 64, "min_p": 0.0, "typical_p": 1.0,
                  "repeat_penalty": 1.0, "presence_penalty": 0.0, "frequency_penalty": 0.0,
                  "dry_multiplier": 0.0, "xtc_probability": 0.0, "top_n_sigma": -1.0,
                  "mirostat": 0, "dynatemp_range": 0.0, "seed": 42}
GPTOSS_SAMPLING = {**GEMMA_SAMPLING, "top_p": 1.0, "top_k": 0}
GPTOSS_CONTROL = ["<|channel|>", "<|message|>", "<|start|>", "<|end|>", "<|return|>", "<|call|>",
                  "<|constrain|>"]
GEMMA_CONTROL = ["<|think|>", "<|channel>", "<channel|>", "<|turn>", "<turn|>"]

CONFIGS = {
    "gemma-4-12b": {
        "slug": "gemma-4-12b", "port": 8092, "ctx": 163840, "budget": 128000,
        "kwargs": {"enable_thinking": True}, "sampling": GEMMA_SAMPLING,
        "render_must_contain": ["<|think|>"], "control_tokens": GEMMA_CONTROL,
        "render_hashes": os.path.join(SB, "models", "gemma-4-12b", "headlineJ_render_sha256.json"),
        "log_prompts_dir": os.path.join(SB, "logs", "gemma-4-12b", "prompts")},
    "gpt-oss-20b": {
        "slug": "gpt-oss-20b", "port": 8091, "ctx": 98304, "budget": 78000,
        "kwargs": {"reasoning_effort": "high", "current_date": "2026-11-11"},
        "sampling": GPTOSS_SAMPLING,
        "render_must_contain": ["Current date: 2026-11-11", "Reasoning: high"],
        "control_tokens": GPTOSS_CONTROL,
        "render_hashes": os.path.join(SB, "models", "gpt-oss-20b", "headlineJ_render_sha256.json"),
        "log_prompts_dir": os.path.join(SB, "logs", "gpt-oss-20b", "prompts")},
}


class TransportError(RuntimeError):
    """The call itself failed (connection, HTTP 5xx, timeout, empty body): D4."""


class CheckFailure(RuntimeError):
    """A per-call check failed. The wave stops; no results row is written."""


# ── the real provider ────────────────────────────────────────────────────────

class LlamaServer:
    def __init__(self, port, host="127.0.0.1"):
        self.base = f"http://{host}:{port}"

    def _get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))

    def _post(self, path, body, timeout=600):
        req = urllib.request.Request(self.base + path, data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def health(self):
        return self._get("/health").get("status") == "ok"

    def props(self):
        return self._get("/props")

    def slots(self):
        return self._get("/slots")

    def apply_template(self, messages, kwargs):
        return self._post("/apply-template", {"messages": messages,
                                              "chat_template_kwargs": kwargs})["prompt"]

    def tokenize(self, text):
        return len(self._post("/tokenize", {"content": text, "add_special": True,
                                            "parse_special": True})["tokens"])

    def chat(self, body):
        """Stream one completion and return it in llama-server's non-stream shape:
        {"choices": [{"message": {"content", "reasoning_content"}, "finish_reason"}],
         "usage": {"prompt_tokens", "completion_tokens", ...}, "timings": {...}}."""
        req = urllib.request.Request(self.base + "/v1/chat/completions",
                                     data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        t0 = time.time()
        content, reasoning, usage, timings, finish = [], [], None, None, None
        try:
            with urllib.request.urlopen(req, timeout=SOCKET_TIMEOUT_S) as r:
                for raw in r:
                    if time.time() - t0 > REQUEST_TIMEOUT_S:
                        raise TransportError(f"timeout: still running after {REQUEST_TIMEOUT_S} s")
                    line = raw.decode("utf-8").strip()
                    if not line.startswith("data: ") or line == "data: [DONE]":
                        continue
                    ev = json.loads(line[6:])
                    if ev.get("error"):
                        raise TransportError(f"server error in stream: {ev['error']}")
                    usage = ev.get("usage") or usage
                    timings = ev.get("timings") or timings
                    for ch in ev.get("choices", []):
                        d = ch.get("delta") or {}
                        content.append(d.get("content") or "")
                        reasoning.append(d.get("reasoning_content") or "")
                        finish = ch.get("finish_reason") or finish
        except urllib.error.HTTPError as e:
            if e.code >= 500:
                raise TransportError(f"HTTP {e.code}: {e.read()[:300]!r}") from None
            raise CheckFailure(f"HTTP {e.code} (request refused): {e.read()[:300]!r}") from None
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
            raise TransportError(f"{type(e).__name__}: {e}") from None
        if usage is None or finish is None:
            raise TransportError("empty body: stream ended without usage or finish_reason")
        return {"choices": [{"index": 0, "finish_reason": finish,
                             "message": {"role": "assistant", "content": "".join(content),
                                         "reasoning_content": "".join(reasoning)}}],
                "usage": usage, "timings": timings, "wall_s": round(time.time() - t0, 1)}


# ── rows: exactly what batch_submit.fetch wrote for Sonnet ───────────────────

STOP_REASON = {"stop": "end_turn", "length": "max_tokens"}


def now():
    return datetime.now(timezone.utc).isoformat()


def row_from_response(cid, resp, fetched_at=None):
    """One results row from a llama-server response (non-stream shape).

    Mirrors batch_submit.fetch: stop at max_tokens -> TruncatedAnswerError with the
    text kept as partial_text; empty answer -> ZeroAnswerError; otherwise text.
    usage keeps llama-server's counts and adds the names the frozen code reads
    (input_tokens, output_tokens). Reasoning goes in "reasoning", never in text.
    """
    ch = resp["choices"][0]
    msg = ch.get("message") or {}
    text = msg.get("content") or ""
    u = resp["usage"]
    row = {"custom_id": cid, **parse_custom_id(cid), "fetched_at": fetched_at or now(),
           "result_type": "succeeded"}
    row["usage"] = {**u, "input_tokens": u["prompt_tokens"], "output_tokens": u["completion_tokens"]}
    row["stop_reason"] = STOP_REASON[ch["finish_reason"]]
    if row["stop_reason"] == "max_tokens":
        row["error"] = TruncatedAnswerError.__name__
        row["detail"] = f"stopped at max_tokens after {u['completion_tokens']} output tokens"
        if text.strip():
            row["partial_text"] = text
    elif not text.strip():
        row["error"] = ZeroAnswerError.__name__
        row["detail"] = (f"empty answer after {u['completion_tokens']} output tokens - "
                         "all reasoning, no answer")
    else:
        row["text"] = text
    row["reasoning"] = msg.get("reasoning_content") or ""
    row["finish_reason"] = ch["finish_reason"]
    for k in ("timings", "wall_s"):
        if resp.get(k) is not None:
            row[k] = resp[k]
    return row


def errored_row(cid, err, fetched_at=None):
    return {"custom_id": cid, **parse_custom_id(cid), "fetched_at": fetched_at or now(),
            "result_type": "errored", "error": f"{type(err).__name__}: {err}"}


# ── the run ──────────────────────────────────────────────────────────────────

class Runner:
    def __init__(self, cfg, provider, raw_dir=None, results_dir=None, log_path=None,
                 resume_after_check_failure=False, spec_path=HEADLINE_SPEC, out=print):
        self.cfg, self.p = cfg, provider
        slug = cfg["slug"]
        self.raw_dir = raw_dir or os.path.join(SB, "raw", slug)
        self.results_dir = results_dir or os.path.join(SB, "results", slug)
        self.log_path = log_path or os.path.join(SB, "logs", slug, "run.log")
        self.resume = resume_after_check_failure
        self.spec_path, self.out = spec_path, out
        hashes = json.load(open(cfg["render_hashes"], encoding="utf-8"))
        assert hashes["summary"]["ok"], "render-hash file did not pass its own checks"
        self.hashes = {r["unit"]: r["sha256"] for r in hashes["rows"]}
        for d in (self.raw_dir, os.path.dirname(self.log_path), cfg["log_prompts_dir"]):
            os.makedirs(d, exist_ok=True)

    def log(self, msg):
        line = f"{now()} {msg}"
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        self.out(line)

    def path(self, tag, kind="results.jsonl"):
        return os.path.join(self.raw_dir, f"{tag}.{kind}")

    # ---- per-call checks -------------------------------------------------

    def body(self, prompt):
        return {"messages": [{"role": "user", "content": prompt}],
                "chat_template_kwargs": self.cfg["kwargs"], "max_tokens": self.cfg["budget"],
                "stream": True, "stream_options": {"include_usage": True}, **self.cfg["sampling"]}

    def pre_checks(self, side, req, body):
        cfg = self.cfg
        try:
            if not self.p.health():
                raise CheckFailure("server not healthy")
            props, slots = self.p.props(), self.p.slots()
            render = self.p.apply_template(body["messages"], body["chat_template_kwargs"])
            n_tok = self.p.tokenize(render)
        except CheckFailure:
            raise
        except Exception as e:                                  # noqa: BLE001
            raise CheckFailure(f"server unreachable before the call: {type(e).__name__}: {e}") from None
        if props.get("total_slots") != 1 or len(slots) != 1:
            raise CheckFailure(f"expected one slot: props {props.get('total_slots')}, slots {len(slots)}")
        n_ctx = (props.get("default_generation_settings") or {}).get("n_ctx")
        if n_ctx != cfg["ctx"] or slots[0].get("n_ctx") != cfg["ctx"]:
            raise CheckFailure(f"n_ctx {n_ctx}/{slots[0].get('n_ctx')} != {cfg['ctx']}")
        if req["prompt"] not in render:
            raise CheckFailure("render does not contain the request prompt verbatim")
        if "\r" in render:
            raise CheckFailure("render contains CR")
        for s in cfg["render_must_contain"]:
            if s not in render:
                raise CheckFailure(f"render lacks {s!r}")
        sha = hashlib.sha256(render.encode("utf-8")).hexdigest()
        if side["round"] == 0 and self.hashes.get(side["unit"]) != sha:
            raise CheckFailure(f"render SHA-256 {sha[:16]} != stored {str(self.hashes.get(side['unit']))[:16]}")
        if n_tok + cfg["budget"] > cfg["ctx"]:
            raise CheckFailure(f"does not fit: {n_tok} prompt + {cfg['budget']} budget > {cfg['ctx']}")
        return render, sha, n_tok

    def logged_prompts(self):
        d = self.cfg["log_prompts_dir"]
        return {f: os.stat(os.path.join(d, f)).st_mtime_ns for f in os.listdir(d)}

    def post_checks(self, resp, render, n_tok, before):
        cfg = self.cfg
        u, ch = resp["usage"], resp["choices"][0]
        if u.get("prompt_tokens") != n_tok:
            raise CheckFailure(f"reported prompt_tokens {u.get('prompt_tokens')} != tokenizer {n_tok}")
        if ch.get("finish_reason") not in STOP_REASON:
            raise CheckFailure(f"finish_reason {ch.get('finish_reason')!r}")
        if ch["finish_reason"] == "length" and u.get("completion_tokens") != cfg["budget"]:
            raise CheckFailure(f"stopped at length after {u.get('completion_tokens')} tokens, "
                               f"not at the budget {cfg['budget']}")
        text = (ch.get("message") or {}).get("content") or ""
        leaked = [t for t in cfg["control_tokens"] if t in text]
        if leaked:
            raise CheckFailure(f"answer text contains control tokens {leaked}")
        after = self.logged_prompts()
        new = [f for f, m in after.items() if before.get(f) != m]
        if len(new) != 1:
            raise CheckFailure(f"expected one new logged prompt, found {len(new)}")
        with open(os.path.join(cfg["log_prompts_dir"], new[0]), "rb") as fh:
            logged = fh.read().decode("utf-8").replace("\r\n", "\n")
        if logged != render:
            raise CheckFailure(f"logged prompt {new[0]} differs from the render")
        try:
            slot = self.p.slots()[0]["params"]
        except Exception as e:                                  # noqa: BLE001
            raise CheckFailure(f"/slots unreadable after the call: {e}") from None
        want = {**cfg["sampling"], "max_tokens": cfg["budget"]}
        bad = {k: (slot.get(k), v) for k, v in want.items()
               if not isinstance(slot.get(k), (int, float)) or abs(slot[k] - v) > 1e-6}
        if bad:
            raise CheckFailure(f"/slots params differ from those sent: {bad}")
        return new[0]

    # ---- one wave ----------------------------------------------------------

    def check_failures_pending(self, tag):
        fails = self.path(tag, "check_failures.jsonl")
        acks = self.path(tag, "check_failures.resumed.jsonl")
        n = sum(1 for ln in open(fails, encoding="utf-8") if ln.strip()) if os.path.exists(fails) else 0
        k = sum(1 for ln in open(acks, encoding="utf-8") if ln.strip()) if os.path.exists(acks) else 0
        return n - k

    def run_wave(self, spec):
        tag, out_path = spec["tag"], self.path(spec["tag"])
        pending = self.check_failures_pending(tag)
        if pending:
            if not self.resume:
                raise SystemExit(f"STOP: {tag} has {pending} unreviewed check failure(s) in "
                                 f"{self.path(tag, 'check_failures.jsonl')}. Resume only on the "
                                 "user's instruction (--resume-after-check-failure).")
            for _ in range(pending):
                with open(self.path(tag, "check_failures.resumed.jsonl"), "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"resumed_at": now(), "by": "user instruction"}) + "\n")
            self.log(f"{tag}: resumed after {pending} check failure(s) on the user's instruction")
        present = set(_latest_rows(out_path)) if os.path.exists(out_path) else set()
        todo = [r for r in spec["requests"]
                if make_custom_id(r["cell"], r["game"], r["unit"]) not in present]
        if present and todo:
            self.log(f"RESTART {tag}: {len(present)} rows already present, {len(todo)} requests to send")
        self.log(f"{tag}: {len(spec['requests'])} requests, {len(todo)} to send")
        for r in todo:
            cid = make_custom_id(r["cell"], r["game"], r["unit"])
            side = spec["sidecar"][cid]
            body, resp = self.body(r["prompt"]), None
            try:
                render, sha, n_tok = self.pre_checks(side, r, body)
                before = self.logged_prompts()
                t0 = time.time()
                try:
                    resp = self.p.chat(body)
                except TransportError as e:
                    row = errored_row(cid, e)
                else:
                    logged = self.post_checks(resp, render, n_tok, before)
                    row = row_from_response(cid, resp)
                    row.update({"render_sha256": sha, "tokenizer_prompt_tokens": n_tok,
                                "logged_prompt_file": logged})
            except CheckFailure as e:
                rec = {"custom_id": cid, "at": now(), "check": str(e)}
                if resp is not None:
                    rec["response"] = resp
                with open(self.path(tag, "check_failures.jsonl"), "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec) + "\n")
                self.log(f"CHECK FAILED {tag} {cid}: {e}. Wave stopped; no row written.")
                raise SystemExit(f"STOP: check failed on {cid}: {e}")
            with open(out_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            self.log(f"{tag} {cid}: {row['result_type']} {row.get('stop_reason', '')} "
                     f"{(row.get('usage') or {}).get('output_tokens', '-')} out "
                     f"{row.get('error', '')[:60]} ({time.time() - t0:.0f} s)")
        return out_path

    def save_spec(self, spec):
        """Specs built during the run are saved; a rebuilt one must match."""
        p = self.path(spec["tag"], "spec.json")
        if os.path.exists(p):
            if json.load(open(p, encoding="utf-8")) != json.loads(json.dumps(spec)):
                raise SystemExit(f"STOP: rebuilt {spec['tag']} differs from the saved spec {p}")
        else:
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(spec, fh, indent=1)

    # ---- the protocol ------------------------------------------------------

    def run(self):
        cfg = self.cfg
        batch_game.MODEL_MAX_OUTPUT = cfg["budget"]
        self.log(f"=== start {cfg['slug']} headline J: ctx {cfg['ctx']}, budget {cfg['budget']}, "
                 f"MODEL_MAX_OUTPUT {batch_game.MODEL_MAX_OUTPUT}")
        spec = json.load(open(self.spec_path, encoding="utf-8"))
        tag = spec["tag"]
        files = [self.run_wave(spec)]
        rs = batch_game.build_resubmit_spec(spec, files, tag + "-rs1")
        self.save_spec(rs)
        if rs["at_ceiling"]:
            self.log(f"{tag}: {len(rs['at_ceiling'])} D6 non-completions at the budget, not re-asked: "
                     f"{rs['at_ceiling']}")
        if rs["requests"]:
            files.append(self.run_wave(rs))
        waves = [(spec, files)]
        try:
            rp = batch_game.build_repair_spec([(spec, files)], 1, 1, tag + "-r1")
        except IncompleteBatchError as e:
            self.log(f"{tag}: holes remain after the resend; no repair round; the gate will refuse ({e})")
            rp = None
        if rp is not None:
            self.save_spec(rp)
            if rp["requests"]:
                rfiles = [self.run_wave(rp)]
                rrs = batch_game.build_resubmit_spec(rp, rfiles, rp["tag"] + "-rs1")
                self.save_spec(rrs)
                if rrs["requests"]:
                    rfiles.append(self.run_wave(rrs))
                waves.append((rp, rfiles))
        return self.score(waves)

    def score(self, waves):
        out = os.path.join(self.results_dir, "final_headlineJ")
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                verdict = batch_game.score(waves, out)
        except IncompleteBatchError as e:
            verdict = {"not scored": str(e)}
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "REPORT.txt"), "w", encoding="utf-8") as fh:
            fh.write(buf.getvalue())
        verdict = {c: sorted(v) if isinstance(v, (set, frozenset, list)) else v for c, v in verdict.items()}
        with open(os.path.join(out, "verdict.json"), "w", encoding="utf-8") as fh:
            json.dump({"verdict": verdict, "budget": self.cfg["budget"],
                       "waves": [[w[0]["tag"], [os.path.basename(f) for f in w[1]]] for w in waves]},
                      fh, indent=1)
        refused = {c: v for c, v in verdict.items() if v}
        self.log(f"scored -> {out}; refused: {refused or 'none'}")
        if refused and "not scored" not in verdict:
            # Secondary only (preregistered): the gate's refusal above is the primary result.
            out2 = os.path.join(self.results_dir, "final_headlineJ_answered_units_only")
            buf2 = io.StringIO()
            with contextlib.redirect_stdout(buf2):
                batch_game.score(waves, out2, allow_partial=True)
            with open(os.path.join(out2, "REPORT.txt"), "w", encoding="utf-8") as fh:
                fh.write("SECONDARY: answered units only (allow_partial=True). The integrity gate "
                         "refused this game; that refusal is the primary result.\n\n" + buf2.getvalue())
            self.log(f"secondary (answered units only) -> {out2}")
        return verdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", choices=sorted(CONFIGS))
    ap.add_argument("--resume-after-check-failure", action="store_true")
    a = ap.parse_args()
    cfg = CONFIGS[a.model]
    Runner(cfg, LlamaServer(cfg["port"]), resume_after_check_failure=a.resume_after_check_failure).run()


if __name__ == "__main__":
    main()
