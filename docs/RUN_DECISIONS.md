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
- *Clarification, 2026-09-13 (docs/adversaries.md):* the parenthetical
  "Memon-inspired" above is superseded. Jaccard-Greedy and Jaccard-MST are
  Michael's classical game-O orderers, formerly labelled Memon-Greedy /
  Memon-MST. They use symmetric word-bigram Jaccard and are **not**
  Memon-inspired in any sense. "Memon-inspired" names only
  adversaries/memon_joint.py. They remain game-O classical floors, and their
  historical game L column is the shared TF-IDF grouper, not a Jaccard linkage
  attack. This entry is kept as written, as the record of the decision.

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
  low (results/audit/g3_diagnostic.json). **Run** (msgbatch_018YeW5fT2GMQhHy77saJGEH,
  4/4 answered, $0.5529):

  | cell | arm | joint F1 | agrees with label numbers (expected from truth alone) | agrees with shown order (expected) |
  |---|---|---|---|---|
  | semantic × sentence | raw ids, true order | 0.994 | 0.999 (0.999) | 0.999 (0.999) |
  | semantic × sentence | masked | 0.685 | 0.505 (0.511) | 0.511 (0.495) |
  | random × sentence | raw ids, true order | 1.000 | 1.000 (1.000) | 1.000 (1.000) |
  | random × sentence | masked | 0.759 | 0.526 (0.516) | 0.485 (0.487) |

  The planted leak is exploited completely. Masked, the answer's order agrees
  with label numbers and with the shown order exactly as often as its accuracy
  implies (every gap ≤ 0.016, about one standard error at ~1,230 pairs): no
  measurable id or presentation side channel. Masked reconstruction is high
  because the model reads the content, which is the finding, not a leak.
- **The final price** is results/budget_final.txt (analysis/budget_final.py).
  No headline or grid request is submitted until the user approves it.

## D9 — 2026-09-13: the budget is $200

The user raised the budget from $167 to **$200, out of pocket**. Sales tax is
**6.25%**, so the ledger's HARD_LIMIT is $200 / 1.0625 = **$188.23 in API
credit** (rounded down). Every credit figure costs 1.0625x out of pocket. The plan to run is chosen against this wall from
results/budget_final.txt and approved by the user before any headline or grid
request is submitted.

## D10 — 2026-09-13: hierarchical go / no-go on development data (oracle ceiling)

A DIAGNOSTIC, never an attacker result (analysis/hier_oracle_ceiling.py,
results/audit/hier_oracle_ceiling.json). The frozen k = 20 blocker, candidate
graph, bridges, clustering and ordering, with Sonnet's pair judgements replaced
by the answer key on the exposed pairs only. Development pools only; the rule
was fixed before any number was seen (median oracle F1_J on the headline
analogue: ≥ 0.80 KEEP, < 0.60 blocker-limited, between SECONDARY).

| data (25 dev pools each) | same-record recall | adjacent recall | records connected | oracle F1_L | oracle q | oracle F1_J |
|---|---|---|---|---|---|---|
| headline analogue (full length) | 22.4% | 41.4% | 80.6% | 0.990 | 0.893 | **0.881** |
| semantic × sentence | 28.2% | 44.1% | 88.0% | 1.000 | 0.881 | 0.878 |
| random × token-window | 16.4% | 24.1% | 65.7% | 0.980 | 0.853 | 0.837 |
| coherence-sever × token-window | 17.5% | 29.0% | 76.0% | 0.988 | 0.856 | 0.848 |
| subject-verb × sentence | 15.8% | 19.6% | 62.9% | 0.972 | 0.845 | 0.822 |
| subject-verb × clause | 13.1% | 16.5% | 56.6% | 0.972 | 0.831 | 0.813 |

**Verdict: HIGH (0.881, minimum 0.808) → KEEP.** Although the blocker exposes
only 13-28% of same-record pairs, the clusterer recovers membership almost
perfectly from them (F1_L 0.97-1.00; no evidence-free merges, no bridge rounds
in 150 pools), and rank aggregation recovers most of the order (q 0.83-0.89).
The architecture is not blocker-limited, so a real hierarchical score measures
its PAIR CLASSIFIER against the defence. It is still not called stronger: its
real accuracy is Sonnet's pair judgement on candidates of which only 35% share a
record (the k = 5 live sample: linkage precision 0.49).

