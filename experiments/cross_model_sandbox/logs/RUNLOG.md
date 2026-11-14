# Run log (post-hoc exploratory cross-model check)

Short record of what was run in this sandbox and why. Newest at the bottom.

## 2026-11-11 — session start checks

- `python tools/verify_frozen.py` (system Python 3.14.8): PASS, 185 files byte-identical.
- `python tools/selfcheck_sonnet.py` (system Python): FAILED on import,
  `ModuleNotFoundError: No module named 'dotenv'`. Nothing scored.
- With user approval: created `.venv/` (gitignored) from Python 3.14.8 and
  installed the study's pins from `frozen/requirements.txt`, wheels only:
  numpy 2.4.6, scipy 1.16.1, openai 1.55.3, python-dotenv 1.2.1
  (+ openai deps: httpx 0.28.1, pydantic 2.14.3, etc.).
  Why: the self-check needs python-dotenv; pinning keeps numerics identical to the study.
- All sandbox Python runs use `PYTHONDONTWRITEBYTECODE=1` so no `__pycache__`
  is written under `frozen/`.
- `.venv/Scripts/python.exe tools/verify_frozen.py`: PASS (185 files).
- `.venv/Scripts/python.exe tools/selfcheck_sonnet.py`: PASS. 46 units re-scored
  from raw rows, every final answer equals the committed row (2 repair requests
  rebuilt); F1_J 0.7225, F1_L 0.8817, q 0.8206, matching KEY_NUMBERS.json.
- `verify_frozen.py` re-run after the self-check: PASS. No `__pycache__` in `frozen/`.

## 2026-11-11 — step 1: environment

Read-only inventory:
- GPU: AMD Radeon RX 9070 XT (gfx1201, RDNA4), 15.92 GB VRAM (registry qwMemorySize),
  Adrenalin 26.10.1, driver 32.0.32015.7029 (2026-10-17). Also an iGPU,
  AMD Radeon(TM) Graphics (gfx1036, 7800X3D), 0.5 GB carve-out.
- CPU Ryzen 7 7800X3D, 31.2 GB RAM.
- Vulkan 1.4 loader + AMD driver: both GPUs listed (vulkaninfo). OpenCL: both GPUs.
- HIP: only the driver's runtime DLLs (amdhip64_6.dll 10.0.3661, amdhip64_7.dll 10.0.3683);
  no ROCm SDK, no hipcc/rocm-smi. WSL2 Ubuntu exists (stopped, untouched).
- No Ollama, LM Studio, llama.cpp, koboldcpp, docker; nothing on ports 11434/1234/8080.

Install (user granted install permission, asked to keep it small):
- **Runtime identity (use this in every record): llama.cpp build b12110 (commit
  cd959bae9), Vulkan backend, Windows x64 zip
  `llama-b12110-bin-win-vulkan-x64.zip`, SHA-256
  9732a5e48887ca54d0bfe4af4324dc85fd56cd8cda19b52df3542fa6ebe6874f.**
  Source: https://github.com/ggml-org/llama.cpp/releases/download/b12110/
  (37,661,146 bytes; SHA-256 matches the GitHub release asset digest).
  Extracted to `runtime/llama-b12110-vulkan/` (102 MB); `runtime/` added to
  .gitignore. Chosen over the ROCm 10.0 build (267 MB): smaller, and Vulkan
  already works on this driver.
- `llama-server --version`: build 12110, commit cd959bae9, Clang 20.1.8.
- `llama-server --list-devices`: Vulkan0 = RX 9070 XT (16304 MiB), Vulkan1 = iGPU
  (16212 MiB, i.e. shared system RAM). Every run must pin `-dev Vulkan0`,
  otherwise llama.cpp may split layers onto the iGPU.

## 2026-11-11 — step 1: GPU smoke test (throwaway model, not a study model)

- Downloaded (user approved) `Qwen3-0.6B-Q8_0.gguf`, 639,446,688 bytes, from
  https://huggingface.co/Qwen/Qwen3-0.6B-GGUF pinned at revision
  23749fefcc72300e3a2ad315e1317431b06b590a. SHA-256
  9465e63a22add5354d9bb4b99e90117043c7124007664907259bd16d043bb031 matches the
  Hugging Face LFS listing. Stored in `runtime/test_models/` (gitignored).
- Ran `llama-completion -m <model> -dev Vulkan0 -ngl 99 -c 4096 -n 128 -s 42 -no-cnv
  -p "Explain in three sentences why the sky is blue."` (generic prompt, nothing
  from frozen/), then the same with `-v` to capture placement lines.
- Placement (verbose log): `using device Vulkan0 (AMD Radeon RX 9070 XT) - 15419 MiB free`;
  layers 0-28 each `assigned to device Vulkan0`; `offloaded 29/29 layers to GPU`;
  no line mentions Vulkan1.
- Memory: Vulkan0 model buffer 604.15 MiB, KV buffer 448.00 MiB (4096 ctx),
  compute buffer 312.77 MiB; llama.cpp projected 1364 MiB. Windows counters:
  llama process peak dedicated 1,477 MiB; 9070 XT adapter 5,610 -> 7,096 MiB
  (+1,486 MiB).
- Speed (verbose run): prompt 1,164 tok/s (11 tokens, too short to mean much),
  generation 541 tok/s (127 tokens). First run: 535 tok/s generation.
- Findings for study runs:
  - The adapter already had ~5.6 GB dedicated in use before the run (desktop and
    other apps), while Vulkan reports 15,419 MiB free. Re-measure free VRAM
    before sizing a study model; budget against the lower figure until resolved.
  - llama.cpp b12110 auto-fits parameters to free memory by default
    (`common_fit_params`), which can change context or offload silently. Study
    runs must pass `-fit off` with explicit `-c`, and check the logged n_ctx.
  - The first attempt failed with `invalid argument` because PowerShell's
    Start-Process split the unquoted prompt. Wrappers must pass arguments as a
    list (Python subprocess), not a joined string.

## 2026-11-11 — step 2 (local part): candidate research, nothing downloaded

- Sources: Google Gemma 4 and Gemma 3 model cards (ai.google.dev), gpt-oss model
  card (arXiv 2508.10925) and openai/gpt-oss README, Qwen and Microsoft HF model
  cards, HF API file listings (sizes, SHA-256) and config.json (attention layout).
