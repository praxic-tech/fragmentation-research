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

## D4 clarification — 2026-09-10: the first pool is a slice, not a pilot

The paid first-pool run is the FIRST STAGED SLICE of the final 25-pool grid, not a
disposable pilot and not a separate dataset. Staging one pool first exists only to
limit financial exposure to implementation or provider failures.

Everything that affects the 11 current cells is FROZEN before the API is called
and recorded in a committed run manifest: git commit, every cell_manifest.json
(cutter, parameters, source sha256), fragment-file hashes, the spec's sha256, the
O and J prompt templates, model id, the max_tokens sizing function, masking seed.

The slice's answers are KEPT in the answer store and INCLUDED in the final grid
results if it passes these predeclared OPERATIONAL / INTEGRITY checks:

1. Masking: every prompt passes preflight (0 blocked), and no request contains a
   document from the 46 headline pools.
2. Transport: after at most 2 resubmissions, 0 requests missing, errored, expired,
   canceled or empty (require_complete passes).
3. Integrity gate: every expected unit has a real model answer and no unit is over
   POLICY_CAP (25% of fragments placed by the completion policy).
4. Repair: at most 1 repair round, as specified; repair rates are reported.
5. Spend: every wave settled in the ledger, within the $120 tripwire.
6. Reproducibility: re-scoring the stored answers reproduces the same numbers.

NO PERFORMANCE SCORE (tau, F1, advantage, longest readable stretch, anything
else) is used to decide whether the slice is valid.

If a failure is traced to TRANSPORT, the affected requests are resubmitted. If it
is traced to SCORING, the stored answers are re-scored and nothing is re-bought.
Only an ANSWER-AFFECTING change (prompt, cut, masking, presentation, model)
invalidates answers, and then only the affected ones: the answer store keys on
the exact model and prompt, so a changed request can never be served an old answer.

## Disclosure — 2026-09-10: headline documents touched BEFORE frame A existed

Development work done before D2 was taken used documents that frame A later
assigned to the 46 headline pools. Measured with batch_game.headline_docs():

| development work                                             | docs | headline docs |
|--------------------------------------------------------------|------|---------------|
| 8-document free-tier probe (O runs, llm-cut defender, Memon)  |    8 |             5 |
| 25-document pilot_reference (J pilots, Memon n-sweep, hier smoke) | 25 |        12 |
| llm-cut decision cache (v1 / v2 / v3 prompt comparisons)      |   23 |            14 |
| week-6 three-way llm-cut cells                                |   11 |             7 |

Together: 21 headline documents in 18 of the 46 headline pools. 28 headline
pools were never touched. Since 7ac35ad, build_spec refuses any request that
touches a headline document, so no further contact is possible on the paid path.

What the contact informed: operational design only (pool size, max_tokens
sizing, repair, integrity checks) and the gpt-oss llm-cut prompt choice. The
llm-cut prompt is re-selected for Kimi on development and held-out documents only
(D3), so that tuning contact does not carry into the final configuration. No
strategy was selected and no headline estimate was computed on these documents.

How the 18 touched pools are handled in the headline analysis: DECISION PENDING.
