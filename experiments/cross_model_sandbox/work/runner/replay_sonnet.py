"""Replay Sonnet's headline answers through the runner. NO MODEL CALLS.

    python -I work/runner/replay_sonnet.py

Sonnet's raw headline rows (frozen/results/batches/final-headlineJ*.results.jsonl)
are converted into llama-server's response format (prompt_tokens, completion_tokens,
finish_reason, content, reasoning_content; a transport-failed row becomes a
TransportError). A fake llama-server hands them back to the runner, which runs its
real per-call checks, writes its own rows, builds the resend and repair waves with
the frozen functions and scores with the frozen batch_game.score, all into a
temporary directory.

It passes only if
  1. the runner asked for exactly what Sonnet was asked, wave by wave
     (46 base, the same 6 resends, the same 2 repairs with the same prompts);
  2. every row the runner wrote agrees with Sonnet's (result type, stop reason,
     text, input and output tokens);
  3. every unit's final answer equals the committed scored row; and
  4. F1_J, F1_L and q equal KEY_NUMBERS.json (0.7225, 0.8817, 0.8206) to 1e-9.
"""
import hashlib
import json
import os
import shutil
import statistics as st
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runner as R                                               # noqa: E402
import batch_game                                                # noqa: E402
from batch_submit import _latest_rows, make_custom_id            # noqa: E402
from joint_game import build_units, score_row                    # noqa: E402

B = os.path.join(R.FROZEN, "results", "batches")
SONNET_FILES = {"final-headlineJ": "final-headlineJ.results.jsonl",
                "final-headlineJ-rs1": "final-headlineJ-rs1.results.jsonl",
                "final-headlineJ-r1": "final-headlineJ-r1.results.jsonl"}
FINISH = {"end_turn": "stop", "max_tokens": "length"}


def sonnet_to_llama(row):
    """A Sonnet raw row in llama-server's (non-stream) response format."""
    if row["result_type"] != "succeeded":
        raise R.TransportError(row.get("error", row["result_type"]))
    u = row["usage"]
    return {"choices": [{"index": 0, "finish_reason": FINISH[row["stop_reason"]],
                         "message": {"role": "assistant",
                                     "content": row.get("text", row.get("partial_text", "")),
                                     "reasoning_content": ""}}],
            "usage": {"prompt_tokens": u["input_tokens"], "completion_tokens": u["output_tokens"],
                      "total_tokens": u["input_tokens"] + u["output_tokens"]}}


def render(prompt):
    """The fake server's chat template (Gemma-shaped, with the <|think|> system turn)."""
    return "<|turn>system\n<|think|><turn|>\n<|turn>user\n" + prompt + "<turn|>\n<|turn>model\n"


class FakeLlamaServer:
    """The LlamaServer interface over a table of prepared answers."""

    def __init__(self, cfg, answers, tokens):
        self.cfg, self.answers, self.tokens = cfg, answers, tokens
        self.params, self.n_log, self.sent = {}, 0, []
        self.fail_at = None                 # call number at which to simulate a crash
        self.tamper = None                  # fn(prompt, resp) -> resp, for fault tests

    def health(self):
        return True

    def props(self):
        return {"total_slots": 1, "default_generation_settings": {"n_ctx": self.cfg["ctx"]}}

    def slots(self):
        return [{"id": 0, "n_ctx": self.cfg["ctx"], "params": self.params}]

    def apply_template(self, messages, kwargs):
        assert len(messages) == 1 and messages[0]["role"] == "user"
        return render(messages[0]["content"])

    def tokenize(self, text):
        prompt = text[len(render("")) - len("<turn|>\n<|turn>model\n"):-len("<turn|>\n<|turn>model\n")]
        return self.tokens(prompt)

    def chat(self, body):
        prompt = body["messages"][0]["content"]
        self.sent.append(prompt)
        if self.fail_at is not None and len(self.sent) == self.fail_at:
            raise KeyboardInterrupt("simulated crash mid-call")
        self.params = {k: body[k] for k in (*self.cfg["sampling"], "max_tokens")}
        self.n_log += 1
        with open(os.path.join(self.cfg["log_prompts_dir"], f"{self.n_log:012d}.txt"), "w",
                  encoding="utf-8") as fh:                      # text mode: \n -> \r\n, as the server
            fh.write(render(prompt))
        resp = self.answers(prompt)
        return self.tamper(prompt, resp) if self.tamper else resp


def sonnet_oracle(cfg):
    """(answers, tokens, expected) built from Sonnet's own files, independently of the runner."""
    spec = json.load(open(R.HEADLINE_SPEC, encoding="utf-8"))
    rows = {t: _latest_rows(os.path.join(B, f)) for t, f in SONNET_FILES.items()}
    saved = batch_game.MODEL_MAX_OUTPUT
    batch_game.MODEL_MAX_OUTPUT = 128000
    try:
        rp = batch_game.build_repair_spec(
            [(spec, [os.path.join(B, SONNET_FILES["final-headlineJ"]),
                     os.path.join(B, SONNET_FILES["final-headlineJ-rs1"])])], 1, 1, "final-headlineJ-r1")
    finally:
        batch_game.MODEL_MAX_OUTPUT = saved
    by_prompt = {}
    for r in spec["requests"]:
        by_prompt[r["prompt"]] = ("base", make_custom_id(r["cell"], r["game"], r["unit"]))
    for r in rp["requests"]:
        by_prompt[r["prompt"]] = ("repair", make_custom_id(r["cell"], r["game"], r["unit"]))
    calls = {}

    def which_row(prompt, advance):
        kind, cid = by_prompt[prompt]
        n = calls.get(cid, 0)
        if advance:
            calls[cid] = n + 1
        if kind == "repair":
            return rows["final-headlineJ-r1"][cid]
        if n == 0 or cid not in rows["final-headlineJ-rs1"]:   # (the latter only in fault tests)
            return rows["final-headlineJ"][cid]
        return rows["final-headlineJ-rs1"][cid]

    def answers(prompt):
        return sonnet_to_llama(which_row(prompt, True))

    def tokens(prompt):
        kind, cid = by_prompt[prompt]
        row = which_row(prompt, False)
        if row["result_type"] != "succeeded":       # its resend carries the count
            row = rows["final-headlineJ-rs1"][cid]
        return row["usage"]["input_tokens"]

    return spec, answers, tokens, rows, rp