Unique value against one-shot J: one-shot is projected to exhaust 128k on ~2.5
headline and ~10.7 grid pools (mostly subject-verb × clause). The hierarchical
path has no per-call ceiling and completes a 330+-fragment pool for ~$5.0-5.3
of credit at k = 20.

Recommended, PENDING the user's decision: the 12 hierarchical headline pools
become (a) every headline pool where one-shot J exhausts 128k, then (b) the
first pools of the frozen D8 order up to 12. Selection is by completion (a
resource bound), never by score; it is fixed before any headline result.

## D11 — 2026-09-13: hierarchical retargeted, $210 wall, identifier J added

**Hierarchical: KEEP, retargeted, frozen before any headline result**
(data/pools/hier_headline_12.json, rule_D11). It runs on (a) every headline pool
where one-shot J exhausts the 128k ceiling (a non-completion, D6), then (b) the
first pools of the frozen, score-independent D8 order not already in (a), up to
12. Two analyses, **never combined**:
1. **RBNC rescue** — hierarchical completion and reconstruction on (a), the
   pools where one-shot exhausted its resource budget.
2. **Paired attacker comparison** — only the filler pools (b), where both
   attackers have scores.
The 12 are failure-enriched: they are never averaged into a headline mean and
never described as representative of the headline pools. The oracle ceiling
(D10) is described only as evidence that the frozen candidate graph and
downstream architecture have a high attainable ceiling; no remaining real-model
error is attributed solely to Sonnet. The attacker is labelled
decomposed / scalable, not stronger, unless the results support it.

**Spend priority:** headline J → grid J → identifier J → headline O → grid O →
hierarchical. Grid O is ahead of hierarchical. Dropped from the bottom:
hierarchical filler pools (from the end of the fill order), then rescue pools,
then grid O, then headline O, then grid J pools from the end; headline J and
identifier J are not dropped.

**Budget: $210 out of pocket** → ledger HARD_LIMIT $210 / 1.0625 = **$197.64**
credit. The user approved Plan A under this wall with the interpretation above,
**but nothing is submitted until the revised price including identifier J is
approved.**

**Identifier Game J (a small fixed secondary experiment).**
- *Existing evidence is exploratory / control only, never merged into the final
  estimates.* LLM runs (week 2/3; Llama-3.3-70B on Groq, temperature 0,
  `item_N` masking) on the 50-record set: game O per record (4 fragments), mean
  τ +0.213 (sd 0.30, n = 50); game L as one 50-way grouping, F1 0.0133 against a
  random floor of 0.0151 and a one-bucket baseline of 0.0297. Free floors at 500
  records, 500-way (D1 pipeline): O τ ≈ 0; L F1 0.0015 (random), 0.0027
  (Jaccard). None is game J, none uses pools of 7, Sonnet, or the current
  masking and gates.
- *Design:* N = 7 records per pool, 28 fragments (one per field), one-shot
  Sonnet, the current J scorer, masking and presentation, the analytic and random
  baselines, and the free Memon-inspired joint baseline. No hierarchical unless
  the J result gives a reason.
- *The ordering half is a template.* The answer key's order is the generator's
  fixed field order (name, ssn, account, address), and each field's type is
  obvious from its format, so order can be recovered with no linkage evidence.
  J is therefore reported against **two** baselines: the analytic T/(P+T) = 0.10
  and a **schema-order** one bucket sorted by field type, 2T/(P+T) = 0.20.
  Advantage over the schema-order baseline and the linkage component are the
  primary identifier quantities; q is reported as a template diagnostic.
- *Pools, frozen by a score-independent rule* (datagen/build_identifier_j.py,
  data/pools/identifier_J_pools.json): records r_0050..r_0499 — the 450 no model
  has seen; the first 50 are excluded for that exposure, not their results —
  ordered by sha256('identifier-J|' + record_id), pools of 7, primary = first 20.
- *Claim, narrow:* on the tested identifier corpus, fragmentation substantially
  limits joint source-linkage and ordering reconstruction under the evaluated
  attackers. Not generalised to all identifiers or all fragmentation schemes.
