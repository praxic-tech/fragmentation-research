# Preregistration: cross-model Game J (post-hoc exploratory)

One entry per model, written and committed **before that model receives its
first request**. Once committed, an entry is not edited. A change of plan is a
new, dated entry that says what changed and why.

## 2026-11-12: Gemma 4 12B and gpt-oss-20b, headline Game J

Two entries committed together, before either model receives a study request.
Post-hoc exploratory. Order of runs: Gemma 4 12B first, then gpt-oss-20b, each
reported before the next starts. Reviewed by the user as
`work/prereg_drafts/PREREGISTRATION_DRAFT.md`; copied here with the entries
reordered (Gemma first) and their cross-references renamed accordingly.

- **Runner (committed with these entries):** `work/runner/runner.py`, run as
  `python -I work/runner/runner.py <slug>` against a server started by
  `work/probes/server_ctl.py` (configs `gemma-run`, `gptoss-run`: the flags
  below, prompt logs in `logs/<slug>/prompts/`). It implements the per-call
  checks, row format, restart rule, D4 resend, one repair round, D6 and scoring
  stated below, using the frozen functions only. Beyond the checks listed in
  the entries it also stops the wave if a render contains a carriage return
  (the server's prompt log is compared after CRLF -> LF), or if a call stops
  at `length` before the full budget (which the fit check rules out).
- **Runner verified before any study request, with no model calls:**
  `work/runner/replay_sonnet.py` converts Sonnet's headline raw rows into
  llama-server's response format (prompt_tokens, completion_tokens,
  finish_reason, content, reasoning_content), passes them through the runner's
  per-call checks and row writer, the frozen resend, repair and score, and
  reproduces the paper: the same 46 base, 6 resend and 2 repair requests,
  every final answer equal to the committed scored row, F1_J 0.7225, F1_L
  0.8817, q 0.8206 (equal to KEY_NUMBERS.json to 1e-9).
  `work/runner/test_runner.py` (11 injected faults: restart, control tokens,
  prompt-token mismatch, early length stop, sampler mismatch, logged-prompt
  mismatch, render hash, fit, D6 ceiling, empty answer, repair transport
  failure) passes 11/11.

**D-A. Output budget and context length: Option B for both.** Sonnet's 46
first-pass headline answers (40 base rows + 6 transport resends) used 29,892
to 81,897 output tokens: median 49,594, 43/46 above 32,768, 30/46 above
44,000, 8/46 above 64,000, none at its 128,000 ceiling. A 32,768 budget would
make most requests D6 non-completions if a model reasons at that length.

