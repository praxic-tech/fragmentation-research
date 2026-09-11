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

### Check #2 on pool 1 — 2026-09-11: 30 answers cut off at max_tokens

Pool 1 (msgbatch_018bZWoLWVBec9de8iR5wYYG) returned 30 of 88 answers cut off at
their max_tokens cap: 29 empty (sonnet reasoned until the cap) and one "succeeded"
O answer (subject-verb-clause, prose_0383) whose JSON list ended mid-label. The
empties were refused by require_complete as designed. The cut-off "success" was
caught by nothing and had been filed in the answer store; it was removed with a
record (results/answer_store.jsonl.removed.jsonl).

Diagnosis: TRANSPORT, not answer-affecting. The caps were sized at 2x the cost
model's anchors, and sonnet wrote 1.6x (O) and 1.9x (J) more than the anchors,
with a 2,048 floor that starved small documents. A cap only truncates -- it does
not change the tokens before the cut -- so the 58 finished answers are exactly
what they would have been under larger caps, and stay.

Fix (tests: harness/test_truncation.py, G1e): J at the 128k model ceiling; O at
3x the measured rate, floor 16k; fetch records stop_reason and treats a
max_tokens stop as a hole; scoring and the answer store refuse cut-off answers,
including old rows that used their whole cap; a resubmission of a cut-off
request keeps its prompt byte-identical and raises only the cap (to the model
ceiling if cut off again, and never past it); repairs use at least the current
sizing. The ledger checks the tripwire against 2x the measured-rate forecast
and the $167 hard limit against the worst case.

Re-ask: runs/grid_A_pool1_rs1.json, 30 requests, prompts byte-identical,
manifest runs/grid_A_pool1_rs1_manifest.json, msgbatch_019icRfo9o3FWGrnNy4ZC9Fj.
Expected $3.07, worst case $7.89, approved by the user before submission.
27 of 30 answered ($4.01); 3 O documents in random cells were cut off again at
16-21k and went to the model ceiling in a second and final resubmission
(runs/grid_A_pool1_rs2.json, msgbatch_01HNUXj6D6A3g3TscV45uNhK, $0.22, approved
before submission): 3 of 3 answered. Pool 1 is 88 of 88 answered; $9.06 total.

### Scoring fix on pool 1 — 2026-09-11: a complete answer scored as unparseable

random__token-window was REFUSED because prose_0383's O answer counted as "no
model answer". The answer was complete -- all 56 labels in a ```json fence --
but the prose before it contained "[35-year-old with TTTS/band complication]",
and extract_json_array took the first "[" to the last "]". Diagnosis: SCORING,
so under this clarification the stored answers are re-scored and nothing is
re-bought. The parser now takes the longest span a JSON decoder reads as a list,
fenced blocks first (harness/test_parser.py, G1f). Checked against every stored
answer text (175): exactly this one answer changes, from unparseable to its 56
labels; the other 173 parse identically.

### Pool 1 complete — 2026-09-11: all six predeclared checks pass; the slice is kept

Repair round 1 (runs/grid_A_pool1_r1.json, 4 units each missing one label,
msgbatch_011iGH8JaYNu4d8WJoDC1xeQ): 3 answered, 1 cut off because repairs took
the round-0 cap, which knew nothing of the 128k resubmission that answered it.
Repairs now always go out at the model ceiling. That one request was resubmitted
unchanged at 128k (runs/grid_A_pool1_r1_rs1.json,
msgbatch_01DFWaoemD7hLh7kEwR6cHRp) and answered. Checks: 1 masking pass;
2 transport 88/88 after 2 resubmissions; 3 integrity 11 of 11 cells; 4 one
repair round, 4 units; 5 $9.75 observed, every wave settled; 6 re-scoring
identical. Report: results/grid_A_scored/REPORT.txt. Under the D4 clarification
the slice's answers are kept and are part of the final grid.

## D5 — 2026-09-11: the grid is pruned after the pool-1 screening slice

**Not preregistered.** These cuts were informed by pool 1's results (the
development-screening slice), and the paper says so.

- **Cut:** semantic × token-window, coherence-sever × sentence.
- **Kept, 9 cells:** random × {sentence, clause, token-window}; semantic ×
  {sentence, clause}; coherence-sever × {clause, token-window}; subject-verb ×
  {sentence, clause}. Clause stays a complete head-to-head row across random,
  semantic, coherence-sever and subject-verb.
- **semantic × sentence is the sentence / reference condition.** It is in
  effect standard sentence-boundary splitting, so it is NOT evidence for a
  distinct semantic cutter. It is the comparator for the repeats, the J-vs-N
  curve and the headline, whose cut is the same (data/prose/prose_fragments.jsonl
  is semantic × sentence at full length, docs/corpus_build.md).
- **llm-cut (Kimi K3) leaves the main confirmatory grid.** The paper is about
  deterministic, reproducible cut strategies; the budget goes to the stronger
  hierarchical adversary. D3's cutter work stays as development material.