- **The schema-order baseline is attacker-visible and truth-free — verified**
  (analysis/identifier_schema_baseline.py, results/audit/identifier_schema_baseline.json).
  It reads only the prompt the model receives (its "label: text" lines),
  infers each field's type from its FORMAT alone (SSN `###-##-####`, account 10
  digits, address starting with a street number, otherwise name), and orders
  one bucket by the published field order. It uses the known fixed schema and
  observable format, never the answer key's field_type labels, record ids or
  fragment ids; its source is checked for all of them. The hidden labels are
  used only to check it: the format classifier is correct on 2,000 / 2,000
  fragments, and on all 20 frozen pools the baseline scores F1_J exactly 0.2000,
  equal to the analytic 2T/(P+T), with q = 1.000 — confirming that identifier q
  measures the template, not reconstruction.
- **The schema-order baseline, fully specified** (refined 2026-09-13 before any
  identifier-J result was scored; it depends only on the prompts, never on
  answers):
  1. *Input:* only the prompt's "label: text" lines.
  2. *Field type, frozen precedence:* SSN `^\d{3}-\d{2}-\d{4}$` → 10-digit account
     `^\d{10}$` → street-number address `^\d+\s+\S.*$` → otherwise name. The
     first full match wins; format only.
  3. *Order:* one bucket, types in the published order name → ssn → account →
     address. Within a type, ascending sha256("42|identifier-schema-baseline|" +
     text): a deterministic seeded tie-break independent of prompt position,
     alias labels and their order, record ids, fragment ids and ground truth.
     Same-type fragments never share a record, so within-type order cannot
     change the score.
  4. *Hidden truth* is used only to verify the classifier's accuracy (and to
     score the output with the J scorer); never to construct the output.
  Checks (results/audit/identifier_schema_baseline.json): the output's text
  sequence is unchanged after shuffling the prompt lines and relabelling every
  alias, and deterministic on repeat, on all 20 pools; no pool contains an
  exact-duplicate text, so the hash is never itself tied.
- **The identifier claim rule, frozen before running.** If and only if the full
  90% confidence interval for the mean advantage over the schema-order baseline
  lies within ±0.10, joint reconstruction is described as near the schema-order
  baseline. Linkage F1 is reported as the main mechanism; q only as a
  template-order diagnostic. The sample is fixed at the 20 primary pools and is
  not extended on the basis of the result.
- **Approved by the user (2026-09-13):** the revised plan at $188.47 out of
  pocket expected, the 20-pool identifier-J design, the ±0.10 margin, and an
  **$182 credit tripwire** under the $197.64 hard wall. Steps 1-3 (headline J,
  grid J, identifier J) are released once the baseline check passes (it did).
  Headline O, grid O and the hierarchical attacker are released only after a
  re-forecast once grid J's actual cost is known.

## D12 — 2026-09-13: headline unlock (first request touching the 46 headline pools)

D2 kept the 46 headline pools untouched. With the user's approval (D11), steps
1-3 are submitted by runs/final_run_steps123.py: headline J
(runs/final_headlineJ.json, 46 requests, spec hash in
runs/final_headlineJ_manifest.json), grid J pools 2-25 (runs/final_gridJ_w1..w4.json)
and identifier J (runs/final_identifierJ.json). The headline guard stays on for
every other spec. The identifier schema-order baseline's full specification
(D11: frozen precedence, text-hash tie-break, truth used only to verify) was
committed after submission but before any identifier-J result was scored; it
reads only the prompts, so no answer could have shaped it. The hierarchical headline pools are chosen afterwards by the
frozen D11 rule; nothing about the headline is decided from its results.

### Credit exhaustion and resends first — 2026-09-13