- VRAM check: 5,728 MiB of the 9070 XT's dedicated memory is held by desktop apps
  (dwm 1.8 GB, Edge, AMDChat, GalaxyClient, Spotify, wallpaper, ...). Vulkan
  reports 15,419 MiB "free" but WDDM would page to system RAM past the real
  limit (slow, not wrong). Plan against ~10 GB unless apps are closed.
- Proposed (not chosen): gpt-oss-20b MXFP4 (ggml-org GGUF) and Gemma 4 12B
  QAT Q4_0 (google GGUF), both 64k context with a 32,768-token output budget.
  Excluded: Qwen3.5/3.6/3.8 (released Feb-Aug 2026, cutoff not stated),
  Gemma 4 26B-A4B (13.45 GiB weights), Phi-4 (16k context), Qwen3-8B/14B
  (32k native context).

## 2026-11-11 — model weights downloaded (user approved), not yet loaded

- Free VRAM before: 14,649 MiB (1,655 MiB in use after the user closed apps).
- `gpt-oss-20b-MXFP4.gguf`, 12,109,566,624 bytes, from
  https://huggingface.co/ggml-org/gpt-oss-20b-GGUF at revision
  15dcfc7e7c608c6161507211ed43c5b590801b4b. SHA-256
  27cd6c432c7672cb812a92f611cf3ba7bbc35928262bb1e1253ff4ee6ae35901: matches HF LFS listing.
- `gemma-4-12b-it-qat-q4_0.gguf`, 6,975,879,296 bytes, from
  https://huggingface.co/google/gemma-4-12B-it-qat-q4_0-gguf at revision
  29d097773436b69ff9feafd636ab4cf873786537. SHA-256
  93567e57a8fe10b23569b9d9ec38cd005deedf71e29477c421a4b83f418a538b: matches HF LFS listing.
- GGUF files only (no mmproj/image projector). Stored in `runtime/models/` (gitignored).

## 2026-11-11 — gpt-oss-20b load test (generic prompt, not a study run)

- Prompt: 29,413 gpt-oss tokens of synthetic "Note N: the <adj> <noun> was <verb>
  by team T on day D." lines plus one question (seeded generator, nothing from
  frozen/). Raw completion mode, no chat template.
- Command: `llama-completion -m runtime/models/gpt-oss-20b-MXFP4.gguf -dev Vulkan0
  -ngl 99 -c 65536 -fit off -n 512 -s 42 -no-cnv -v -f filler.txt`
  (runtime: llama.cpp build b12110, Vulkan, zip SHA-256 9732a5e4...874f).
- Placement: 25/25 layers on Vulkan0, none on other devices; n_ctx = 65536 as set
  (fit off, no silent change); flash_attn auto.
- Buffers (Vulkan0): model 10,949 MiB, KV 1,536 MiB (full-attn, 65,536 cells)
  + 18 MiB (SWA, 768 cells), compute 480 MiB = 12,983 MiB. Host: CPU_Mapped model
  587 MiB, Vulkan_Host compute 87 MiB.
- Windows counters: adapter dedicated 1,679 -> peak 13,329 MiB of 16,304
  (2,975 MiB headroom); llama process peak 11,647 MiB; adapter shared 96 -> 1,689 MiB
  (host-side mapped/pinned buffers; no device buffer was placed off-GPU).
- Speed: prefill 1,363 tok/s (29,413 tokens in 21.6 s); generation 60.4 tok/s
  at ~29.5k context (511 tokens). Wall time 42.5 s including load.
- Time estimate for headline J (46 requests, 32,768-token output budget): about
  25 s prefill + up to ~10-12 min of generation per request if it uses the full
  budget; roughly 2-9 h for the wave depending on reasoning length.

## 2026-11-11 — Gemma file re-check, Gemma load test, headline token counts, gpt-oss server probe

### Gemma file vs Hugging Face listing at its pinned revision
- Repo google/gemma-4-12B-it-qat-q4_0-gguf, revision 29d097773436b69ff9feafd636ab4cf873786537,
  file gemma-4-12b-it-qat-q4_0.gguf, 6,975,879,296 bytes, SHA-256
  93567e57a8fe10b23569b9d9ec38cd005deedf71e29477c421a4b83f418a538b.
- HF API tree at that revision lists the same size and LFS oid; the resolve URL's
  headers give X-Repo-Commit 29d09777..., X-Linked-Size 6975879296, X-Linked-ETag
  = the same SHA-256. Local file hash matches. MATCH.

### Gemma 4 12B load test (generic prompt, not a study run)
- Prompt: the first 1,200 lines of the gpt-oss filler plus the question
  (synthetic, nothing from frozen/). Gemma's tokenizer gives 29,456 tokens for the
  file as written (CRLF) and 28,256 with LF; llama-completion reads -f in text mode
  and evaluated 28,255 tokens (CR stripped; 1-token gap = BOS accounting).
  Lesson: count tokens on the exact string sent, never on a file re-read in a
  different mode. The frozen spec prompts contain no CR.
- Command: `llama-completion -m runtime/models/gemma-4-12b-it-qat-q4_0.gguf -dev Vulkan0
  -ngl 99 -c 65536 -fit off -n 512 -s 42 -no-cnv -v -f filler_gemma.txt`
  (runtime: llama.cpp build b12110, Vulkan, zip SHA-256 9732a5e4...874f).
- Placement: 49/49 layers on Vulkan0, none elsewhere; n_ctx = 65536; flash_attn auto.
- Buffers (Vulkan0): model 6,637.63 MiB; KV 1,024 MiB (8 full-attention layers,
  65,536 cells) + 480 MiB (40 SWA layers, 1,536 cells); compute 607.53 MiB
  = 8,749 MiB. Host: CPU_Mapped 787.50 MiB, Vulkan_Host compute 95.53 MiB.
- Windows counters: adapter dedicated 1,686 -> peak 10,632 MiB of 16,304
  (5,672 MiB headroom); llama process peak 8,953 MiB; adapter shared 115 -> 212 MiB.
- Speed: prefill 799 tok/s (28,255 tokens, 35.4 s); generation 58.2 tok/s at
  ~28k context. Wall 55.7 s.

