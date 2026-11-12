# DRAFT preregistration entries: Gemma 4 12B and gpt-oss-20b (for review)

Status: draft for review, 2026-11-12. Nothing here is preregistered until the
reviewed text is copied into `PREREGISTRATION.md` and committed. No study
request has been sent to either model. Order of runs: Gemma 4 12B first, then
gpt-oss-20b (see "Order between models").

## Decisions taken (formerly open)

**D-A. Output budget and context length: Option B for both.** Sonnet's 46
first-pass headline answers (40 base rows + 6 transport resends) used 29,892
to 81,897 output tokens: median 49,594, 43/46 above 32,768, 30/46 above
44,000, 8/46 above 64,000, none at its 128,000 ceiling. A 32,768 budget would
make most requests D6 non-completions if a model reasons at that length.

| model | context `-c` | output budget | trained context | headroom over max prompt + budget | load test (made-up prompts) |
|---|---|---|---|---|---|
| Gemma 4 12B | 163,840 | 128,000 (= Sonnet's) | 262,144 | 16,277 | no spill; process peak 10.2 GB dedicated |
| gpt-oss-20b | 98,304 | 78,000 | 131,072 | 3,160 | spills ~2 GB to shared memory; accepted (Entry 1, "GPU placement") |

Measured worst-case time (longest headline prompt, answer at the budget):
Gemma 41.3 min per answer, a 46-request wave <= 31.7 h; gpt-oss 39.2 min per
answer, a 46-request wave <= 30.0 h (answers at the budget are D6 and never
re-asked). Absolute ceiling if every answer ends just under the budget and its
repair runs to the budget: Gemma 63.3 h, gpt-oss 60.0 h.

**D-B. Pinned date for gpt-oss.** `current_date` = `2026-11-11`. Any constant
works; it only has to be fixed and recorded.

**C-1 (gpt-oss), done.** One generic request through the fixed-date template
with `--log-prompts-dir`: the logged prompt contains "Current date: 2026-11-11"
and "Reasoning: high"; the final answer ("42") came back in `content`, the
reasoning separately in `reasoning_content`; `/slots` shows every sampler value
below as sent. Record: `logs/RUNLOG.md`.

---

## Entry 1: gpt-oss-20b (DRAFT)

- **Date committed:** (on commit)
- **Label:** post-hoc exploratory cross-model robustness check. Not part of the
  prespecified design; does not revise any Sonnet result.
- **Model / weights:** OpenAI gpt-oss-20b (open weights, Apache-2.0). GGUF
  `gpt-oss-20b-MXFP4.gguf` from Hugging Face `ggml-org/gpt-oss-20b-GGUF`
  (the llama.cpp project's conversion; OpenAI publishes no GGUF), revision
  `15dcfc7e7c608c6161507211ed43c5b590801b4b`, 12,109,566,624 bytes, SHA-256
  `27cd6c432c7672cb812a92f611cf3ba7bbc35928262bb1e1253ff4ee6ae35901` (matches
  the HF LFS listing). Quantization: MXFP4, the format the weights were released in.
- **Runtime:** llama.cpp build b12110 (commit cd959bae9), Vulkan backend, Windows
  x64 zip `llama-b12110-bin-win-vulkan-x64.zip`, SHA-256
  `9732a5e48887ca54d0bfe4af4324dc85fd56cd8cda19b52df3542fa6ebe6874f`;
  `llama-server`. GPU: AMD Radeon RX 9070 XT (Vulkan0 only), driver
  32.0.32015.7029 (Adrenalin 26.10.1), Windows 11 Pro 10.0.26200.
- **Server flags (fixed):** `-m <gguf> -dev Vulkan0 -ngl 99 -c 98304 -np 1
  -fit off --jinja --reasoning-format auto --no-cache-prompt --cache-ram 0
  --chat-template-file work/templates/gpt-oss-20b.fixed-date.jinja
  --log-prompts-dir <run log dir>`. `-np 1`: one slot holds the whole context.
  `-fit off`: llama.cpp may not shrink context or offload. Prompt cache off.
- **GPU placement (known, accepted):** llama.cpp places all 25 layers and the
  whole KV cache on Vulkan0 (model 10,949 MiB + KV 2,304 + 18 + compute 187 =
  13,458 MiB; f16 KV, not quantized). Windows gives the llama-server process
  at most ~11.7 GB of dedicated VRAM, and about 2 GB of its GPU allocations
  sit in shared system memory (process dedicated 11,699 MiB, shared 2,041 MiB
  in the load test at these flags). This changes speed, not answers, and is
  accepted. Evidence, decode speed by depth (made-up prompts, these flags,
  display on the same GPU):

  | depth (tokens) | 3.5k | 21k | 36k | 51k | 66k | 93k | 95k |
  |---|---|---|---|---|---|---|---|
  | tok/s | 122 | 66 | 47 | 36 | 30 | 21.8 | 21.4 |

  ms/token = 6.35 + 0.000422 x depth (max residual 0.41 ms). One answer at
  the budget from the longest prompt: 39.2 min; 46 requests all at the
  budget: 30.0 h. Recorded in `logs/RUNLOG.md`. The run log records process
  dedicated and shared memory during the run; a run whose placement differs
  materially from this (shared above ~2.3 GB) is reported.
- **Chat template:** the GGUF's embedded template (SHA-256
  `b2215de6da8ba369957eece8c5aa18f4af94f6c4d311d85e691373a421d80e89`, saved as
  `work/templates/gpt-oss-20b.embedded.jinja`) with one change: the line
  `"Current date: " + strftime_now("%Y-%m-%d")` reads `current_date` from
  `chat_template_kwargs` instead (missing → "PINNED-DATE-MISSING"). Result:
  `work/templates/gpt-oss-20b.fixed-date.jinja`, SHA-256
  `56290db74923ae982fde0edab1dfdb4c3421d7deb1e643fd945b0ef0c01259f5`, made by
  `work/templates/make_gpt_oss_fixed_date.py`.
  `chat_template_kwargs = {"reasoning_effort": "high", "current_date": "2026-11-11"}`.
- **Messages:** exactly one user message whose content is `request["prompt"]`
  from the frozen spec, verbatim, as Sonnet received it (`batch_submit.py:199`
  sent no system message). The only system content is the template's own
  system block ("You are ChatGPT ... Knowledge cutoff: 2024-06 / Current date:
  2026-11-11 / Reasoning: high / # Valid channels ..."). No developer message,
  no tools. Repair requests send the frozen `build_repair_spec` prompt verbatim.
- **Training cutoff:** June 2024. Source: gpt-oss model card (arXiv 2508.10925),
  "Our model has a knowledge cutoff of June 2024"; the template states
  "Knowledge cutoff: 2024-06". Weights released August 2025. Both before the
  prose corpus (case reports published February 2026 or later), so prose
  results are read as reconstruction, not recall, on the stated cutoff.
- **Context / output budget:** `-c 98304`, `max_tokens = 78000` on every
  request, including resends and repairs (the frozen repair spec carries
  128,000; the caller sends `78000`). Measured headline prompts (this
  tokenizer and template): max 17,144 (pool_037), median 7,707, min 5,573.
- **Reasoning:** `reasoning_effort` "high" (Sonnet ran at its default effort with
  no reasoning cut; RUN_DECISIONS records that effort "low" returned invalid
  output). Reasoning is returned in `reasoning_content` and stored in the raw
  row's `reasoning` field, never in `text`.
- **Sampling (every request, all set explicitly; llama-server's own defaults
  are top_k 40, min_p 0.05, temperature 0.8, top_p 0.95):** temperature 1.0,
  top_p 1.0, top_k 0 (off), min_p 0.0 (off), typical_p 1.0 (off),
  repeat_penalty 1.0 (off), presence_penalty 0.0, frequency_penalty 0.0,
  dry_multiplier 0.0 (DRY off), xtc_probability 0.0 (XTC off), top_n_sigma -1
  (off), mirostat 0 (off), dynatemp_range 0.0 (off), seed 42 for every request.
  Temperature and top_p are OpenAI's recommendation (openai/gpt-oss README);
  Sonnet ran at provider defaults with no temperature. A fixed seed does not
  guarantee bit-identical output on a GPU.
- **Per-call checks (any failure stops the wave and is reported; nothing is
  written as an answer):** the `/apply-template` render of the exact request
  body contains `request["prompt"]` verbatim, "Current date: 2026-11-11" and
  "Reasoning: high", and for base-wave requests its SHA-256 equals the stored
  value in `models/gpt-oss-20b/headlineJ_render_sha256.json`; the logged
  rendered prompt (`--log-prompts-dir`) equals that render; response
  `usage.prompt_tokens` equals the `/tokenize` count of the render;
  `prompt_tokens + 78000 <= 98304`; `/props` reports n_ctx `98304` and one
  slot; `/slots` params after the call equal the sampling values above;
  the answer `text` (`content`) contains none of the harmony control tokens
  `<|channel|>`, `<|message|>`, `<|start|>`, `<|end|>`, `<|return|>`,
  `<|call|>`, `<|constrain|>` (a leak would mean the reasoning parser failed).
- **Raw rows:** `raw/gpt-oss-20b/<spec_tag>.results.jsonl`, one row per request
  in the README format; `custom_id` from `batch_submit.make_custom_id`;
  `finish_reason` "stop" → `end_turn`, "length" → `max_tokens`; `usage` as
  reported by llama-server plus `output_tokens` = `completion_tokens` and
  `input_tokens` = `prompt_tokens`, because the frozen `at_ceiling` reads
  `usage.output_tokens` and needs `>= MODEL_MAX_OUTPUT` (checked: a request
  stopped at `max_tokens` 4,096 reported `completion_tokens` exactly 4,096 with
  `finish_reason` "length"); reasoning in `reasoning`.
- **Specs, in order:** `final_headlineJ` (46 requests) only. Other specs are
  proposed after the headline result is reported.
- **D4 / D6 as applied:** a transport failure (connection error, HTTP 5xx,
  timeout after 4 h, empty body) is `result_type: "errored"` and is resent once,
  unchanged, in a `-rs1` wave (`batch_game.build_resubmit_spec`). One repair
  round (`batch_game.build_repair_spec(..., 1, 1, tag + "-r1")`). The wrapper
  sets `batch_game.MODEL_MAX_OUTPUT = 78000`, so a call that stops at
  `max_tokens` having used 78,000 tokens is a resource-bounded
  non-completion, recorded, never re-asked. Scoring:
  `batch_game.score([(spec, files), (repair_spec, repair_files)], out_root)`
  into `results/gpt-oss-20b/final_headlineJ/`. No other retries, no prompt
  changes, no second scorer.
- **Restarts:** the runner appends one row per request to the wave's results
  file and, when started again, skips every `custom_id` already present in
  that file. A request interrupted before its row was written (runner stopped,
  crashed, or the machine went down) is sent again as its first attempt,
  because no answer was seen. Every restart is logged with the time, the wave,
  the rows already present and the requests still to send. A restart is
  neither a D4 resend nor a repair. A transport failure the runner did see
  (connection error, HTTP 5xx, timeout, empty body) is not a restart: it is
  written as an errored row and handled by D4. A request stopped by a failed
  per-call check writes no results row; the failure is recorded in
  `<spec_tag>.check_failures.jsonl`, and the wave resumes only on the user's
  instruction, which is logged; the request is then sent again as its first
  attempt.
- **Primary result and the integrity gate:** the frozen `score` (default
  `allow_partial=False`) runs the same integrity gate as for Sonnet. If it
  refuses the headline J game for any cell (a unit with no parseable answer
  after repair, or a unit over `joint_game.POLICY_CAP`), that refusal, with
  its counts (units without an answer, units over the cap, D6
  non-completions), IS the primary result for the model. The mean from
  `score(..., allow_partial=True)` is then reported only as a secondary
  figure, labelled "answered units only", never in place of the verdict.
- **Comparison:** F1_J, F1_L and q on the same 46 pools against Sonnet's
  headline (F1_J 0.7225, F1_L 0.8817, q 0.8206), each reported beside the
  completion rate, the D6 non-completion rate, the transport-error rate and the
  invalid-after-repair rate, for both models. Descriptive only; labelled
  post-hoc exploratory wherever reported. A non-completion is never recorded
  as a zero and never dropped silently.

---

## Entry 2: Gemma 4 12B (DRAFT)

- **Date committed:** (on commit)
- **Label:** post-hoc exploratory cross-model robustness check, as above.
- **Model / weights:** Google Gemma 4 12B instruction-tuned ("12B Unified"),
  quantization-aware-trained Q4_0. GGUF `gemma-4-12b-it-qat-q4_0.gguf` from
  Hugging Face `google/gemma-4-12B-it-qat-q4_0-gguf` (published by Google),
  revision `29d097773436b69ff9feafd636ab4cf873786537`, 6,975,879,296 bytes,
  SHA-256 `93567e57a8fe10b23569b9d9ec38cd005deedf71e29477c421a4b83f418a538b`
  (matches the HF listing at that revision). Text only: the image projector
  (`mmproj`) is not downloaded or loaded.
- **Runtime:** as Entry 1 (llama.cpp build b12110, Vulkan, zip SHA-256
  `9732a5e4...874f`, RX 9070 XT Vulkan0 only).
- **Server flags (fixed):** `-m <gguf> -dev Vulkan0 -ngl 99 -c 163840 -np 1
  -fit off --jinja --reasoning-format auto --no-cache-prompt --cache-ram 0
  --log-prompts-dir <run log dir>`. Embedded chat template, unchanged
  (SHA-256 `6a1015c47ccfcfa67c3b772385bccee357a4d37c3cda37bd202e9047f391ab82`;
  it contains no date or time call).
- **GPU placement:** all 49 layers and the KV cache on Vulkan0; no spill
  (load test at these flags: process dedicated 10,194 MiB, shared 197 MiB,
  the host-side compute buffer). Decode 62 tok/s at depth 21k, 44 tok/s at
  150k; ms/token = 15.03 + 0.0000503 x depth.
- **Messages:** one user message, `request["prompt"]` verbatim; repairs send the
  frozen repair prompt verbatim. `chat_template_kwargs = {"enable_thinking": true}`,
  so the template adds a system turn holding only `<|think|>` (Google's switch
  for thinking). No other system text.
- **Training cutoff:** January 2025. Source: Google's Gemma 4 model card
  (ai.google.dev/gemma/docs/core/model_card_4), which gives one pre-training
  cutoff for the family. Note: this GGUF repo was created 2026-06-05, after the
  corpus window opened; the reading as reconstruction rests on Google's stated
  cutoff, and the report says so.
- **Context / output budget:** `-c 163840`, `max_tokens = 128000` on every
  request including resends and repairs. Measured headline prompts (this
  tokenizer and template, with BOS): max 19,563 (pool_037), median 8,603.5,
  min 6,106.
- **Reasoning:** thinking on. Verified on one generic request: the rendered
  prompt logged by the server contains `<|think|>`; reasoning came back in
  `reasoning_content` (1,112 chars), content was only the answer. Stored in the
  row's `reasoning` field, never in `text`.
- **Sampling (every request, all explicit):** temperature 1.0, top_p 0.95,
  top_k 64, min_p 0.0 (off; server default 0.05), typical_p 1.0 (off),
  repeat_penalty 1.0 (off), presence_penalty 0.0, frequency_penalty 0.0,
  dry_multiplier 0.0 (off), xtc_probability 0.0 (off), top_n_sigma -1 (off),
  mirostat 0 (off), dynatemp_range 0.0 (off), seed 42 for every request.
  Temperature, top_p and top_k are Google's recommendation (Gemma 4 model card).
  All fourteen values confirmed applied via `/slots` on the generic request.
- **Per-call checks:** as Entry 1, with the render required to contain the
  `<|think|>` system turn instead of the date and reasoning lines, and the
  control-token check on `text` using Gemma's markers `<|think|>`,
  `<|channel>`, `<channel|>`, `<|turn>`, `<turn|>` (taken from the embedded
  template); render
  hashes for the base wave stored before the run in
  `models/gemma-4-12b/headlineJ_render_sha256.json`.
- **Raw rows, specs, D4/D6, scoring, comparison:** as Entry 1, with
  `raw/gemma-4-12b/` and `results/gemma-4-12b/final_headlineJ/`, and
  `batch_game.MODEL_MAX_OUTPUT = 128000`.
- **Restarts:** the same rule as Entry 1. Rows are appended and a restarted
  runner skips every `custom_id` already in the wave's results file; a request
  interrupted before its row was written is sent again as its first attempt;
  every restart is logged; a restart is neither a D4 resend nor a repair.
- **Order between models:** Gemma 4 12B headline first, then gpt-oss-20b
  headline; each reported before the next starts.

---

## Common to both entries

- **Trained context (context must not exceed it):** gpt-oss-20b 131,072
  (GGUF `gpt-oss.context_length`; HF config `max_position_embeddings`; YaRN
  factor 32 from 4,096). Gemma 4 12B 262,144 (GGUF `gemma4.context_length`;
  HF config; model card "256K" for 12B). Read with `work/probes/gguf_meta.py`.
- **Repair margin:** 2,048 tokens. The frozen `repair_report_text` caps each
  label list at 40; its worst case is 1,590 characters = 778 gpt-oss tokens /
  1,262 Gemma tokens. `<CTX> >= longest headline prompt + <BUDGET> + 2,048`.
- **A request that does not fit:** before every call the caller checks
  `rendered prompt tokens + <BUDGET> <= <CTX>`. A base or resend request that
  fails it stops the wave. A repair prompt is the original prompt + "\n\n" +
  the capped feedback (`build_repair_spec`), at most ~1,264 tokens longer, so
  the 2,048 margin guarantees it fits; the check still runs on every repair,
  and a failure stops the repair wave and is reported. Such a request is never
  truncated, shortened or skipped: the frozen `score` requires a row for every
  request in a wave and refuses the cell otherwise.
- **Secondary analysis at a common output cap of 78,000 tokens
  (preregistered; the primary result is each model's full-budget run):**
  every model, Sonnet included, is also reported as if its output had been
  capped at 78,000 tokens. It is derived from the full runs, with no new
  requests:
  1. Output tokens are `usage` as recorded in the raw row, reasoning
     included (Sonnet: `usage.output_tokens` in
     `frozen/results/batches/final-headlineJ*.results.jsonl`; local models:
     `completion_tokens`, stored as `output_tokens`).
  2. Every first-pass row (base or `-rs1` resend) with more than 78,000
     output tokens is replaced by a capped copy: `stop_reason "max_tokens"`,
     `output_tokens 78000`, empty `text` and `reasoning`. All other rows are
     unchanged.
  3. With `batch_game.MODEL_MAX_OUTPUT = 78000`, the repair spec is rebuilt
     from the capped first-pass rows with the frozen
     `build_repair_spec(..., 1, 1, tag + "-r1")`. A capped unit gets no repair.
     Every repair request in it must equal one sent in the full run
     (same custom_id and prompt); if not, the secondary analysis stops and is
     reported. Repair rows are taken from the full run and capped by rule 2.
  4. Scored with the frozen `batch_game.score` into
     `results/<slug>/final_headlineJ_cap78000/` (Sonnet:
     `results/claude-sonnet-5/final_headlineJ_cap78000/`). Nothing in
     `frozen/` and no existing Sonnet result is written or changed.
  5. Reported beside the primary result with the same rates (completion,
     D6 non-completion at the cap, transport error, invalid after repair).
     For a model whose own budget is 78,000 the two coincide, and the report
     says so. Already known for Sonnet: 2 of its 46 first-pass answers
     (81,683 and 81,897 tokens) exceed the cap.
