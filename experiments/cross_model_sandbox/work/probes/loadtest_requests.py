"""Made-up-prompt load test requests for a running llama-server (no frozen/ content).

Every request setting and body is built here in Python; nothing is passed through a
shell. Prompts are seeded synthetic "Note N: ..." lines, LF only, trimmed by the
server's own tokenizer to a target prompt length.

Per request it writes OUT_DIR/<name>.json with: tokenizer count of the rendered
prompt, the server's reported prompt tokens (asserted equal), finish reason, server
timings, and a streamed timeline (wall-clock time at every 1,000 generated tokens).

usage: python -I work/probes/loadtest_requests.py TEST_NAME OUT_DIR
"""
import json
import random
import sys
import time
import urllib.request
from pathlib import Path

# Gemma 4 12B, preregistration-draft sampling, thinking on.
GEMMA_SAMPLING = {"temperature": 1.0, "top_p": 0.95, "top_k": 64, "min_p": 0.0, "typical_p": 1.0,
                  "repeat_penalty": 1.0, "presence_penalty": 0.0, "frequency_penalty": 0.0,
                  "dry_multiplier": 0.0, "xtc_probability": 0.0, "top_n_sigma": -1.0,
                  "mirostat": 0, "dynatemp_range": 0.0, "seed": 42}
GEMMA_KWARGS = {"enable_thinking": True}

TESTS = {
    # 1) fill the 163,840 context: ~150k-token prompt, then decode at that depth
    "gemma-b-fill": {"port": 8092, "kwargs": GEMMA_KWARGS, "sampling": GEMMA_SAMPLING,
                     "prompt_tokens": 150000, "max_tokens": 8192, "ignore_eos": True},
    # 2) headline-sized prompt (~ the longest Gemma headline prompt, 19,563), then a
    #    long generation to see how speed falls with depth
    "gemma-b-long": {"port": 8092, "kwargs": GEMMA_KWARGS, "sampling": GEMMA_SAMPLING,
                     "prompt_tokens": 19563, "max_tokens": 50000, "ignore_eos": True},
}

# gpt-oss-20b, preregistration-draft sampling, reasoning high, pinned date.
GPTOSS_SAMPLING = {**GEMMA_SAMPLING, "top_p": 1.0, "top_k": 0}
GPTOSS_KWARGS = {"reasoning_effort": "high", "current_date": "2026-11-11"}
TESTS.update({
    # condition (3): one ordinary request (stops on its own), rendered prompt logged
    "gptoss-b-generic": {"port": 8091, "kwargs": GPTOSS_KWARGS, "sampling": GPTOSS_SAMPLING,
                         "prompt_tokens": 2000, "max_tokens": 4096, "ignore_eos": False},
    # fill: 98,304 - 8,192 generated - margin
    "gptoss-b-fill": {"port": 8091, "kwargs": GPTOSS_KWARGS, "sampling": GPTOSS_SAMPLING,
                      "prompt_tokens": 88000, "max_tokens": 8192, "ignore_eos": True},
    # longest gpt-oss headline prompt is 17,144 tokens
    "gptoss-b-long": {"port": 8091, "kwargs": GPTOSS_KWARGS, "sampling": GPTOSS_SAMPLING,
                      "prompt_tokens": 17144, "max_tokens": 50000, "ignore_eos": True},
    # one short ordinary request that should reach a final answer
    "gptoss-b-final": {"port": 8091, "kwargs": GPTOSS_KWARGS, "sampling": GPTOSS_SAMPLING,
                       "fixed_prompt": "What is 17 + 25? Reply with the number only.",
                       "max_tokens": 4096, "ignore_eos": False},
})

NOUNS = ['river', 'engine', 'library', 'garden', 'station', 'harbor', 'valley', 'market',
         'bridge', 'forest', 'tower', 'village']
VERBS = ['crossed', 'repaired', 'visited', 'painted', 'measured', 'described', 'opened', 'mapped']
ADJS = ['old', 'quiet', 'busy', 'narrow', 'bright', 'distant', 'small', 'large']
QUESTION = "\n\nQuestion: how many notes mention a bridge? Explain your count in detail.\n"


