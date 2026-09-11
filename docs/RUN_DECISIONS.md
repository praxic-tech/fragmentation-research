# Run decisions — frozen 2026-09-10

Decisions taken by Aiden before any confirmatory spend. Each one is recorded
here so it cannot drift after results are seen. Change a line only with a new
dated entry below it, never by editing the original.

## D1 — classic Greedy / MST ordering baselines are fixed and renamed

Measured: as the harness ran them, Greedy scored tau +0.3232 and MST +0.7044 on
the prose corpus. With masked labels in shuffled order both fall to chance
(-0.0304, -0.0175). Word-bigram Jaccard is exactly 0 for 86.7% of within-document
pairs, and ties were broken by raw fragment id or list position while the
fragment file lists every document in true order (500/500). MST was also
non-deterministic across processes (set iteration under hash randomisation:
0.704416 / 0.704440 / 0.704190 for three seeds).

- Game O for both runs on masked labels with shuffled presentation, as Game L
  already did.
- Tie-breaking is deterministic and truth-independent: no iteration over sets,
  no ordering by raw id or by input position.
- Re-run, and the new O results SUPERSEDE the old. The old numbers are kept only
  as an audit record.
- Renamed Jaccard-Greedy / Jaccard-MST ("Memon-inspired") unless the actual PPM
  plus tree-pruning method is implemented.

## D2 — frame A

- The grid runs on the 25 pools in `data/pools/linkage_grid.json`: the fixed
  DEVELOPMENT / GRID pools.
- The other 46 pools in `data/pools/pools.json` are the HEADLINE pools and stay
  COMPLETELY UNTOUCHED: no testing, no tuning, no prompt selection, no requests
  of any kind until the headline run.
- The grid corpus is rebuilt on the 175 development-pool documents and every
  cell is cut on it.

## D3 — Kimi K3 replaces gpt-oss-120b as the single LLM cutter

- One LLM-cutter cell only; no second LLM-cutter dimension.
- Prompt selection (v1 / v2-adversarial / v3-strategist) on development-pool or
  held-out documents only.
- The exact cutter configuration is frozen in a committed manifest: provider,
  model id, prompt version and hash, units, temperature, max_tokens, reasoning
  setting, decision-cache path.

## D4 — paid testing is staged

- Build and dry-run **1 pool per cell** first. Spend only after the dry run
  passes.
- Inspect results and telemetry before anything else is spent.
- The second pool is authorised separately.
- Every paid answer is filed in the answer store, so test answers are reused by
  the real run rather than paid for twice.