### Headline J prompt token counts (46 prompts, no generation)
- Method: `work/probes/count_prompt_tokens.py` against llama-server
  (`work/probes/serve.sh`: -dev Vulkan0 -ngl 99 -c 65536 -np 1 -fit off --jinja).
  Each request rendered as ONE user message = request["prompt"] verbatim, exactly
  as Sonnet received it (batch_submit.py:199 sends no system message), through
  /apply-template, then /tokenize (parse_special on). Asserted the frozen prompt
  appears verbatim in the rendered text. Per-prompt counts saved in
  models/<slug>/headlineJ_prompt_tokens.json.
- gpt-oss-20b, chat_template_kwargs {"reasoning_effort": "high"}: template adds a
  system block "You are ChatGPT ... Knowledge cutoff: 2024-06 / Current date:
  2026-11-11 / Reasoning: high / # Valid channels ...". max 17,144 (pool_037),
  median 7,707, min 5,573. 17,144 + 32,768 = 49,912 <= 65,536. OK.
  NOTE: the template inserts the run date, so the system text changes per day.
- Gemma 4 12B, {"enable_thinking": true}: template adds a system turn holding
  only `<|think|>`. max 19,563 (pool_037), median 8,603.5, min 6,106 (with BOS;
  19,562 without). 19,563 + 32,768 = 52,331 <= 65,536. OK.
- Sonnet reference: max 26,851, median 11,940 input tokens.

### gpt-oss-20b: one generic request through llama-server
- Server started with --reasoning-format auto, n_slots 1, n_ctx_slot 65536.
- Request: user "List the four seasons in order, starting from spring. Answer as a
  JSON array of strings only.", chat_template_kwargs {"reasoning_effort":"high"},
  max_tokens 4096, temperature 1.0, top_p 1.0, seed 42.
- Result: finish_reason stop; content '["spring","summer","autumn","winter"]';
  reasoning_content separate (1,076 chars); no channel markers in content.
  usage prompt_tokens 87 = /tokenize count of the /apply-template render (87). MATCH.
  completion_tokens 263; 174 tok/s at short context.
- "high" reaching the model: the /apply-template render of the identical request
  body contains "Reasoning: high". The completion's own rendered prompt is not
  exposed by /slots or the default log, and the token count cannot tell high from
  low (same length). Direct confirmation still open.
- Finding: llama-server applied its own defaults top_k=40 and min_p=0.05 on top of
  the requested temperature/top_p (seen in /slots params). Preregistration must
  set top_k and min_p explicitly for every model.
- Servers stopped afterwards (TaskStop does not kill the exec'd llama-server.exe
  on Windows; it was ended with taskkill by PID).

## 2026-11-11 — gpt-oss re-send, sampler settings, fixed date, Gemma request, Sonnet output tokens

- gpt-oss re-send (approved, once): same generic request, server with `-v`.
  Same result (content '["spring","summer","autumn","winter"]', reasoning 1,076
  chars separate, prompt_tokens 87). The verbose log does NOT print the rendered
  prompt; its only "Reasoning:" line ("Reasoning: medium") is the startup
  template example (log line ~2007; the request began at line 2023), not the
  request. Direct confirmation still open: llama-server `--log-prompts-dir`
  writes the rendered prompt (confirmed on Gemma); needs one more request.
- Effective sampler settings read from /props (server defaults) and /slots
  (after request). gpt-oss defaults: temperature 0.8, top_p 0.95, top_k 40,
  min_p 0.05, typical_p 1.0, repeat_penalty 1.0 (last_n 64), presence 0,
  frequency 0, dry_multiplier 0 (base 1.75, allowed_length 2, last_n 64),
  xtc_probability 0 (threshold 0.1), top_n_sigma -1, mirostat 0, dynatemp_range 0,
  adaptive_target -1, seed 4294967295 (random). Gemma defaults differ only in
  temperature 1.0 and top_k 64 (from the GGUF). Sampler order: penalties, dry,
  top_n_sigma, top_k, typ_p, top_p, min_p, xtc, temperature.
- gpt-oss date: embedded template (SHA-256 b2215de6...0e89) calls
  strftime_now. A template that raises when current_date is missing is rejected
  by llama-server at startup (it test-renders with no kwargs). Final:
  work/templates/gpt-oss-20b.fixed-date.jinja (SHA-256 56290db7...59f5), one-line
  change, missing date renders "PINNED-DATE-MISSING". Served with
  --chat-template-file, --no-cache-prompt, --cache-ram 0.
  work/probes/render_check.py on the 46 headline prompts with
  {"reasoning_effort":"high","current_date":"2026-11-11"}: repeat renders
  identical, a different date changes only the "Current date:" line, prompts
  verbatim, missing date shows the sentinel, max 17,144 tokens (unchanged).
  Hashes: models/gpt-oss-20b/headlineJ_render_sha256.json.
- Gemma generic request (approved, once), server with --no-cache-prompt
  --cache-ram 0 --log-prompts-dir, enable_thinking true, all sampler values
  explicit. Logged rendered prompt: "<|turn>system\n<|think|>\n<turn|>\n<|turn>user\n
  ...<turn|>\n<|turn>model\n". finish stop; content '["Spring", "Summer",
  "Autumn", "Winter"]'; reasoning_content 1,112 chars, separate; prompt_tokens 36
  = /tokenize count of the render. /slots after the call: all 14 requested
  sampler values applied. Gemma's embedded template (SHA-256 6a1015c4...ab82)
  has no date or time call.
- Sonnet headline output tokens (frozen raw rows): base wave 40 succeeded +
  6 errored ("Your credit..." InvalidRequestError), resent in rs1 (6 succeeded);
  2 repairs (r1). 46 first-pass answers: min 29,892, p10 33,831, p25 40,234,
  median 49,594, p75 59,993, p90 67,899, max 81,897, mean 50,559; > 32,768: 43/46;
  > 44,000: 30/46; > 64,000: 8/46; all end_turn, none at 128,000.
- Frozen-code note: max_tokens_for() binds cap=MODEL_MAX_OUTPUT at definition
  (128,000); build_repair_spec and at_ceiling read batch_game.MODEL_MAX_OUTPUT at
  call time. The caller must send max_tokens = budget on every request.
  Rebuilt (in memory) Sonnet's two headline repair prompts: feedback 356 and
  180 chars.
- Drafted both preregistration entries in work/prereg_drafts/ (not committed).

## 2026-11-11 — Option B conditions: trained context, repair margin, gpt-oss B load test STOPPED (spill)