| model | context `-c` | output budget | trained context | headroom over max prompt + budget | load test (made-up prompts) |
|---|---|---|---|---|---|
| Gemma 4 12B | 163,840 | 128,000 (= Sonnet's) | 262,144 | 16,277 | no spill; process peak 10.2 GB dedicated |
| gpt-oss-20b | 98,304 | 78,000 | 131,072 | 3,160 | spills ~2 GB to shared memory; accepted (gpt-oss-20b entry, "GPU placement") |

Measured worst-case time (longest headline prompt, answer at the budget):
Gemma 41.3 min per answer, a 46-request wave <= 31.7 h; gpt-oss 39.2 min per
answer, a 46-request wave <= 30.0 h (answers at the budget are D6 and never
re-asked). Absolute ceiling if every answer ends just under the budget and its
repair runs to the budget: Gemma 63.3 h, gpt-oss 60.0 h.

**D-B. Pinned date for gpt-oss.** `current_date` = `2026-11-11`. Any constant
works; it only has to be fixed and recorded.

### Gemma 4 12B

- **Date committed:** 2026-11-12
- **Label:** post-hoc exploratory cross-model robustness check, as the gpt-oss-20b entry below.
- **Model / weights:** Google Gemma 4 12B instruction-tuned ("12B Unified"),
  quantization-aware-trained Q4_0. GGUF `gemma-4-12b-it-qat-q4_0.gguf` from
  Hugging Face `google/gemma-4-12B-it-qat-q4_0-gguf` (published by Google),
  revision `29d097773436b69ff9feafd636ab4cf873786537`, 6,975,879,296 bytes,
  SHA-256 `93567e57a8fe10b23569b9d9ec38cd005deedf71e29477c421a4b83f418a538b`
  (matches the HF listing at that revision). Text only: the image projector
  (`mmproj`) is not downloaded or loaded.
- **Runtime:** as the gpt-oss-20b entry below (llama.cpp build b12110, Vulkan, zip SHA-256
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
- **Per-call checks:** as the gpt-oss-20b entry below, with the render required to contain the
  `<|think|>` system turn instead of the date and reasoning lines, and the
  control-token check on `text` using Gemma's markers `<|think|>`,
  `<|channel>`, `<channel|>`, `<|turn>`, `<turn|>` (taken from the embedded
  template); render
  hashes for the base wave stored before the run in
  `models/gemma-4-12b/headlineJ_render_sha256.json`.
- **Raw rows, specs, D4/D6, scoring, comparison:** as the gpt-oss-20b entry below, with
  `raw/gemma-4-12b/` and `results/gemma-4-12b/final_headlineJ/`, and
  `batch_game.MODEL_MAX_OUTPUT = 128000`.
- **Restarts:** the same rule as the gpt-oss-20b entry. Rows are appended and a restarted
  runner skips every `custom_id` already in the wave's results file; a request
  interrupted before its row was written is sent again as its first attempt;
  every restart is logged; a restart is neither a D4 resend nor a repair.
- **Order between models:** Gemma 4 12B headline first, then gpt-oss-20b
  headline; each reported before the next starts.

### gpt-oss-20b

- **Date committed:** 2026-11-12
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

### Common to both entries

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

## Entry template

- Date committed:
- Model id / provider or runtime / exact revision (weights SHA-256 and quantization if local):
- Training cutoff, and its source:
- Context length (and how it is enforced) / output budget / sampling parameters / reasoning setting:
- Specs to run, in order:
- Resend, repair and non-completion rules (D4, D6 as applied here):
- Comparison planned, and the post-hoc exploratory label:

## 2026-11-13: Sonnet-dependence sweep on headline J (seven hosted models)

Post-hoc exploratory. Written, committed and pushed before any API request for
these models (the commit time is the record). Smoke tests (dummy prompt, no
evaluation text) come after this commit and count toward nothing.

**Supersedes** the 2026-11-12 local llama.cpp gpt-oss-20b entry: gpt-oss-20b
now runs on OpenRouter (model 4 below). No gpt-oss-20b study request was ever
sent locally, and the Colab idea is dropped. Reason: local compute time (the
Gemma run took ~24 h). The Gemma 4 12B entry and its result (REFUSED,
`results/gemma-4-12b/PRIMARY_RESULT.md`) are unchanged.

**Question.** The frozen prompts were tuned on Sonnet. Does another model, on
the same prompts and the same answer-key scoring, reach Sonnet's headline
(F1_J 0.7225, F1_L 0.8817, q 0.8206)?

**Interpretation (fixed now).** A model at or above Sonnet is evidence against
Sonnet dependence of the headline. A lower score is NOT evidence that
fragmentation protects, because it may reflect fit to a Sonnet-tuned prompt.

**Scope.** `frozen/runs/final_headlineJ.json` only (46 pools): base wave, the
frozen D4 resend of transport holes (`-rs1`), one repair round (`-r1`, and its
`-rs1`), nothing else. Frozen prompts sent verbatim, never rebuilt; repair
prompts from the frozen `build_repair_spec`. Same answer-key scoring as Sonnet.

### Models (list fixed now)

| # | slug | role | lab | where | settings | output budget | training cutoff (source) |
|---|---|---|---|---|---|---|---|
| 1 | `gpt-5.6-sol` | frontier reasoning | OpenAI | Azure OpenAI deployment `$AZURE_DEPLOYMENT_GPT56`: Global Standard, model version 2026-07-09, version upgrade NoAutoUpgrade, 250k TPM, content filter DefaultV2. Responses API (`/openai/v1/responses`). | `service_tier: "flex"` on every request (Microsoft Learn, "Use Flex processing with Azure OpenAI"); no Standard fallback, ever. `reasoning: {"effort": "max"}`, the highest effort available: Microsoft Learn (Azure OpenAI reasoning models, API and feature support) lists `none, minimal, low, medium, high, xhigh, max` and states that `max` works only with GPT-6 or GPT-5.6 models and the Responses API. `reasoning.mode` not sent (Azure default `standard`; `pro` is a separate execution mode, not an effort level). | `max_output_tokens` 128000 | 2026-02-16 (OpenAI model page) |
| 2 | `gpt-4.1` | non-reasoning flagship | OpenAI | Azure deployment `$AZURE_DEPLOYMENT_GPT41`: Global Standard, version 2025-04-14, auto-upgrade off, 1M TPM, DefaultV2. Responses API. | no `service_tier` sent (Standard); pinned tier = `default` | `max_output_tokens` 32768 | May/June 2024 (Microsoft Learn models table / Azure pricing page) |
| 3 | `gpt-oss-120b` | open reasoning, mid-size | OpenAI | OpenRouter `openai/gpt-oss-120b`, provider CoreWeave only, quantization fp4 only, `allow_fallbacks: false` | `reasoning: {"effort": "high"}`, temperature 1.0, top_p 1.0 (as the 2026-11-12 gpt-oss-20b entry) | `max_tokens` 117964 = the provider's cap; BELOW Sonnet's 128,000 | June 2024 (gpt-oss model card) |
| 4 | `gpt-oss-20b` | open reasoning, small | OpenAI | OpenRouter `openai/gpt-oss-20b`, CoreWeave only, fp4 only, `allow_fallbacks: false` | as model 3 | `max_tokens` 117964 (provider cap; below Sonnet's 128,000) | June 2024 (gpt-oss model card) |
| 5 | `llama-4-maverick` | open, non-reasoning | Meta | OpenRouter `meta-llama/llama-4-maverick`, Parasail only, fp8 only, `allow_fallbacks: false` | provider defaults | `max_tokens` 32768 | August 2024 (Meta model card) |
| 6 | `deepseek-v3.2` | open reasoning, frontier-class | DeepSeek | OpenRouter `deepseek/deepseek-v3.2`, GMICloud only, fp8 only, `allow_fallbacks: false`. GMICloud may retain prompts but does not train on them; recorded. | `reasoning: {"enabled": true}` | `max_tokens` 128000 | none published; released 2025-12-01 |
| 7 | `kimi-k2.5` | open reasoning, frontier-class | Moonshot | OpenRouter `moonshotai/kimi-k2.5`, SiliconFlow only, int4 only (Moonshot's released format), `allow_fallbacks: false` | `reasoning: {"enabled": true}` (thinking on) | `max_tokens` 128000 | none published; released 2026-01-27 |

- **Disclosure (Kimi):** Kimi K3 was used earlier as a fragment cutter (D3/D5)
  on development data only.
- **Sampling:** provider defaults for every model (no temperature, top_p or
  other sampling field sent) except gpt-oss (temperature 1.0, top_p 1.0).
  Every request body is logged exactly as sent.
- **Messages:** one user message, `request["prompt"]` verbatim (Responses API:
  `input` = `[{"role": "user", "content": prompt}]`). No system or developer
  message, no tools.
- **OpenRouter request fields (models 3-7):** `provider: {"only": [p],
  "order": [p], "quantizations": [q], "allow_fallbacks": false,
  "require_parameters": true}`, `transforms: []` (middle-out compression off:
  no prompt is ever shortened), `usage: {"include": true}`, streaming.
- **Azure request fields:** `model` = deployment name, `input`,
  `max_output_tokens`, `truncation: "disabled"` (an over-long input errors
  instead of being cut), plus model 1's `reasoning` and `service_tier`;
  streaming.

**Models not run, recorded with reasons:** Azure-hosted gpt-oss-120b,
DeepSeek-V3.2, Kimi-K2.5, grok-4-1-fast-reasoning and Llama 4 (not deployable,
or zero quota on the student subscription); gpt-6.x and gpt-5.6-terra/luna
(training cutoffs after the documents, or the same family as gpt-5.6-sol);
gpt-5.5 (cost).

### Eligibility

A model is eligible if its training cutoff, or its release date when no cutoff
is published, is before the earliest document's first online date (2026-02-17
for the corpus, 2026-02-26 for the headline pools). All seven are eligible:
gpt-5.6-sol 2026-02-16; gpt-4.1 mid-2024; gpt-oss June 2024; Llama 4 Maverick
August 2024; DeepSeek-V3.2 released 2025-12-01; Kimi-K2.5 released 2026-01-27.

**Exception, reported for every model:** 5 headline pools (`pool_009`,
`pool_011`, `pool_041`, `pool_056`, `pool_062`) each hold one document first
online in 2025 by its epub date (`verify_postcutoff.py` read `sortdate`, which
for these is the later print-issue date). Every model, Sonnet and Gemma
included, is reported on all 46 pools and on the 41 without those 5. The
41-pool figure is the frozen `batch_game.score` on the same rows with those 5
pools removed from the spec's `build.pools` and sidecar (nothing re-run, no
second scorer).

### Run order

gpt-oss-20b, gpt-oss-120b, llama-4-maverick, deepseek-v3.2, gpt-4.1,
gpt-5.6-sol; then the Kimi decision (below). Each model: base wave, `-rs1`,
repair wave, its `-rs1`, scored before the next model starts.

### Transport

- **Runner:** `work/runner/api_runner.py`, committed after this entry and
  before the smoke tests; it implements this entry. Threads; pacing as fast as
  each provider's limits allow: Azure requests admitted under a token bucket at
  the deployment's TPM, counting each request as its estimated prompt tokens +
  its `max_output_tokens`; at most 16 requests in flight per model; every
  admission also passes the cost cap (below).
- **Timeouts:** 30 min per request on Azure, 2 h on OpenRouter (wall clock
  from send to the final event). Every timeout is logged before the resend.
- **Transport errors:** HTTP 408, 429, 5xx, connection errors, timeouts, and a
  stream that ends without a final response. Retried in the same wave with
  exponential backoff and jitter (Retry-After honoured when present; else
  min(30 x 2^k, 900) s), at most **6 attempts** per request per wave. Every
  attempt is logged. Never scored. A request still failing after 6 attempts is
  written as an `errored` row; the frozen D4 resend (`build_resubmit_spec`,
  `-rs1`) then sends it once more, again with up to 6 attempts. A unit still
  failing after that is reported as **not completed**.
- **Content-filter blocks** (Azure HTTP 400 `content_filter`, or a response
  `incomplete` with reason `content_filter`; OpenRouter `finish_reason`
  `content_filter` or an error naming moderation) are their own outcome: logged
  in `<tag>.content_filter.jsonl`, never written as a results row, never
  resent, never repaired, never scored.
- **Provider and tier check, every response:** OpenRouter's reported
  `provider` must equal the pinned provider; Azure's reported `service_tier`
  must equal the pinned tier (`flex` for model 1, `default` for model 2) and
  its reported `model` must be the pinned model. Any mismatch is a **halt**.
- **Auth failures** (401/403), and 400/404 that are not content filters, are
  **halts**, never retried.
- **Prompt integrity:** truncation is off by configuration
  (`truncation: "disabled"`, `transforms: []`). In addition, every response's
  reported prompt tokens must be at least 0.5 x Sonnet's `input_tokens` for the
  same pool (`frozen/results/batches/final-headlineJ*.results.jsonl`); all
  ratios are recorded; after each wave the spread of (prompt tokens / prompt
  characters) across its requests must be within a factor 1.25. A failure is
  a halt.
- **Stop reasons:** OpenRouter `finish_reason` "stop" -> `end_turn`, "length"
  -> `max_tokens`; Azure `status` "completed" -> `end_turn`, `incomplete` with
  reason `max_output_tokens` -> `max_tokens`. `usage.output_tokens` = reported
  output tokens including reasoning (OpenRouter `completion_tokens`; Azure
  `output_tokens`). A `max_tokens` stop below the full budget is a halt (not
  covered by D6). `text` = the final answer only; reasoning text, when a
  provider returns it, goes in `reasoning`, never in `text`.

### Cost caps

The runner counts each response's reported cost plus the worst case of every
in-flight request (its prompt at the input rate + its full output budget at the
output rate), and never sends a request that could take the total past the cap.
Units not sent are reported as **not run**.

| model | cap (USD) | how cost is counted |
|---|---|---|
| gpt-5.6-sol | 50.00 | reported usage x Azure Flex rates = 50% of Standard Global short-context: input $2.00/M, output $10.00/M (Azure retail price meters "5.6 sol ShortCo Inp/Opt Std Gl": $4/$20 per M); no cache discount applied (an upper bound) |
| gpt-4.1 | 10.00 | reported usage x Azure Global Standard: input $2.00/M, output $8.00/M (meters "gpt 4.1 Inp/Outp glbl") |
| gpt-oss-20b | 1.00 | OpenRouter `usage.cost` as reported; worst case from the pinned endpoint's listed prices |
| gpt-oss-120b | 1.50 | as above |
| llama-4-maverick | 1.50 | as above |
| deepseek-v3.2 | 3.00 | as above |

OpenRouter holds $10.00 of credit, key limit $10.00.

- A cap reached **before a model's base wave finishes** is a halt. A cap
  reached later (resend or repair wave) stops sending; the requests not sent
  are reported as not run, and those units are scored on the attempts they
  have. A cap stop is reported as incomplete (gate verdict plus units not run),
  never dropped silently.
- **Kimi rule:** Kimi runs only if the remaining OpenRouter balance after
  models 3-6 is at least $7.50 (read from OpenRouter's key endpoint). Otherwise
  it is dropped and reported as "planned; dropped for budget under a rule fixed
  before any Kimi request". If it runs, its cap is the remaining balance minus
  $0.25. The decision is budget-only and cannot depend on any model's results.
  No Kimi request, smoke test included, is sent before the decision.

### Scoring

- The frozen `batch_game.score` / `joint_game.score_row`, unchanged, with
  `batch_game.MODEL_MAX_OUTPUT` = the model's output budget (D6: a call that
  stops at `max_tokens` having used the whole budget is a resource-bounded
  non-completion, recorded and never re-asked). Path as in the README: results
  rows -> one resend -> one repair round -> `batch_game.score`.
- **PRIMARY verdict: the preregistered rule applied as written.** The cell is
  REFUSED if any unit has no answer after repair, or if any unit's recorded
  `repair.policy_share` exceeds `joint_game.POLICY_CAP` (0.25). Policy share is
  computed from the scored rows themselves (`repair.policy_share` in
  `J.jsonl`), because the frozen gate reads `1 - coverage_frac` for Game J and
  misses this (logged in the Gemma run, `logs/RUNLOG.md` 2026-11-13). A unit
  not completed (transport), content-filtered or not run (cap) has no answer,
  so its cell is REFUSED.
- The frozen gate's own output is kept too, labelled "frozen gate output".
  Units that cannot enter the frozen `score` (content-filtered, not completed,
  not run) are removed from the spec passed to it, and listed.
- If REFUSED, the answered-units-only mean (`score(..., allow_partial=True)`)
  is the SECONDARY figure, labelled "answered units only", never in place of
  the verdict.
- **Beside every score:** completion rate, D6 rate, transport-error rate
  (requests with at least one transport error, and units not completed),
  content-filter count, invalid-after-repair rate, mean `policy_share`, the
  units over the cap, tokens (input, output, reasoning where reported), and
  actual cost. On 46 and on 41 pools.
- **Output:** `raw/<slug>/` (rows, specs, attempt logs), `results/<slug>/`
  (`final_headlineJ/`, `final_headlineJ_41pools/`, secondary dirs if refused,
  `PRIMARY_RESULT.md`), committed per model with the small logs; full request
  bodies with prompt text are not committed.

### Final report

One table: every model plus Sonnet and Gemma 4 12B: verdict, F1_J, F1_L, q,
their 41-pool versions, all the rates above, and cost. Descriptive only;
labelled post-hoc exploratory wherever reported.


## 2026-11-13 (amendment): gpt-oss provider and budget; run order

Post hoc exploratory, like the entry it amends ("Sonnet-dependence sweep on
headline J", above). Written after the gpt-oss-20b base-wave halt
(`logs/RUNLOG.md`, "gpt-oss-20b: HALT in the base wave") and before any
further request. The settings below were chosen from the endpoint limits and
prompt lengths only. No row of this sweep has been scored.

### Run order

- The Azure line (gpt-4.1, then gpt-5.6-sol) runs now, concurrently with the
  OpenRouter line (gpt-oss-20b, gpt-oss-120b, llama-4-maverick, deepseek-v3.2).
  The two lines use separate endpoints, keys, rate limits and caps, and the
  order affects no result.
- The Kimi decision comes after all six models finish. The Kimi rule is
  unchanged.

### gpt-oss-20b and gpt-oss-120b

- **Provider: AkashML, fp4 only, `allow_fallbacks: false`**, replacing
  CoreWeave. Reason: CoreWeave's effective limit is about 117.7k total tokens,
  below its listed 131,072 (3 length stops at 107,549 / 112,188 / 111,621
  output tokens; see RUNLOG).
- **Max output: 110,000 tokens**, replacing 117,964. Reason: gpt-oss holds
  131,072 tokens in total on every provider, so 117,964 cannot fit prompts
  over about 13.1k tokens (2 HTTP 400s: pool_018 at 14,748 prompt tokens,
  pool_007 at 13,552). The longest headline prompt, pool_037 (75,956 chars),
  is about 19.1k gpt-oss tokens (at most about 19.9k at the highest observed
  0.262 tokens/char); 110,000 fits it with margin.
- **D6 = a call that reaches 110,000 output tokens.** This is below Sonnet's
  128k. Each model runs at its own feasible maximum: gpt-4.1 and
  llama-4-maverick 32,768; deepseek-v3.2, kimi-k2.5 and gpt-5.6-sol 128,000;
  gpt-oss 110,000.
- All other gpt-oss settings unchanged: reasoning effort high, temperature
  1.0, top_p 1.0.
- **The 11 CoreWeave rows are superseded**: kept in the logs, never scored.
  gpt-oss-20b reruns all 46 pools from the start. The $0.1064 already spent is
  reported in its cost totals.
- Caps unchanged: gpt-oss-20b $1.00, gpt-oss-120b $1.50.

### Halt conditions added

- Any HTTP 400 on context length.
- Any length stop below 110,000 output tokens (gpt-oss).
- A halt on one line (Azure or OpenRouter) does not stop the other.

### Fallback

- If AkashML fails its smoke test (auth, provider, quantization, or rejecting
  a ~19-20k-token prompt with max output 110,000), use Parasail fp4 under the
  same settings, record it in RUNLOG and continue. For gpt-oss-120b on
  Parasail the cap is raised to $3.00.
- Smoke test: a dummy prompt of the length of the longest headline prompt
  (not a headline prompt), with max output 110,000.
