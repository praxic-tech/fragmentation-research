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