- **Pool 1 is screening data. This supersedes the D4 clarification.** Pool 1
  was an exploratory slice used to decide which cells warranted evaluation, so
  it is not independent of cell selection. It is reported separately. The
  reduced grid is frozen now; pools 2–25 characterise the selected cells after
  selection; an all-25 sensitivity analysis may be reported, labelled as
  development. The 46 untouched headline pools remain the confirmatory evaluation.
- **The dropped cells' pool-1 results are preserved** for the audit record and
  the appendix: results/audit/pool1_screening/ (all 11 cells' scored rows,
  per-unit metrics, the full report, SHA256.json).

Pending before pool 2 (analysis/budget_final.py): the grid's size (pools, O
documents per cell), the hierarchical attacker's scope, and the rule for an
answer that cannot fit in the model's 128k output.

## D6 — 2026-09-11: an answer that cannot fit in the model's output is a resource-bounded non-completion

**Why it happens (measured on pool 1, before any rule was set).** The one-shot
schema is already minimal: prompt_J asks for "ONLY a JSON array ... of item
labels ... No explanation, no markdown", and labels are 9-character masked
aliases. Every J answer's visible text was at most ~2,000 tokens (a 272-fragment
pool's whole answer is 3,313 characters), while billed output ran 31k-97k:
**at least 96.7% of every J answer's output is sonnet-5's adaptive reasoning**,
which is billed as output and counts against max_tokens. Output therefore scales
with how long the model thinks about the pool, not with the answer: the same
141-fragment size took 31k on one pool and 68k on another. Shortening labels
would save under 2% of output. The only levers that cut reasoning -- effort or
thinking settings, or prompting it to think less -- change the attacker, and
RUN_PLAN found effort "low" returned invalid output. So a pool that exceeds
128k is reasoning-bound: a genuine resource bound of this attacker.

**The rule** (revised the same day: one attempt, no re-ask at the ceiling).
- Every J and O request gets the model's full 128k ceiling. Not 64k: 5 of pool
  1's 11 J answers needed more than 64k, mostly in the strongest defences, so
  a lower cap would handicap the attacker exactly where the defence looks best.
  Reasoning is not reduced for the primary attacker (no effort / thinking cut).
- ONE attempt per unit. Whatever it finishes at -- 30k, 60k, 95k -- is scored.
- A call that exhausts 128k without an answer is a RESOURCE-BOUNDED
  NON-COMPLETION (RBNC). It is NOT re-asked: a pool that exhausted the full
  budget once would most likely do so again, and re-asking only repeats the bill.
- One retry only for what is clearly transient: an errored / expired request
  (resubmitted unchanged), or a malformed answer that did not exhaust the
  budget (the one repair round, original prompt). A repair that itself
  exhausts 128k leaves the unit with its earlier real answer.
- An RBNC is recorded (`<game>.rbnc.jsonl` beside the cell's rows), never
  scored: no F1 = 0, no completion-policy fill. Completed units are scored
  normally. Every cell reports completion (scored / attempted) and its RBNCs.
- An RBNC does not refuse a cell. Transport holes and POLICY_CAP still do.
- An operational attack-success measure that counts RBNCs may be defined
  separately; it is not the headline metric.
- The hierarchical attacker decomposes a pool into many small pairwise
  decisions and does not share the one-shot reasoning bottleneck; it is the
  architecture that covers what one-shot J cannot finish.
- Reasoning summaries are not stored: the usage counts already show the cost is
  internal reasoning, and the scientific object is the reconstruction.
- Priced in analysis/budget_final.py: an RBNC is paid once at 128k.

Paper wording: the one-shot attacker was given the model's full per-call
reasoning budget; pools that exhausted it are reported as non-completions; a
separate hierarchical attacker decomposes reconstruction into smaller pairwise
decisions and does not share that bottleneck.

## D7 — 2026-09-11: pre-pool-2 fixes from the audit packet

From docs/audit_packet_final_run.md. All chosen from code, text statistics and
fidelity checks, never from attack scores.

- **coherence-sever, re-cut.** Topic shift is now "the adjacent units share no
  content word" (was content-word Jaccard < 0.12, which fired at 82-84% of
  boundaries because 57-69% of adjacent units share no content word at all).
  Token-window counts whitespace words, the ruler random and semantic use (was
  spaCy tokens, 9.8-word windows). New cells: × clause 3,926 fragments (was
  5,119), cutting 72.3% of clause boundaries (was 95.3%); × token-window 6,977
  (was 8,448), 11.88 words per fragment against 11.86 for random / semantic.
  Pool 1's coherence-sever numbers describe the OLD cells, archived in
  results/grid_A/_superseded_2026-09-11/. The new cells were not screened; D5's
  decision to keep them stands on design grounds (a complete clause row).