def make_prompt(n_lines):
    rng = random.Random(7)
    lines = [f"Note {i}: the {rng.choice(ADJS)} {rng.choice(NOUNS)} was {rng.choice(VERBS)} "
             f"by team {rng.randint(1, 40)} on day {rng.randint(1, 365)}." for i in range(1, n_lines + 1)]
    return "\n".join(lines) + QUESTION


def post(base, path, body, timeout=600):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def count(base, prompt, kwargs):
    msgs = [{"role": "user", "content": prompt}]
    rendered = post(base, "/apply-template", {"messages": msgs, "chat_template_kwargs": kwargs})["prompt"]
    return len(post(base, "/tokenize", {"content": rendered, "add_special": True,
                                        "parse_special": True})["tokens"])


def fit_prompt(base, target, kwargs):
    lo, hi = 1, 20000
    while lo < hi:  # largest line count whose rendered prompt is <= target tokens
        mid = (lo + hi + 1) // 2
        if count(base, make_prompt(mid), kwargs) <= target:
            lo = mid
        else:
            hi = mid - 1
    p = make_prompt(lo)
    return p, lo, count(base, p, kwargs)


def main():
    name, out_dir = sys.argv[1], Path(sys.argv[2])
    t = TESTS[name]
    base = f"http://127.0.0.1:{t['port']}"
    out_dir.mkdir(parents=True, exist_ok=True)
    if "fixed_prompt" in t:
        prompt, n_lines = t["fixed_prompt"], 0
        n_tok = count(base, prompt, t["kwargs"])
    else:
        prompt, n_lines, n_tok = fit_prompt(base, t["prompt_tokens"], t["kwargs"])
    body = {"messages": [{"role": "user", "content": prompt}], "chat_template_kwargs": t["kwargs"],
            "max_tokens": t["max_tokens"], "ignore_eos": t["ignore_eos"], "stream": True,
            "stream_options": {"include_usage": True}, **t["sampling"]}
    (out_dir / f"{name}.body_settings.json").write_text(
        json.dumps({k: v for k, v in body.items() if k != "messages"}, indent=1), encoding="utf-8")
    print(f"{name}: {n_lines} lines, {n_tok} prompt tokens, max_tokens {t['max_tokens']}", flush=True)

    req = urllib.request.Request(base + "/v1/chat/completions", data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    first = None
    n, timeline, final, usage, finish = 0, [], None, None, None
    n_reason, n_content = 0, 0
    reasoning_text, content_text = [], []
    with urllib.request.urlopen(req, timeout=4 * 3600) as r:
        for raw in r:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            ev = json.loads(line[6:])
            if ev.get("usage"):
                usage = ev["usage"]
            if ev.get("timings"):
                final = ev["timings"]
            for ch in ev.get("choices", []):
                d = ch.get("delta", {})
                if d.get("reasoning_content") or d.get("content"):
                    if first is None:
                        first = time.time() - t0
                    n += 1
                    n_reason += bool(d.get("reasoning_content"))
                    reasoning_text.append(d.get("reasoning_content") or "")
                    content_text.append(d.get("content") or "")
                    n_content += bool(d.get("content"))
                    if n % 1000 == 0:
                        timeline.append([n, round(time.time() - t0, 2)])
                        print(f"  {n} tokens at {timeline[-1][1]:.0f} s", flush=True)
                if ch.get("finish_reason"):
                    finish = ch["finish_reason"]
    wall = time.time() - t0
    res = {"test": name, "prompt_lines": n_lines, "tokenizer_count": n_tok,
           "reported_prompt_tokens": usage and usage.get("prompt_tokens"),
           "prompt_tokens_match": bool(usage) and usage.get("prompt_tokens") == n_tok,
           "completion_tokens": usage and usage.get("completion_tokens"), "stream_chunks": n,
           "reasoning_chunks": n_reason, "content_chunks": n_content, "finish_reason": finish,
           "time_to_first_token_s": first, "wall_s": round(wall, 1), "timings": final,
           "timeline_every_1000": timeline}
    if "fixed_prompt" in t:  # short request: keep the texts for inspection
        res["reasoning_text"] = "".join(reasoning_text)
        res["content_text"] = "".join(content_text)
    (out_dir / f"{name}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "timeline_every_1000"}, indent=1))
    assert res["prompt_tokens_match"], "reported prompt tokens != tokenizer count"


if __name__ == "__main__":
    main()