- Trained context (GGUF header via work/probes/gguf_meta.py; HF config.json;
  model cards): gpt-oss-20b gpt-oss.context_length 131072 (YaRN factor 32 from
  4096; config max_position_embeddings 131072). Gemma 4 12B gemma4.context_length
  262144 (config 262144; card "256K" for 12B). Option B contexts 98,304 and
  163,840 are within both. The 131,072 fallback for Gemma does not apply.
- Repair margin: frozen repair_report_text caps each list at 40 labels.
  Worst case built with it (40 missing + "(and 360 more)", 40 duplicated,
  40 invalid label-shaped ids, group-count sentence): 1,590 chars; 778 gpt-oss
  tokens, 1,262 Gemma tokens. Proposed margin 2,048 tokens for both.
  gpt-oss B: 98,304 - 17,144 - 78,000 = 3,160 >= 2,048. Gemma B: 163,840 -
  19,563 - 128,000 = 16,277 >= 2,048 (the formula would allow 142,229; budget
  kept at 128,000 = Sonnet's ceiling).
- gpt-oss load test at B (approved): work/probes/loadtest_server.ps1, llama-server
  with the preregistered flags, -c 98304, fixed-date template, --log-prompts-dir.
  The test request never ran (my bug: PowerShell stripped the JSON quotes passed
  to the background job). Memory samples during load (MiB):
    idle            adapter ded 2,332  shared 250
    weights loaded  adapter ded 13,440 shared 253   process ded 11,077 shared 0
    context alloc   adapter ded 14,037 shared 2,174 process ded 11,677 shared 2,040
  About 2 GB of llama-server's GPU allocations (size of the 2,304 MiB KV cache)
  went to shared system memory. => SPILL. Stopped as instructed: no request,
  no gpt-oss generic request (step 3), no Gemma B test.
- CORRECTION to the 64k gpt-oss load test above: it had the same signature
  (process dedicated 11,647 MiB vs 12,983 MiB of llama.cpp Vulkan0 buffers;
  adapter shared +1.6 GB). That was also a spill, not host-side buffers as I
  wrote. Gemma at 64k did not spill (process dedicated 8,953 MiB ~ its 8,749 MiB
  of buffers; shared +97 MiB).
- Vulkan limits for the 9070 XT (vulkaninfo): maxMemoryAllocationSize and
  maxBufferSize 0x80000000 (2 GiB); heap 1 DEVICE_LOCAL 15.92 GiB; heap 0
  (system) 15.58 GiB. Cause of the spill not yet established.

## 2026-11-11 — gpt-oss spill diagnosis (approved: one verbose start, no requests)

- Tools: work/probes/server_ctl.py (starts llama-server from argv lists written in
  Python; no shell quoting), work/probes/memsample.ps1 (memory sampler; reads
  counters only). loadtest_server.ps1 deleted (its JSON-quoting bug is why the B
  request never ran); requests are now built in work/probes/loadtest_requests.py.
- Run: config gptoss-b-verbose = prereg flags, -c 98304, fixed-date template, -v.
  Ready in ~7 s, no request sent, stopped. Log: work/probes/out/gptoss_b_verbose/.
  The memory sampler did not run (PowerShell execution policy; now invoked with
  -ExecutionPolicy Bypass for that one process). Memory counters for these exact
  buffers are the earlier B-attempt samples above (same flags minus -v).
- Ctrl+C reached the server ("stop: all tasks already finished") but it had not
  exited after 60 s; killed with taskkill /F. So llama.cpp's exit-time memory
  breakdown table was not printed; breakdown below is from the load lines.
- Placement (verbose): all 25 layers on Vulkan0; every non-SWA KV layer
  "dev = Vulkan0"; token_embd (q8_0) on CPU by design.
- llama.cpp memory breakdown (MiB):
    Vulkan0 model 10,949.35 + KV 2,304.00 (non-SWA, 98,304 cells, 12 layers,
    f16 K 1,152 + V 1,152) + KV 18.00 (SWA, 768 cells) + compute 186.77
    = 13,458 MiB on Vulkan0.
    Host: CPU_Mapped model 586.82, Vulkan_Host compute 119.28, output 0.77.
  llama.cpp saw "15419 MiB free" on Vulkan0 at start, so by its own accounting
  everything fits; no Vulkan allocation error or fallback message in the log.
- 2 GiB per-allocation limit: not implicated by the evidence. The 10.9 GB of
  weights are also allocated in <= 2 GiB pieces and stayed in VRAM; the KV cache
  is per-layer tensors of 96 MiB each, and nothing failed to allocate.
- Pattern across the three gpt-oss runs (llama-server process dedicated memory):
    64k (llama-completion): adapter idle 1,679; process dedicated peak 11,647;
      buffers on Vulkan0 12,983 -> ~1.3 GB elsewhere; adapter peak 13,329 of 16,304.
    98,304 (llama-server): adapter idle 2,332; process dedicated 11,677;
      buffers 13,458 -> ~1.8 GB elsewhere; adapter peak 14,037 of 16,304.
  The process stopped at ~11.65 GB dedicated both times, although the card still
  had ~3.0 GB and ~2.3 GB unused, and the idle baseline differed by 650 MB.
  Gemma at 64k (8,953 MiB) stayed under it and did not spill. Working hypothesis:
  a per-process limit on dedicated memory near 11.65 GB in this driver/WDDM
  setup, not the card running out. Two data points; not established.

## 2026-11-11 — Gemma 4 12B load test at Option B (approved; made-up prompts only)

- Command: `bash work/probes/run_loadtest.sh gemma-b work/probes/out/gemma_b
  gemma-b-fill gemma-b-long`. Server argv from server_ctl.py config gemma-b:
  prereg flags, -c 163840, -np 1, -fit off, no KV quantization (f16 default).
  Request bodies built in loadtest_requests.py (draft Gemma sampling, seed 42,
  enable_thinking true, ignore_eos true so generation length is controlled).
  Runtime: llama.cpp build b12110, Vulkan, zip SHA-256 9732a5e4...874f.
- /slots after the run: n_ctx 163840; temperature 1.0, top_p 0.95, top_k 64,
  min_p 0, typical_p 1, repeat_penalty 1, presence 0, frequency 0, dry 0, xtc 0,
  top_n_sigma -1, mirostat 0, dynatemp 0, seed 42 (all as sent).
- Request 1 (fill): 6,171 synthetic lines = 149,980 prompt tokens (tokenizer =
  reported, match), 8,192 generated (finish "length"). Prefill 811 s
  (185 tok/s average over 150k); decode 44.0 tok/s at depth 150k-158k.
- Request 2 (long): 836 lines = 19,551 prompt tokens (match; ~ the longest Gemma
  headline prompt, 19,563), 50,000 generated (41,215 reasoning chunks, 8,781
  content chunks, finish "length"). Prefill 17.6 s (1,109 tok/s); decode
  57.9 tok/s average; 62.2 tok/s at depth 21k falling to 54.8 at 63k.
- Decode time per token vs depth (both requests, 1,000-token intervals):
  ms/token = 15.03 + 0.0000503 * depth (max residual 0.12 ms).
- Memory (626 samples, ~3 s apart, whole run): llama-server dedicated max
  10,194 MiB, shared max 197 MiB; adapter dedicated 2,523 idle -> max 12,584 of
  16,304; adapter shared 150 -> max 343. Expected Vulkan0 buffers (not printed
  without -v): model 6,638 + KV 2,560 (8 full-attention layers x 163,840) + 480
  (SWA) + compute ~500 = ~10.2 GB = the dedicated figure, so no device buffer
  spilled; the ~200 MiB shared is in line with the host-side Vulkan_Host compute
  buffer (95 MiB at 64k). No spill. Server stopped with taskkill after Ctrl+C
  did not end it within 90 s.
- Worst-case time estimates (from the fit; display on the 9070 XT as now):
  one 128,000-token answer to the longest headline prompt: 18 s prefill +
  41.0 min decode = 41.3 min. A 46-request wave in which every answer hits the
  budget: 31.7 h (such answers are D6 and never re-asked). Absolute upper bound
  with every answer finishing just under budget AND needing a repair that also
  runs to the budget: 92 calls = 63.3 h, plus one 41-min resend per transport
  error. If Gemma's lengths resembled Sonnet's (median 49,594), ~14 min per
  request, ~11 h for 46.

## 2026-11-11/12 — gpt-oss-20b retest at Option B, monitor unchanged (approved; made-up prompts only)

- Commit 4471132 (drafts + log) pushed to origin/main before this run; the push
  also carried the earlier unpushed sandbox commits d711cbe, 9a2d26c, d2ae9b1.
- Command: `bash work/probes/run_loadtest.sh gptoss-b work/probes/out/gptoss_b
  gptoss-b-generic gptoss-b-fill gptoss-b-long`. Server: prereg flags, -c 98304,
  fixed-date template, --log-prompts-dir work/probes/out/gptoss_b/prompts, f16 KV.
  Bodies from loadtest_requests.py: reasoning_effort high, current_date
  2026-11-11, draft gpt-oss sampling, seed 42. Monitor still on the 9070 XT.
  Runtime: llama.cpp build b12110, Vulkan, zip SHA-256 9732a5e4...874f.
- Step 3 checks:
  - Logged rendered prompts (2 files, generic and fill) begin with the system
    block "Knowledge cutoff: 2024-06 / Current date: 2026-11-11 / Reasoning:
    high". Confirmed.
  - Prompt tokens: tokenizer = reported on all three requests (1,990; 87,984;
    17,128).
  - /slots after the run: n_ctx 98304; temperature 1.0, top_p 1.0, top_k 0,
    min_p 0, typical_p 1, repeat_penalty 1, presence 0, frequency 0, dry 0,
    xtc 0, top_n_sigma -1, mirostat 0, dynatemp 0, seed 42. All as sent.
  - Reasoning returned separately: every generated token came back as
    reasoning_content. But no request reached a final answer (the generic one
    used its 4,096 tokens reasoning; the others are fixed-length), so a final
    answer separated from reasoning under the fixed-date template is NOT yet
    shown.
- Memory: same spill as before. llama-server dedicated max 11,699 MiB, shared
  max 2,041 MiB; adapter dedicated max 14,336 of 16,304, adapter shared max 2,246.
- Speed: prefill 3,906 tok/s (2k), 4,097 tok/s (17k), 1,740 tok/s (88k).
  Decode by depth: 122 tok/s at 3.5k; 66 at 21k; 47 at 36k; 36 at 51k; 30 at
  66k; 21.8 at 93k; 21.4 at 95k. ms/token = 6.35 + 0.000422 * depth (max
  residual 0.41 ms) -- the depth slope is ~8x Gemma's, consistent with the KV
  cache being read partly from system memory.
- Worst-case times (longest headline prompt 17,144, budget 78,000): one answer
  at the budget 39.2 min; 46 requests all at the budget 30.0 h (D6, not
  re-asked); absolute ceiling with every answer just under budget plus a repair
  to the budget, 92 calls, 60.0 h. Sonnet-median-length answers (49,594 from a
  7,707 prompt): ~16.6 min each, ~12.7 h for 46.
- Server stopped with taskkill after Ctrl+C did not end it within 90 s.

## 2026-11-12 — gpt-oss spill accepted; final-answer check; Gemma render hashes; draft updates

- Decision (user): the gpt-oss spill at -c 98304 is accepted and recorded as the
  known placement, with the speed-by-depth table above as the evidence
  (draft Entry 1, "GPU placement").
- Ceiling check (from the 4,096-token generic request, 2026-11-11): sent
  max_tokens 4,096, reported completion_tokens exactly 4,096, finish_reason
  "length". So a budget hit reports output == budget, and the frozen at_ceiling
  (stop_reason max_tokens AND usage.output_tokens >= MODEL_MAX_OUTPUT) fires,
  provided the caller stores completion_tokens as usage.output_tokens (now in
  the draft's raw-row rule).
- Approved: one short generic gpt-oss request (config gptoss-b, test
  gptoss-b-final, `bash work/probes/run_loadtest.sh gptoss-b
  work/probes/out/gptoss_final gptoss-b-final`). Prompt "What is 17 + 25? Reply
  with the number only." 81 prompt tokens (tokenizer = reported). 52
  completion tokens, finish "stop". content = "42"; reasoning_content (41
  chunks) = the model's reasoning, separate; no harmony control tokens in
  content. Logged rendered prompt contains "Current date: 2026-11-11" and
  "Reasoning: high". C-1 closed.
- Gemma render hashes (no generation: /apply-template and /tokenize only;
  server log shows no slot launched): `work/probes/render_check.py` (now also
  handles templates without a date; required substring "<|think|>") on all 46
  headline prompts with {"enable_thinking": true}: repeat renders identical,
  prompts verbatim, "<|think|>" present, no date in any render; max 19,563
  tokens. Written to models/gemma-4-12b/headlineJ_render_sha256.json.
- Gemma template control markers (from the GGUF's embedded template): <|think|>,
  <|channel>, <channel|>, <|turn>, <turn|> (plus tool/media markers).
- Draft updates: Option B values filled in per model; gpt-oss placement
  accepted; raw rows store output_tokens/input_tokens; per-call control-token
  check on text (failure stops the wave); integrity-gate refusal is the
  primary result, allow_partial mean secondary and labelled "answered units
  only"; run order Gemma first, then gpt-oss.

## 2026-11-12 — runner, Sonnet replay, preregistration (no model calls)

- Probe scripts and small load-test outputs committed (6c23f65). Left out:
  `work/probes/out/gptoss_b/prompts/000000061904.txt` (298 KB made-up fill
  prompt), `work/probes/out/gptoss_b_verbose/server.log` (238 KB), empty
  marker files.
- Restart rule added to both draft entries (rows appended; a restarted runner
  skips custom_ids already present; an interrupted request is sent again as its
  first attempt; every restart logged; not a D4 resend, not a repair).
- Runner `work/runner/runner.py`. Streams from llama-server (as in the load
  tests) and assembles the non-stream response shape; the row writer mirrors
  `batch_submit.fetch` (max_tokens stop -> TruncatedAnswerError + partial_text;
  empty answer -> ZeroAnswerError). Found while writing it: llama-server writes
  `--log-prompts-dir` files in Windows text mode (LF -> CRLF; checked on the
  committed gpt-oss prompt log), so the logged-prompt check compares after
  CRLF -> LF and requires the render to contain no CR.
- `work/runner/replay_sonnet.py`: Sonnet's raw headline rows -> llama-server
  format -> fake server -> runner checks and row writer -> frozen resend, repair,
  score. Same 46/6/2 requests per wave, rows agree, every final answer equals
  the committed scored row, F1_J 0.7225, F1_L 0.8817, q 0.8206 (= KEY_NUMBERS
  to 1e-9). REPLAY PASSED.
- `work/runner/test_runner.py`: 11/11 injected-fault cases pass. Noted from the
  D6 case: the frozen integrity gate does not refuse a cell for a D6
  non-completion (recorded in J.rbnc.jsonl beside the rows), as for Sonnet.
- `tools/selfcheck_sonnet.py` PASSED. `server_ctl.py` gains `gemma-run` and
  `gptoss-run` (prompt logs in `logs/<slug>/prompts/`).
- Not yet exercised against a real server: the runner's `/props` fields
  (`total_slots`, `default_generation_settings.n_ctx`). A mismatch stops the
  wave before the first call is sent.
- Both entries copied into PREREGISTRATION.md (Gemma first) and committed with
  the runner.

## 2026-11-12 — Gemma 4 12B headline J run launched (approved)

- Preflight (approved; no completions): `gemma-run` server, GET /props:
  `total_slots` 1, `default_generation_settings.n_ctx` 163840 (exact field
  names), `build_info` "b12110-cd959bae9", chat template SHA-256 6a1015c4...ab82.
  Server stopped. (A first preflight started the `gemma-b` config by mistake,
  same flags minus `--log-prompts-dir`; repeated with `gemma-run`.) Output:
  `work/probes/out/gemma_props_run/`.
- Run started 2026-11-12 16:30 UTC with `bash work/runner/run_headline.sh
  gemma-run gemma-4-12b`. The launcher starts the server only through the
  committed `work/probes/server_ctl.py` `gemma-run` config, with no added or
  changed flags (its saved argv equals `server_ctl.py show gemma-run`, and the
  running llama-server command line was checked to be exactly that argv), and
  runs `work/runner/runner.py gemma-4-12b` unmodified (runner.py and
  server_ctl.py identical to commit 6a08a87). Memory sampled every 5 s to
  `logs/gemma-4-12b/mem.<stamp>.csv`. Runtime: llama.cpp build b12110 + Vulkan,
  zip SHA-256 9732a5e48887ca54d0bfe4af4324dc85fd56cd8cda19b52df3542fa6ebe6874f.

## 2026-11-12/13 — Gemma run: memory-logging gap, Windows Update restart, resume

- Memory sampler gap: the launcher's sampler filters the GPU adapter by LUID
  (`*15c57*`, the 2026-11-11 value); the adapter's LUID was 0x15da4 on
  2026-11-12, so `mem.20261112T163025Z.csv` holds zeros for the adapter columns.
  `memsample.ps1` gained an `-Adapter` parameter; a second sampler with
  `-Adapter '*15da4*'` wrote `mem.20261112T163025Z.luid15da4.b.csv` from about
  17:20 UTC (a first attempt, `...luid15da4.csv`, died with its shell).
  Process memory: 10,194-10,202 MiB dedicated, 197 MiB shared, throughout.
  Another program briefly took whole-GPU dedicated use to 16,066 MiB
  (2026-11-13 ~04:49-05:03 UTC); the server's own memory did not change.
- Base wave complete 2026-11-13 05:36 UTC: 46 rows, 38 end_turn, 8 D6
  (pool_003, 017, 018, 024, 037, 053, 054, 066), 0 transport errors, 0 empty
  answers, 0 check failures. -rs1 built empty. -r1 built with 38 requests:
  every end_turn answer failed validation (23 missing+duplicated labels,
  14 missing only, 1 duplicated only).
- 2026-11-13 09:12 UTC: Windows Update (MoUsoCoreWorker, then TrustedInstaller;
  "Operating System: ... (Planned)", KB5132061) restarted the machine twice
  (boots 09:13:57 and 09:15:30 UTC). The server and runner were killed during
  the 15th repair (pool_025-r1, server log ends at n_gen 36,398). No row was
  written for it. All 46 base rows and 14 -r1 rows parse intact. GPU driver
  unchanged (32.0.32015.7029); OS patch level changed by KB5132061.
- Resumed 2026-11-13 13:44 UTC on the user's instruction, under the
  preregistered restart rule, with the same command (`run_headline.sh
  gemma-run gemma-4-12b`, no runner flags; no check failure was outstanding).
  Server pid 39808. Run log: "RESTART final-headlineJ-r1: 14 rows already
  present, 24 requests to send"; pool_025-r1 is resent as its first attempt.
  Rebuilt specs matched the saved ones. The adapter LUID is now 0x15cee, so a
  second sampler writes `mem.20261113T134400Z.luid15cee.csv`; the launcher's
  own sampler file for this start records zeros for the adapter columns.

## 2026-11-13 — Gemma 4 12B headline J run complete

- Runner exited 0 at 18:01:15 UTC; server stopped by the launcher.
  -r1: 38 rows, 35 end_turn, 3 D6 (pool_020, 022, 025), 0 transport errors;
  -r1-rs1 built empty. 0 check failures over the whole run. 0 of 38 repaired
  answers valid.
- Frozen score (results/gemma-4-12b/final_headlineJ/): gate verdict "refused:
  none"; game J ok, answered 38/46, 8 D6 non-completions. Per-pool means over
  the 38 scored pools: F1_J 0.2615, F1_L 0.4655, q 0.5629 (q_micro 0.5507).
  Records recovered exactly 0/266. No answered-units-only copy was written
  (the gate did not refuse).
- Observation, not a re-score: the gate printed "fragments placed by policy
  0.0%" and COVERAGE 100%, but the scored rows' own `repair.policy_share`
  (written by frozen batch_game.finalise_row) is > 0 for all 38 units, mean
  0.188, and > POLICY_CAP 0.25 for 9 (pool_061 0.412, 005 0.393, 031 0.385,
  064 0.382, 007 0.352, 008 0.310, 065 0.309, 038 0.290, 070 0.251). Cause:
  for game J, integrity_gate takes policy_share = 1 - score_row's
  coverage_frac, and coverage_frac is computed on raw_response, which
  finalise_row has already completed with singletons, so it is always 1.0 on
  the batch path. Sonnet's headline rows all have policy_share 0.0, so its
  result is unaffected. Scorer left unchanged.
- verify_frozen at session end: PASS, 185 files byte-identical. Found, not
  touched: untracked, gitignored `__pycache__` dirs in frozen/adversaries,
  frozen/analysis and frozen/harness (cpython-314 .pyc, dated 2026-11-11
  23:41 UTC, i.e. from a system-Python 3.14 import on 2026-11-11, not from
  this run, whose Python calls set PYTHONDONTWRITEBYTECODE). Left for the
  user to decide.

## 2026-11-13 — Gemma 4 12B headline J: primary result is REFUSED (rule applied as written)

- Gate bug: for Game J, `joint_game.integrity_gate` sets a unit's policy share
  to 1 - `score_row`'s `coverage_frac` and never reads the row's recorded
  `repair.policy_share`. On the batch path `batch_game.finalise_row` has
  already completed `raw_response` with singletons, so `coverage_frac` is
  always 1.0 and the gate always sees 0% placed by policy. The gate therefore
  printed "ok" / "refused: none" for this cell.
- 9 units are over `joint_game.POLICY_CAP` (0.25) by their recorded
  `repair.policy_share`: pool_061 0.412, pool_005 0.393, pool_031 0.385,
  pool_064 0.382, pool_007 0.352, pool_008 0.310, pool_065 0.309,
  pool_038 0.290, pool_070 0.251.
- PREREGISTRATION.md ("Primary result and the integrity gate") says a unit
  over `joint_game.POLICY_CAP` makes the refusal the primary result. Applying
  that rule as written, the Gemma 4 12B headline J cell is REFUSED. This is
  the preregistered rule, not a post hoc change; the gate's printed verdict is
  the error. Nothing in frozen/ or the scorer was edited; the gate is to be
  fixed separately in the main session.
- Primary result: REFUSED; 9 units over the cap; 0 units without an answer;
  8 D6 non-completions; 0 transport errors; 38/38 invalid after repair;
  completion 38/46. Recorded in results/gemma-4-12b/PRIMARY_RESULT.md.
- Secondary, as the refusal path writes it: `work/runner/score_secondary.py`
  runs the frozen `batch_game.score(waves, ..., allow_partial=True)` on the
  same waves (base + -r1) into results/gemma-4-12b/final_headlineJ_answered_units_only/,
  labelled SECONDARY, "answered units only". Its J.jsonl and report body are
  identical to final_headlineJ/. Per-pool means over 38 pools: F1_J 0.2615,
  F1_L 0.4655, q 0.5629.
- No new model run until the gate fix is in and a new preregistration entry
  for the next models is written (user's instruction).

## 2026-11-13 — Sonnet-dependence sweep: runner, offline tests, smoke tests

- Preregistration entry committed and pushed (515571f, merged with origin as
  561ca0d) before any API request. Runner committed (d78ada1) before the smoke
  tests: `work/runner/api_runner.py`, `score_api.py`, `test_api_runner.py`
  (5/5 offline: Sonnet replay reproduces 0.7225/0.8817/0.8206 with identical
  final answers; content filter, provider mismatch, base-wave cap and a
  below-budget length stop behave as preregistered).
- `score_api.py` offline on the references: Sonnet PASS (46 pools
  0.7225/0.8817/0.8206; 41 pools 0.7218/0.8825/0.8192). Gemma REFUSED (9 over
  cap, 8 D6, 38/46), secondary 0.2615/0.4655/0.5629 (46) and
  0.2612/0.4638/0.5643 (41).
- OpenRouter balance before any request: usage $0, limit $10, remaining $10.
- Smoke tests (dummy prompt, no evaluation text; `logs/smoke_tests.jsonl`):
  gpt-oss-20b CoreWeave, reasoning 98 tokens; gpt-oss-120b CoreWeave, reasoning
  264; llama-4-maverick Parasail; deepseek-v3.2 GMICloud, reasoning 41; gpt-4.1
  tier `default`, reported model `gpt-4.1` (no version string; the version pin
  rests on the deployment's settings); gpt-5.6-sol tier `flex`, echoed reasoning
  `{effort: max, mode: standard, context: all_turns}`, `max_output_tokens`
  128000, `truncation` disabled; 0 reasoning tokens on the trivial prompt. All
  checks pass. Kimi not smoke-tested (no Kimi request before its decision).
- Two runner fixes found by the smoke tests, neither a protocol change: the
  Azure endpoint already carries `/openai/v1` (first gpt-4.1 smoke request got
  HTTP 404, no tokens billed); Azure responses now also checked for the echoed
  reasoning effort, `max_output_tokens` and `truncation` (a mismatch halts).

## 2026-11-13 — gpt-oss-20b: HALT in the base wave (provider output limit)

- Started 21:55 UTC. Halted 22:06 UTC under the entry's halt rules; no new
  request sent after the first halt; in-flight requests finished.
- 11 base rows written (all `end_turn`, 48k-98k output tokens), cost $0.1064;
  OpenRouter balance after: $9.8644 remaining.
- 5 halts (`raw/gpt-oss-20b/final-headlineJ.check_failures.jsonl`):
  - pool_018, pool_007: HTTP 400 from OpenRouter before generation: prompt +
    117,964 > the endpoint's 131,072 context (14,748 + 117,964; 13,552 +
    117,964). Not a transport error or content filter.
  - pool_008, pool_006, pool_005: `finish_reason length` at 107,549 / 112,188 /
    111,621 output tokens, below the 117,964 budget, all reasoning and no answer.
    Prompt + output = 117,752 / 117,759 / ~117.8k: CoreWeave appears to stop at
    about 117,760 total tokens, not at the listed 131,072 context.
- Cause: the preregistered budget (117,964 = the listed max_completion_tokens)
  cannot be reached for any headline prompt on this endpoint; the entry's D6
  rule (stop at the full budget) cannot apply. Applies equally to gpt-oss-120b
  (same provider, same listing). Waiting for the user's decision.

## 2026-11-13 — Amendment applied: gpt-oss on AkashML fp4, 110,000 budget

- Amendment committed and pushed before any further request (a4ef6ca).
- Runner: gpt-oss-20b/120b pinned to AkashML fp4 (`only`/`order` akashml,
  `allow_fallbacks: false`), `max_tokens` 110,000 (D6 at 110,000); HTTP 400 on
  context length is now an explicit halt; Parasail fp4 fallback wired
  (`--parasail-fallback`, 120b cap $3.00), not used.
- The 11 CoreWeave rows and the run's attempt/check-failure logs moved to
  `logs/gpt-oss-20b/superseded_coreweave_117964/` (never scored).
  Correction: the superseded spend is **$0.1501**, not $0.1064. $0.1064 was
  the 11 written rows only; the 3 length-stopped calls (pool_008/006/005) were
  billed too (OpenRouter `usage.cost`, $0.0437). Reported in gpt-oss-20b's totals.
- Smoke tests (`logs/smoke_tests.jsonl`), neutral dummy prompt of 76,124 chars
  (pool_037, the longest headline prompt, is 75,956), max 110,000:
  gpt-oss-20b and gpt-oss-120b both PASS — provider AkashML, model as pinned,
  `finish stop`, answer "OK", 16,252 prompt tokens reported; cost $0.0008.
- A second smoke attempt with a longer 93.5k-char dummy got HTTP 400 from
  OpenRouter's own pre-routing check (`provider_name: null`): OpenRouter sizes
  prompts at ~3.97 chars/token (23,701 estimated + 110,000 > 131,072). That
  dummy was longer than any headline prompt (my overshoot, not a provider
  failure). By the same estimate pool_037 is 19,142 + 110,000 = 129,142, which
  fits. No fallback taken.

## 2026-11-14 — Lines started; gpt-4.1 and gpt-oss-20b done

- 00:09 UTC both lines started (Azure: gpt-4.1 -> gpt-5.6-sol; OpenRouter:
  gpt-oss-20b -> gpt-oss-120b -> llama-4-maverick -> deepseek-v3.2).
- gpt-4.1: REFUSED (46 and 41 pools): all 46 answered, 44 over the policy cap
  (it omits fragments; mean policy_share 0.39). Secondary F1_J 0.2363. $2.42.
- gpt-oss-20b (AkashML): all waves done, $0.5688 (+ $0.1501 superseded =
  $0.7189). AkashML does reach the full 110,000 (3 D6 units). The runner then
  crashed in my scoring wrapper, not in a protocol check: `means()` averaged
  `q`, which the frozen `score_row` returns as None when K = 0 (no guessed
  linked pairs). Fixed to the frozen convention (q undefined -> left out of the
  q mean, as in `game_j_adjacency.py` / `build_master.py`), with the count of
  rows where q is defined reported beside it. F1_J/F1_L unaffected; Sonnet,
  Gemma and gpt-4.1 re-scored with identical means (all q defined). Offline
  tests 5/5. OpenRouter line restarted at gpt-oss-120b (01:08 UTC).
- gpt-oss-20b: REFUSED (46 and 41): 6 units without an answer, 32 over the cap.
  Secondary F1_J 0.0759, F1_L 0.1396, q 0.5477 (defined on 21 of 40).
- gpt-5.6-sol (Azure flex, effort max): waves done 01:11 UTC, $24.19 of $50.
  REFUSED (46 and 41): pool_005 and pool_037 ended `response.incomplete`
  with reason `content_filter` (after ~100 s and ~130 s of streaming), never
  resent per the entry. The other 44 were all valid on the first pass (no
  repair needed, policy_share 0 everywhere, 0 D6). Secondary (answered units
  only, 44): F1_J 0.8470, F1_L 0.9515, q 0.8906; 41 pools (39): 0.8461 /
  0.9532 / 0.8880. Note: the runner records $0 for the two filtered
  responses; any tokens Azure billed for them before the filter are not in the
  $24.19 (usage was not captured on the incomplete path).

## 2026-11-14 — gpt-oss-120b: HALT in the base wave (AkashML length stops)

- Started 01:08 UTC; halted 01:28 UTC (amendment halt: a length stop below
  110,000); in-flight requests drained, line stopped 01:49 UTC. llama-4-maverick
  and deepseek-v3.2 not started.
- 27 base rows written, cost $0.4498 (cap $1.50).
- 2 halts (`raw/gpt-oss-120b/final-headlineJ.check_failures.jsonl`), both
  reasoning with no answer: pool_019 at 109,837 output tokens (prompt 7,535;
  total 117,372); pool_035 at 108,089 (prompt 9,958; total 118,047). Not a fixed
  total limit (the totals differ; gpt-oss-20b on AkashML reached the full
  110,000 with totals up to 117,812). Waiting for the user's decision.
- OpenRouter key 01:49 UTC: usage $1.1697, limit_remaining $8.9806 (the key's
  remaining does not equal limit - usage; see the 00:09 reading, to settle
  before the Kimi decision).