- The prepaid balance ran out while steps 1-3 were processing. 48 requests (6
  headline, 42 grid) were refused by the provider BEFORE inference ("credit
  balance is too low"): zero token usage, no answer, not charged. They are
  listed from the provider's own result records, with provider request IDs and
  prompt hashes, in runs/resend_manifest_2026-09-13.json (built by
  runs/build_resend_manifest.py). The driver refuses any resend that differs
  from the manifest, request for request and hash for hash.
- Each gets the protocol's one unchanged operational retry (D6: transient).
- **Order (user, 2026-09-13):** every resend completes before any repair
  request is sent (runs/final_run_steps123.py, commit 766bfca). Missing
  experimental units take priority over repairs, so a credit shortfall can only
  cost repairs.
- The repair round is the frozen structural rule only (harness/repair.py
  validate, applied by batch_game.build_repair_spec): an answer is repaired if
  and only if it is unparseable or its labels are missing, duplicated or not in
  the input. The decision reads no score, no truth and no reconstruction
  quality. The 28 answers that qualified before the resends were listed for the
  user, with reason and projected cost, before anything was submitted.

### Instruction-collision concern — checked and cleared, 2026-09-13

- **Concern.** That a fragment contained instruction-like text ("do not try
  again") that could have affected an attack.
- **Source.** The wording ("never retried") is run bookkeeping only: the
  reason field of the non-retry entry for random × token-window pool_002 in
  runs/resend_manifest_2026-09-13.json, written by
  runs/build_resend_manifest.py. It was never present in any prompt and no
  model saw it. Prompts are built from the frozen specs, never from the manifest.
- **Checks.** All 62,527 fragment lines in the frozen final specs contain no
  instruction-like text. Pool_002's 322 fragment lines are medical prose (two
  matched a naive search for "never" only through "Nevertheless"). The model's
  stored answer for pool_002 contains no reference to retrying, instructions or
  ignoring anything. The only "try again" text in the repository is the
  harness's own rate-limit error message in the 2026-09-10 O-probe failure
  records and a rehearsal log, which was never part of a prompt.
- **Decision (user).** There was no instruction collision. The post-hoc
  diagnostic rerun is NOT run, and no instruction-collision limitation is
  reported.

### random × token-window, pool_002 — the D6 treatment, kept exactly

- A pool-level, one-shot resource-bounded non-completion (RBNC): grid J, batch
  msgbatch_01VT6Tb1TfoYtECs8s9134ZA, 322 fragments, 12,057 input tokens,
  stop_reason max_tokens at 128,000 output tokens. It exhausted the 128k output
  (inference) budget before producing a complete reconstruction: the stored
  visible answer is 3,050 characters of JSON cut off mid-list after 250 of the
  322 labels, and the rest of the budget went to reasoning (D6).
- No individual fragment is known to have caused the failure.
- It is not retried. The partial output is not scored. It is not treated as
  F1 = 0.
- Pool_002's valid results in the other grid cells stand; the pool is missing
  only from the cell where it did not complete.

### Reporting rules for non-completions — frozen 2026-09-13, before any step 1-3 result was scored

- Every result shows, separately: (1) reconstruction scores on completed pools,
  and (2) completion and RBNC rates. The two are never merged into one number.
- A paired comparison involving a cell uses only the pools where BOTH compared
  conditions completed. An RBNC in one cell never removes that pool from
  comparisons between other cells.
- Paper wording: the 128k cap is a prespecified attacker resource budget, not
  a fundamental limit of modern AI. Larger inference budgets or future models
  could reduce RBNCs. The hierarchical attacker (D11) tests whether
  decomposition can complete pools the one-shot attacker cannot.

### Free attackers on the final pools — frozen 2026-09-13, before any final pool is attacked

- They run on exactly the frozen final J pools: the 46 headline pools, grid
  pools 2-25 in all 9 cells, and the 20 identifier pools. Each comes from the
  same spec, fragment files and truth that the one-shot model's answers are
  scored against, and goes through the same scorer (joint_game.score_row).
  Runner: runs/final_free_attackers.py. No API calls.
- **Memon-inspired joint attacker (audit packet C4): n = d = 2**, the committed
  default in adversaries/memon_joint.py, frozen here. Development evidence
  (commit 8ca7b69, pilot cell only): once the ID leak was fixed, ordering sat at
  chance for every n from 2 to 8, so the choice cannot favour the attacker. The
  fragments go in shuffled by the same per-unit seed that orders the model's
  prompt, with per-unit seeded aliases, never in file order (D1).
- The analytic baseline is reported per pool by the scorer. The identifier
  schema-order baseline is as frozen in D11
  (results/audit/identifier_schema_baseline.json).
- Random, Jaccard-Greedy and Jaccard-MST are game-O / L floors (audit packet
  C3), not J attackers. They run on the game-O documents, the same ones the
  model gets, once the O specs are frozen.
  *Clarification, 2026-09-13 (docs/adversaries.md):* in the final analysis
  they are game-O floors only. "L" here referred to the shared TF-IDF grouper,
  which is not a Jaccard attack. No game J version of them is built.
- Only per-pool rows and descriptive summaries are produced for now.
  Confidence intervals, the advantage definition used in the paper and paired
  tests wait for the frozen results plan.

### Steps 4-5 released: headline O and grid O — 2026-09-13

- The user released headline O and grid O after steps 1-3 were scored.
  Whether the hierarchical attacker runs is decided after these are scored;
  nothing about it is released. The headline unlock above extends to headline
  O's 100 documents.
- The specs are built by runs/build_final_O_specs.py, which uses the exact
  sample rules that priced the plan (analysis/budget_final.py). It reads
  document ids and fragment counts only:
  - **Headline O:** 100 of the 322 headline documents, proportional to the
    length bands, largest remainder, seeded within bands. Band split: 1-15
    fragments 9, 16-30 47, 31-60 37, 61-100 6, 101+ 1. Full-length reference
    cut (data/prose).
  - **Grid O:** the first 30 documents of the seeded order of the 168 pool
    2-25 documents, the same 30 in all 9 cells. Submitted as 3 waves of 10
    documents × 9 cells (90 requests each), because the ledger holds each
    submission's worst case (every request at 128k) against the hard limit. A
    wave that stops leaves every cell equally covered.
- The protocol is the same as steps 1-3 (runs/final_run_steps45.py): one
  attempt at 128k, one resend of transport holes, every resend before the one
  structural repair round, non-completions under D6, and the same scorer.
- **Forecast:** $15.34 expected from the specs' own pricing. The plan's figure,
  including repair overhead, is $19.88 expected and $26.54 at P95.

## D13 — 2026-09-13: results plan committed; uncertainty method; schema advantage

- **docs/results_plan.md is committed unchanged** as the authority for the
  analysis. Disclosure: it was committed after the descriptive point results
  of steps 1-5 had been seen (the per-cell REPORT.txt means and the
  Memon-inspired descriptive table). No confidence interval, bootstrap, paired
  test or correlation had yet been computed.
- **Uncertainty (user, 2026-09-13), fixed before any interval or test was
  computed:**
  - A percentile bootstrap over the independent units (results plan §2):
    pools for game J, documents for game O. 10,000 resamples, seed 42.
  - Paired comparisons resample a unit ID once and carry both conditions'
    scores together, bootstrapping the per-unit difference. Conditions are
    never resampled independently and then subtracted.
  - Spearman ρ is bootstrapped over the unit rows. When the same pool (or
    document) appears in several grid cells, a correlation pooled across
    cells resamples the pool (or document) ID and carries all of its rows,
    because §2 makes the pool the independent unit.
  - 95% CIs in general; 90% for the frozen identifier near-baseline rule.
    The t-interval is a sensitivity check, never a replacement.
  - The plan specifies no multiplicity adjustment. Intervals are reported
    unadjusted and labelled as such.
- **Schema-aware advantage, clarified:** A_schema = (F1_J − 0.20) / (1 − 0.20),
  the plan's normalized advantage with b = 0.20. The raw difference
  F1_J − 0.20 is reported alongside it for interpretability. This was
  clarified after the descriptive means were visible and before any interval
  or test was computed. In the current data the near-baseline verdict does
  not depend on the choice: one-shot Sonnet's normalized (−0.146) and raw
  (−0.117) point estimates both already lie outside ±0.10. The primary
  criterion is unchanged: the entire 90% CI on the normalized A_schema must
  lie inside [−0.10, +0.10]. Nonsignificance is never read as equivalence.
- **The identifier random baseline (D11) is included:** a local random
  attacker that shuffles the pool's fragments, deals them round-robin into
  the known 7 groups (the week-1 random_linkage_guess convention) and keeps
  the shuffled order within each group. Its per-pool value is the mean over
  10,000 seeded draws.
- **Figure 9 becomes a completion / RBNC table.** The whole study has one
  one-shot non-completion, and the plan draws the figure only if RBNCs are
  numerous enough to matter.
- **The hierarchical 12-pool run stays pending.** It is not launched as part
  of the analysis.
- **SHA-256 seed fix (commit 0621396), made before any analysis used the
  Memon-inspired results.** `order_from_sim.order_cluster` seeded its third
  search start with Python's `hash()` of the component ids, and that changes
  per process. It now uses SHA-256. The effect on the Memon-inspired attacker
  (results/audit/memon_sha256_reproducibility.md): 9 of 282 final pools
  changed in F1_J and q. F1_L is unchanged in all 282, because only ordering
  uses the search. The maximum absolute score difference is 0.023, and no
  condition's mean F1_J moved by more than 0.0003. The post-fix run is
  canonical (results/final_free); the pre-fix run is kept in
  results/audit/memon_joint_pre_sha256. Two post-fix runs under PYTHONHASHSEED
  0 and 987 are identical in all 282 pools, reconstructions included.
- The hierarchical attacker shares `order_cluster`, so it inherits only the
  SHA-256 behaviour. G2c, G5a, G5b and the hierarchical tests pass after the
  fix. The oracle-ceiling diagnostic was rerun after the fix
  (results/audit/hier_oracle_ceiling_post_sha256.json): 244 of 2,178 stored
  values moved, by at most 0.021. The headline-analogue median oracle F1_J
  moved 0.881 → 0.883, and the D10 verdict (HIGH → KEEP) is unchanged. The
  frozen D10 record stays as results/audit/hier_oracle_ceiling.json.

## D14 — 2026-09-13: post-hoc exploratory embedding adversary, design frozen (not run)

- **Status.** The user approved the design with eight corrections, all applied
  in docs/embedding_adversary_design.md, which is the frozen design. It is
  labelled POST-HOC EXPLORATORY EMBEDDING ADVERSARY: it was designed after the
  final one-shot and Memon-inspired results were visible, and it is never
  merged into the prespecified attacker comparisons. **Nothing is downloaded
  or installed until the user explicitly approves the download.**
- **Model: `sentence-transformers/all-mpnet-base-v2` only**, a widely used
  general-purpose Sentence Transformers model. The Hugging Face revision is
  pinned to `e8c3b32edf5434bc2275fc9bab85f82640a19130`. Only the files it
  needs are downloaded (the ONNX / OpenVINO / `pytorch_model.bin` files are
  not):
  - `model.safetensors`: 437,971,872 bytes, SHA-256
    `78c0197b6159d92658e319bc1d72e4c73a9a03dd03815e70e555c5ef05615658`.
  - Git blob ids: `tokenizer.json` 7c8e1940…b2b3, `vocab.txt` 1c51ab79…be4d,
    `config.json` b9fd4298…fc88, `modules.json` 952a9b81…6c5e43,
    `1_Pooling/config.json` 4e09f293…e2666, `sentence_bert_config.json`
    4eb670bb…198e, `config_sentence_transformers.json` fd1b2911…acdf,
    `special_tokens_map.json` 378d4fa3…4d14d, `tokenizer_config.json`
    20ae1276…2c1d. The full ids are in the design and verified after download.
  - 438.7 MB in total.
- **Biomedical embeddings are not in this run.** They are a possible future
  sensitivity analysis only, not a second model to select between.
- **Comparison.** The embedding representation is the only architectural
  change relative to Memon-inspired. **F1_L is the primary comparison.** F1_J
  differences are not attributed solely to linkage, because changed clusters
  can change q indirectly; F1_J and q are secondary. q is measured, not
  assumed: the inherited ordering module was near chance in the existing
  Memon-inspired results, but it is not presumed to stay there.
- **Identifiers.** That embeddings cluster by field type is a hypothesis, not
  an expected success outcome.
- **Contamination.** Per its model card, the model was trained on more than
  1 billion sentence pairs from existing datasets (for example S2ORC). Those
  datasets predate the evaluated corpus of post-cutoff PMC case reports, which
  reduces the concern about direct document memorization. This is not a claim
  that contamination is absent.
- **Parameters.** Every one is fixed by a standard default or inherited from
  frozen code: mean pooling, 384 word-piece limit, L2 / cosine, average
  linkage cut to exactly N, jitter 1e-6 with seed 42, ordering n = d = 2, the
  SHA-256-seeded order_cluster, batch 64, CPU. None is tuned; nothing needs
  calibration.
- **The development smoke test is score-blind.** It runs only on grid pool 1
  (screening) in the nine cells and identifier records r_0000–r_0049. It
  computes and prints no reconstruction score. It checks pipeline execution,
  actual word-piece lengths and truncation, embedding reproducibility,
  batch-size numerical stability (1 / 16 / 64 / 128), clustering and scorer
  compatibility (validity only), and determinism across processes. It also
  benchmarks CPU throughput, and the measured projection for the 62,527 final
  fragments replaces any estimate before the final run. Development results
  never select a parameter.
- **Packages to install (pending approval)** into the project `.venv`
  (Python 3.11.9): `sentence-transformers==6.0.1` and `torch==2.14.0` (the
  PyPI Windows CPU wheel). pip resolves `transformers`, `tokenizers`,
  `huggingface-hub`, `safetensors`, `scikit-learn` and their small
  dependencies; the resolved versions are recorded in a D14 addendum after
  installation.

### D14 addendum — 2026-09-13: install, one correctness fix, score-blind smoke test

- **Download approved by the user and done.** Resolved versions
  (results/audit/embedding_env_freeze.txt): sentence-transformers 6.0.1,
  torch 2.14.0+cpu, transformers 5.17.0, tokenizers 0.23.2, huggingface-hub
  1.31.0, safetensors 0.8.0, scikit-learn 1.9.1, plus small dependencies. The
  model snapshot at revision e8c3b32e… matches every D14 pin (SHA-256 for
  model.safetensors, git blob ids for the rest). Only the 10 needed files were
  fetched.
- **Correctness fix (not tuning).** Cosine similarity of normalised float
  embeddings can exceed 1 by rounding, which made 1 − sim slightly negative,
  and scipy refused the linkage on the first development pool. The distance
  is now clamped at 0 (`embedding_joint.cut_exact_n`). Cosine distance is
  non-negative by definition, and the clamp is a no-op for TF-IDF similarity
  (check 7 below).
- **Score-blind smoke test PASSED** (results/audit/embedding_smoke.json). It
  ran on 16 development units (grid pool 1 in 9 cells; identifier records
  r_0000–r_0048 in 7 pools of 7), 1,890 fragments. No reconstruction score was
  computed.
  - The model files match the pins.
  - The pipeline runs, and every output is a valid partition with exactly N
    groups.
  - Word pieces: max 203, 99th percentile 99, 0 of 1,890 over the 384 limit.
  - Embeddings are bit-identical on repeat.
  - Batch sizes 1 / 16 / 128 differ from 64 by at most 5.3e-7 and give
    identical reconstructions.
  - Reconstructions are identical across processes (PYTHONHASHSEED 0 vs 1).
  - The grouper reproduces `memon_joint.group_known_n` exactly when given
    TF-IDF similarity (0 mismatches).
- **Measured throughput** (CPU, 4 torch threads): 22.5 fragments/s to embed;
  0.068 s per fragment for the whole attack. **Projection for the 62,527
  final fragments: about 46 min of embedding and about 71 min for the full
  attack in one process.** That is a lower bound for the largest pools,
  because the ordering cost grows faster than linearly. This replaces the
  earlier 5–15 minute estimate. No development score was computed, so none
  could select a parameter.

### D14 addendum 2 — 2026-09-13: final run released; how it is reported (user)

- **The user released the frozen all-mpnet-base-v2 run on all 282 final J
  pools** (runs/final_embedding_attacker.py, committed before it runs; the
  model is loaded offline from the pinned snapshot).
- **It appears in the main results.** The embedding attacker is a real
  evaluated attacker. It is shown in the relevant attacker tables and figures
  (the headline, grid and identifier J tables; Figures 1, 2, 3 and 5; the
  paired attacker comparisons) alongside the statistical and LLM attackers,
  each time marked **POST-HOC EXPLORATORY**. It is never presented as a
  prespecified or confirmatory attacker.
- **Required disclosure wording.** It was motivated by the observed gap between
  Memon-inspired and one-shot Sonnet. It was then fully designed and frozen
  before its own evaluation, with no final-data tuning and no model selection
  from its scores.
- **Its first complete result is kept, whatever it shows.** No additional
  embedding model and no pipeline tuning is run on the basis of the result
  unless it is separately labelled as a further analysis.
- **Metrics.** F1_L is its primary comparison; F1_J and q are secondary
  components.

### D14 addendum 3 — 2026-09-14: the first complete result (kept as is)

- All 282 final J pools completed (results/final_embedding/, REPORT.txt),
  offline from the pinned snapshot, deterministic on re-run. It took 5,419
  attack-seconds, about 90 minutes in one process.
- One fragment of 62,527 (in coherence-sever / clause) reached 386 word
  pieces against the model's 384 limit, so its last 2 word pieces were
  truncated by the model default, as the design anticipated. It is kept as run
  and not rerun or altered.
- Descriptive means (pool-level CIs and paired comparisons are in the
  analysis package):
  - F1_L: headline 0.364; grid 0.246–0.315; identifier 0.110.
  - F1_J: headline 0.182; grid 0.124–0.158; identifier 0.054.
  - q_micro: 0.49–0.52 in every condition.
- No further embedding model or tuning is run on the basis of this result.

## D15 — 2026-09-14: POST-HOC EXPLORATORY — CONTROLLED EXCERPT GRANULARITY EXPERIMENT (design only)

- **Why fixed excerpts.** The naturally-short-document search was stopped by
  the user. No corpus document is short enough (minimum 99 words; 0 of 500 at
  71 words or fewer), and the same PMC pipeline structurally does not produce
  narratives that short. The user chose the controlled fixed-excerpt design.
- **Goal.** Measure the effect of fragmentation granularity with the source
  text held constant: the same clinical excerpt under the sentence cut and the
  single-token cut. It stays separate from the prespecified grid, and it is
  exploratory throughout.
- **Selection (frozen once built).** 70 documents, 10 pools × 7: the 500
  corpus documents ordered by sha256('xgran-select-v1|' + record_id), taking
  the first 70 and dealing them into pools of 7 in that order. Nothing about
  difficulty, attacker score, prior outcome, topic or length enters. The only
  requirement, a whole-sentence run of 40 or more words, is met by every
  document.
- **Excerpt.** Each document's reference sentence cut (data/prose) supplies
  the sentences. The start sentence is sha256('xgran-start-v1|' + record_id)
  modulo the valid starts, meaning those from which the document still reaches
  40 words. Whole sentences are taken until the running count reaches 40 words;
  the sentence that crosses 40 is kept whole, and no sentence is ever cut.
  Actual word and sentence counts are recorded. No excerpt is chosen or
  inspected for content.
- **Conditions, from the identical excerpt text.** (1) Sentence: one fragment
  per sentence. (2) Single-token: one fragment per whitespace-delimited token,
  verbatim, with case and punctuation untouched. The builder asserts that both
  cuts reproduce the same excerpt.
- **Attackers.** Frozen one-shot Sonnet game J, Memon-inspired J and the
  frozen MPNet embedding J, on both conditions, with every existing Sonnet
  setting, masking, per-unit shuffle, scorer, repair policy and the 128k RBNC
  rule unchanged, and no prompt adaptation. **The primary comparison is the
  paired within-pool Sonnet difference, sentence vs single-token.** Reported:
  F1_J, F1_L, q, completion / RBNC, fragment count, tokens and cost. The same
  10 pools appear in both conditions; no pool is kept or dropped on its
  scores; an RBNC stays an RBNC.
- **Game O is not included.** It is priced separately only if the user asks,
  after seeing the J price.
- **Status.** Built by datagen/build_excerpt_granularity.py
  (data/pools/excerpt_granularity_pools.json, results/excerpt_granularity/,
  runs/xgran_J.json marked NOT_SUBMITTED). The price / resource report is in
  results/excerpt_granularity/DESIGN_REPORT.md. **Nothing is submitted until
  the user approves that report.**

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
