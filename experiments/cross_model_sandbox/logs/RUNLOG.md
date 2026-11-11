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