- **subject-verb, re-cut.** A cut must fall on whitespace (4 frame-A cut points
  split "patient’s" / "MP™"). × sentence 7,115 fragments, × clause 8,418; every
  re-cut cell rejoins its source exactly, 175/175.
- **Presentation seeded per unit.** Label and order shuffles are seeded from
  sha256 of the unit's fragment ids and texts, the run seed and the purpose,
  as independent streams (joint_game._unit_seed). Rebuilt pool-1 prompts: shown
  order vs truth τ mean +0.015 (was −0.137, never positive); no size repeats a
  pattern. Every prompt changes, so pool-1 answers are not reused by the answer
  store; pool 1 is screening data (D5).
- **The hierarchical attacker runs on the Batches API** (adversaries/hier_batch.py):
  waves by replay of the unchanged attack(), D6's rules per pair batch (128k,
  one attempt, exhausted batches never re-asked, one transport retry, HOLE_CAP
  25%). Test G2c: batch waves reproduce the offline attacker exactly, including
  when clustering needs bridge rounds.
- **Live sample, approved by the user** (runs/hier_sample1.py,
  msgbatch_01NUXxhBgUzdLnz6fyYYeuRD): grid pool_000 × semantic × sentence, 141
  fragments, 0 headline documents. 24 pair batches, 24/24 answered, 467/467
  pairs, no batch near the ceiling, no bridge round needed, pool scored.
  **$0.5049** (forecast $0.50 at the ×2.3 reasoning multiplier: ~187 output
  tokens per pair, measured). Result: joint F1 0.380, advantage +0.285, linkage
  F1 0.529, q 0.718. One-shot J on the same pool (pool-1 screening): joint F1
  0.642, advantage +0.587, linkage F1 0.811. One pool; development data.

## D8 — 2026-09-11: hierarchical k, its 12 pools, the G3 diagnostic, the final price

- **k is chosen from the blocker, never from reconstruction F1.** The rule was
  fixed before any number was seen (analysis/hier_blocker_calibration.py): the
  smallest k in {5, 10, 20} with ≥ 90% of records fully connected by
  same-record candidate edges and ≥ 80% adjacent-pair recall; otherwise the
  smallest k past which the next gains < 5 points on both. Development data
  only: the 25 development pools at full length, reference cut, masked as in
  the run; 0 headline documents.

  | k | records connected | adjacent recall | same-record recall | candidate precision | $ / pool |
  |---|---|---|---|---|---|
  | 5 | 13.1% | 21.8% | 8.8% | 51.0% | 0.78 |
  | 10 | 45.7% | 30.7% | 14.2% | 42.9% | 1.49 |
  | 20 | 80.6% | 41.4% | 22.4% | 34.7% | 2.91 |

  No k meets the thresholds and every step still gains > 5 points, so the
  fallback gives **k = 20**, and coverage is reported as **inadequate at every
  tested k**: TF-IDF blocking misses most true adjacencies in this corpus,
  because consecutive sentences rarely share a content word -- the property that
  also broke coherence-sever's old topic-shift rule. Frozen as
  adversaries/hier_batch.py DEFAULT_K = 20. The $0.50 live sample ran at k = 5
  and no longer describes the final attacker.
- **Its 12 headline pools are prespecified** (data/pools/hier_headline_12.json):
  the first 12 of the 46 by sha256('hier-subset|' + pool_id). Ids only; no
  fragment, text or outcome was read.
- **Its role:** a decomposed, scalable attacker and a check on the one-shot
  ceiling -- can it complete pools one-shot J cannot? It is not described as
  stronger unless the final results support that: the live sample scored below
  one-shot J on its pool, and its blocker is measurably lossy.
- **G3** runs on development pool pool_000 × {semantic, random} × sentence, each
  asked masked and with RAW fragment ids in true order, as a masking
  SIDE-CHANNEL diagnostic -- not a requirement that masked reconstruction be
  low (results/audit/g3_diagnostic.json).
- **The final price** is results/budget_final.txt (analysis/budget_final.py).
  No headline or grid request is submitted until the user approves it.

## Development history — 2026-09-10: headline documents used before frame A existed

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

Attackers were run on these documents during development and their scores were
seen. What that informed: operational design (pool size, max_tokens sizing,
repair, integrity checks), the choice of J as the headline game alongside the
threat-model argument, and the gpt-oss llm-cut prompt choice (on cut statistics,
not attack scores). The
llm-cut prompt is re-selected for Kimi on development and held-out documents only
(D3), so that tuning contact does not carry into the final configuration. No
strategy was selected and no headline estimate was computed on these documents.

Decision (2026-09-10, Aiden): ALL 46 POOLS ARE THE PRIMARY HEADLINE SET. No
fragmentation strategy was chosen or rejected, and no prompt, threshold or
hyperparameter feeding the headline was tuned on these documents' performance.
The coherence-sever repair and the corpus rebuild were correctness fixes, not
tuning. This is development history, not contamination; the 28 never-touched
pools remain available as an optional robustness check.