def replay_cfg(tmp):
    cfg = {**R.CONFIGS["gemma-4-12b"], "slug": "sonnet-replay",
           "control_tokens": R.GEMMA_CONTROL + R.GPTOSS_CONTROL,
           "render_hashes": os.path.join(tmp, "render_sha256.json"),
           "log_prompts_dir": os.path.join(tmp, "prompts")}
    spec = json.load(open(R.HEADLINE_SPEC, encoding="utf-8"))
    hrows = [{"unit": r["unit"], "sha256": hashlib.sha256(render(r["prompt"]).encode("utf-8")).hexdigest()}
             for r in spec["requests"]]
    with open(cfg["render_hashes"], "w", encoding="utf-8") as fh:
        json.dump({"summary": {"ok": True}, "rows": hrows}, fh)
    return cfg


def make_runner(tmp, server, cfg, **kw):
    return R.Runner(cfg, server, raw_dir=os.path.join(tmp, "raw"), results_dir=os.path.join(tmp, "results"),
                    log_path=os.path.join(tmp, "run.log"), out=lambda m: None, **kw)


def compare_rows(tmp, sonnet_rows):
    """Runner rows vs Sonnet rows, file by file."""
    for tag, want in sonnet_rows.items():
        got = _latest_rows(os.path.join(tmp, "raw", f"{tag}.results.jsonl"))
        assert set(got) == set(want), f"{tag}: runner sent {sorted(set(got) ^ set(want))[:4]} differently"
        for cid, w in want.items():
            g = got[cid]
            assert g["result_type"] == w["result_type"], (tag, cid, "result_type")
            if w["result_type"] != "succeeded":
                assert "error" in g, (tag, cid)
                continue
            for k in ("stop_reason", "text"):
                assert g.get(k) == w.get(k), (tag, cid, k)
            for k in ("input_tokens", "output_tokens"):
                assert g["usage"][k] == w["usage"][k], (tag, cid, k)
    extra = sorted(f for f in os.listdir(os.path.join(tmp, "raw"))
                   if f.endswith(".results.jsonl") and f[:-len(".results.jsonl")] not in sonnet_rows)
    assert not extra, f"runner wrote waves Sonnet did not have: {extra}"
    return {t: len(v) for t, v in sonnet_rows.items()}


def headline_numbers(results_dir, spec):
    path = os.path.join(results_dir, "final_headlineJ", "prose", "J.jsonl")
    mine = {r["unit"]: r for r in map(json.loads, open(path, encoding="utf-8"))}
    ref = {r["unit"]: r for r in map(json.loads, open(
        os.path.join(R.FROZEN, "results", "final", "headlineJ", "prose", "J.jsonl"), encoding="utf-8"))}
    assert set(mine) == set(ref), "different units"
    diff = [u for u in ref if mine[u]["raw_response"] != ref[u]["raw_response"]]
    assert not diff, f"final answers differ for {diff[:5]}"
    f1, fl, q = [], [], []
    for pid, members in spec["build"]["pools"]:
        _o, _u, key, truth = build_units(os.path.join(R.FROZEN, "data", "prose"), 0, len(members), 42,
                                         pools=[(pid, members)], o_docs=[])
        s = score_row(mine[pid], key, truth)
        f1.append(s["joint_f1"])
        fl.append(s["j_linkage_f1"])
        q.append(s["q"])
    return len(mine), {"F1_J_mean": st.fmean(f1), "F1_L_mean": st.fmean(fl), "q_mean": st.fmean(q)}


def main():
    tmp = tempfile.mkdtemp(prefix="replay_sonnet_")
    try:
        cfg = replay_cfg(tmp)
        spec, answers, tokens, sonnet_rows, rp = sonnet_oracle(cfg)
        server = FakeLlamaServer(cfg, answers, tokens)
        verdict = make_runner(tmp, server, cfg).run()
        assert not any(verdict.values()), f"gate refused: {verdict}"
        counts = compare_rows(tmp, sonnet_rows)
        print(f"1-2. runner waves and rows agree with Sonnet's: {counts}; "
              f"{len(server.sent)} calls; repair prompts equal Sonnet's ({len(rp['requests'])})")
        n, got = headline_numbers(os.path.join(tmp, "results"), spec)
        kn = json.load(open(os.path.join(R.FROZEN, "results", "final_analysis", "KEY_NUMBERS.json"),
                            encoding="utf-8"))["headline"]["One-shot Sonnet"]
        print(f"3. {n} units; every final answer equals the committed scored row")
        for k, v in got.items():
            assert abs(v - kn[k]) < 1e-9, f"{k}: {v} vs {kn[k]}"
        want = {"F1_J_mean": 0.7225, "F1_L_mean": 0.8817, "q_mean": 0.8206}
        for k, v in want.items():
            assert round(got[k], 4) == v, f"{k}: {got[k]:.4f} vs required {v}"
        print("4. " + ", ".join(f"{k} {v:.4f}" for k, v in got.items()) + " (= KEY_NUMBERS.json to 1e-9)")
        print("REPLAY PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
