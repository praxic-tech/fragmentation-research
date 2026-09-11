# Audit packet — the final run (frame A, decisions D1–D6)

2026-09-11. Everything below was checked against code and data, not restated
from docstrings. **No API calls were made for this audit.** Headline-cut checks
read fragment files for fidelity only; nothing was scored or sent (D2).

**Status as of D7/D8.** The audit found four problems; all four are fixed and
re-verified (section H). Each finding below keeps its original evidence, marked
**RESOLVED (D7)** with what changed, so the history stays auditable.

Evidence sources: grid cells `results/grid_A/*`, grid corpus
`data/grid_corpus_A/prose_raw.jsonl`, headline cut `data/prose/`, pool-1
screening answers `results/batches/grid-A-pool1*`, the preserved audit copy
`results/audit/pool1_screening/`, and `analysis/verify_fragments.py`.

---

## 0. Verdict

| component | does what it claims? | holds up? | status |
|---|---|---|---|
| random (sentence, clause, token-window) | **yes** | yes | — |
| semantic × sentence (reference) | yes — it is sentence splitting | yes, named honestly (D5) | — |
| semantic × clause | yes | yes | — |
| coherence-sever × clause | yes, after D7 — cuts 72.3% of boundaries (was 95%) | yes | **RESOLVED (D7)**, re-cut |
| coherence-sever × token-window | yes, after D7 — same word ruler as the other two | yes | **RESOLVED (D7)**, re-cut |
| subject-verb (sentence, clause) | **yes** | yes | **RESOLVED (D7)**, whitespace-legal cuts, re-cut |
| grid corpus cap | yes | yes | — |
| headline cut | yes, drops 0.12% of tokens by design | yes, document it | — |
| masking / presentation | yes, after D7 — per-unit seeds | yes | **RESOLVED (D7)** |
| masking side-channel diagnostic (G3) | yes — planted leak exploited (F1 ≈ 1.0), masked shows no side channel | yes | **done (D8)**, see B and H |
| one-shot Sonnet J / O | yes | yes | — |
| hierarchical attacker (batch) | yes — equals the offline attacker (G2c); live sample completed | yes, as a decomposed attacker | **RESOLVED (D7)**; k fixed by blocker calibration (D8) |
| Random / Jaccard-Greedy / Jaccard-MST | yes, at chance after D1 | yes, as floors | — |
| Memon-inspired joint | yes (tested) | yes | run on frame A (free) |
| scoring, integrity gate, RBNC, parser | yes | yes | — |
| ledger / answer store / resubmission | yes | yes | tax-adjust the wall |

---

## A. Cutters

Every grid cell cuts the same frozen, hashed source
(`data/grid_corpus_A/prose_raw.jsonl`, 175 documents from the 25 development
pools, each truncated to the first N sentences so the reference cell yields at
most 30 fragments). Granularity is the independent variable, so the cap is on
the SOURCE, never on each cutter's output (build_grid_corpus.py explains why a
per-cutter cap would have pinned 64% of clause and 82% of token-window
documents at exactly 30). One document, prose_0305, needed an iterative
adjustment (29 of 79 sentences kept) and is recorded in the manifest.

### A1. Fidelity — re-run for this audit

`python analysis/verify_fragments.py --raw data/grid_corpus_A/prose_raw.jsonl --cell results/grid_A/*/`

| cell | invented tokens | dropped | rejoins exactly |
|---|---|---|---|
| coherence-sever × {sentence, clause, token-window} | 0 | 0 | 175/175 each |
| random × {sentence, clause, token-window} | 0 | 0 | 175/175 each |
| semantic × {sentence, clause, token-window} | 0 | 0 | 175/175 each |
| subject-verb × clause | 0 | 0 | **172/175** |
| subject-verb × sentence | 0 | 0 | **174/175** |

Subject-verb's four failures are the same class of bug that was fixed in
coherence-sever: the cut falls on a spaCy token boundary that is not whitespace
in the source, and the rejoin inserts a space.

```
source: 'for the patient’s severe AKI.'      rejoin: 'for the patient ’s severe AKI.'
source: 'Quadra Assura MP™ CRT-D (Abbott'    rejoin: 'Quadra Assura MP ™ CRT-D (Abbott'
```

No word is invented or lost, so the verifier passes the cells, but a fragment
boundary exists that is not a real boundary in the text.

**RESOLVED (D7).** subject_verb._cut_unit now cuts only where the source has
whitespace; both cells were re-cut (7,115 and 8,418 fragments) and rejoin their
source exactly, 175/175. The re-cut coherence-sever cells also rejoin exactly.
Every grid cell now passes exact reconstruction.

### A2. random

**Claim.** Structure-blind cuts at whitespace word boundaries; fragment count
per document matched to the reference count at the same granularity, so a score
difference is strategy, not count. Seeded per document from sha256(record_id).

**Verified.**
- Fragment count equals semantic's on **175/175** documents at every granularity.
- Cuts that end a sentence: **5.5%** (sentence), 5.5% (clause), 5.2% (token-window),
  against a **5.1%** chance that any word boundary ends a sentence. Structure-blind, as claimed.
- Fidelity 175/175 in all three cells.

**Holds up.** It is the control strategy and behaves as one.

### A3. semantic

**Claim.** Cut at every boundary of the granularity's unit (sentence, clause, or
fixed 12-word window).

**Verified.**
- Sentence cuts end a sentence **99.3%** of the time; clause cuts 78.3% (the rest
  are clause-internal, by design); token-window 5.3% (structure-blind, by design).
- semantic × sentence **is ordinary sentence-boundary splitting** (D5): it is the
  reference condition, not evidence for a distinct "semantic" cutter.
- Grid reference vs the headline cut: on **165/175** grid documents the fragments
  equal the first k fragments of `data/prose/prose_fragments.jsonl`. The other 10
  differ because the rebuilt grid text joins bullet lists and paragraph breaks with
  single spaces, and spaCy then merges two sentences (e.g. prose_0431
  "as follows: • Complete blood count…"). Same splitter, different whitespace.
  Worth one methods sentence; not a validity problem.

**Holds up.**

### A4. coherence-sever — did not do what it said; RESOLVED (D7)

**Claim.** Take the granularity's units as candidate boundaries and cut only
where a discourse link sits (a connective, a pronoun needing an antecedent, or a
topic shift), merging everything else. Token-window: 12-token windows with edges
snapped to a nearby discourse token.

**Verified — sentence and clause.**

| granularity | candidate boundaries | cut | via topic shift | via pronoun | via connective | merged |
|---|---|---|---|---|---|---|
| sentence | 4,092 | **95.1%** | 82.2% | 9.9% | 2.9% | 4.9% |
| clause | 5,188 | **95.3%** | 83.9% | 9.1% | 2.3% | 4.7% |

The topic-shift rule (content-word Jaccard < 0.12 between adjacent units) fires
at over four of every five boundaries. Consecutive sentences in clinical case
reports share little vocabulary, so nearly every boundary reads as a "topic
shift". The module's own CALIBRATION WARNING predicted exactly this and was never
resolved. **coherence-sever × clause is semantic × clause with about 5% of
boundaries merged.** Pool 1 agrees: J advantage +0.678 against semantic ×
clause's +0.670, and on two documents the prompts were byte-identical.

**Verified — token-window.** Its windows count **spaCy tokens** (12.07 per
fragment), while random and semantic token-window count **whitespace words**.
spaCy counts punctuation as tokens, so:

| cell | fragments | words / fragment |
|---|---|---|
| random × token-window | 6,987 | 11.86 |
| semantic × token-window | 6,987 | 11.86 |
| coherence-sever × token-window | **8,448** | **9.81** |

Its fragments are 17% shorter and 21% more numerous. Its pool-1 J advantage
(+0.405 vs random × token-window's +0.614) is therefore confounded with a finer
granularity. The snapping behaviour is real, but this cell is not measured on the
same ruler as the other two token-window cells.

**RESOLVED (D7) — fixed and re-cut, the user's choice.**
- Topic shift is now "the adjacent units share no content word". It has no
  threshold, and was chosen from the text's overlap distribution alone (57-69%
  of adjacent units share no content word; median overlap 0), never from scores.
  × clause re-cut: **72.3%** of clause boundaries cut (was 95.3%), 3,926
  fragments (was 5,119). It is now a distinct, selective strategy.
- Token-window counts whitespace words. × token-window re-cut: 6,977 fragments,
  **11.88** words per fragment against 11.86 for random / semantic: the same
  ruler, so the granularity confound is gone.
- Both rejoin their source exactly. Pool 1's coherence-sever numbers describe the
  OLD cells (archived in results/grid_A/_superseded_2026-09-11/); the new cells
  were not screened, and D5's decision to keep them stands on design grounds.

### A5. subject-verb

**Claim.** Within each sentence or clause, find the first `nsubj`, cut right
before its governing head (the verb): subject phrase | verb onward. Units with no
match are emitted whole, never faked.

**Verified.**

| granularity | units | fired | head is VERB/AUX | head is the main-clause root | auxiliary left on subject side |
|---|---|---|---|---|---|
| sentence | 4,267 | **66.7%** | 99.1% | 86.4% | 5.1% |
| clause | 5,363 | **57.0%** | 99.1% | 89.6% | 5.7% |

The cut lands immediately before the subject's governing verb in 99% of fires.
Fire rates are below the docstring's figures (72% / 65%, measured on 40 other
documents); a third of sentences and 43% of clauses have no active subject and
stay whole. Passives (`nsubjpass`) are excluded by the original spec, which
matters in case reports ("a biopsy was performed").

**Holds up.** The 4-cut fidelity defect in A1 is fixed (D7).

### A6. The headline cut

`data/prose/prose_fragments.jsonl` is semantic × sentence at full length
(docs/corpus_build.md). Fidelity: 0 invented tokens; **0.12%** of tokens (399 of
335,742, in 111 documents) dropped because units under MIN_SENT_CHARS are
discarded by the corpus build; 384/500 documents rejoin exactly, the rest differ
only by those dropped units (short headings and labels). The dropped text is
never shown to any attacker and never scored. **Holds up;** state it in methods.

---

## B. Masking and presentation

**Claim.** Fragment ids (`prose_0000_frag_000`, which encode document and
position) never reach a prompt. Labels are a shuffled permutation
`m_0000000…`, and the presentation order is shuffled, so neither label numbers
nor position carries order information. `preflight()` refuses any prompt still
carrying a raw id; `assert_ids_masked` guards the attackers.

**Verified.**
- No raw id reached any prompt: 88/88 pool-1 prompts preflighted, 0 blocked.
- **But the shuffle is not per-unit.** `present()` calls `mask_fragment_ids(…, seed=42)`
  and then `Random(42).shuffle` on the same length, so the permutation depends
  **only on the number of fragments**. All 23 sizes seen more than once had an
  identical pattern every time, and random and semantic cells at the same
  granularity (equal counts) received byte-identical presentation patterns.
- In every one of the 77 O prompts the shown order and the label-number order are
  **anti-correlated** with the true order: τ from −0.006 to −0.333, mean −0.137.
  Python's shuffle with a fixed seed produces near-identical patterns across sizes.

**Was it exploited?** No, as measured:
- O: the model's answers agree with the shown order no more than their accuracy
  implies (excess −0.018). It ignores presentation.
- J: same-record fragments are **not** clustered in the shown order (adjacency
  z-scores −1.4 to +1.7 over all 11 pools; same-record gap ratio 0.98–1.03),
  although `build_units` hands pools over grouped by record. Within-record shown
  order carries τ +0.046 (sd 0.168): negligible.

**RESOLVED (D7).** `joint_game.present` now seeds both shuffles per unit from
sha256 of the unit's fragment ids and texts, the run seed and the purpose, as
independent streams (`joint_game._unit_seed`), as D1 did for the classic
baselines. Rebuilt pool-1 prompts: τ(shown, true) mean **+0.015** (sd 0.150, 41
of 77 positive; was −0.137 and never positive); no document size repeats a
pattern (0 of 23). Every prompt changed, so pool-1 answers are not reused; pool 1
is screening data (D5).

**The masking side-channel diagnostic (G3) is run in D8**, on development pools
(never headline): the same pools asked twice, once with RAW fragment ids in true
order (a deliberately planted leak) and once masked. It is a diagnostic of the
side channel, not a requirement that masked reconstruction be low: the unmasked
arm shows what an exploitable id leak looks like, and the masked arm is checked
for signs of exploiting label numbers or presentation order beyond what its
accuracy implies. Pool-1 already showed a masked attacker can reconstruct well
from content alone; that is the finding, not a failure of masking.

---

## C. Adversaries

### C1. One-shot Sonnet, games J and O — the primary attacker

**Claim.** One prompt per unit; the model returns only labels (O: an ordered
list; J: 7 ordered lists); answers are validated, repaired once with
bookkeeping-only feedback, and scored by one shared scorer.

**Verified.**
- Prompts ask for "ONLY a JSON array … No explanation, no markdown" (J). O lacks
  the "no explanation" line, and 44 of 77 O answers wrapped the JSON in prose.
  Harmless to cost and parsing now (G1f); not worth a prompt change.
- Output is **≥ 96.7% hidden reasoning** on every J answer (visible answer ≤ ~2k
  tokens even at 272 fragments; billed output 31k–97k). D6 records why this is a
  genuine resource bound and why reasoning is not reduced for the primary attacker.
- Repair feedback names only missing / duplicated / invalid labels, never ground
  truth (G1: "no ground truth" test).
- Parser: the longest decodable JSON list wins, fenced first (G1f). Checked against
  all 175 stored texts: only the one mis-parsed answer changed.
- Pool 1: 88/88 answered after 2 resubmissions and 1 repair round; all six
  predeclared checks pass; re-scoring reproduces 22/22 files byte-identically.

**Holds up.**

### C2. Hierarchical attacker — not ready

**Claim.** Never puts a whole pool in one prompt. TF-IDF top-k candidates →
one query per unordered pair (P(same document), P(shown-first precedes)) with the
shown-first side randomised per pair → exact-N clustering on the membership
channel → rank aggregation on the precedence channel → the same partition-with-
order shape as one-shot J, scored by the same code.

**Verified.**
- Logic tested on mocks: test_hierarchical, test_hierarchical_resume (G2b), pair
  cache and resume, refusal above HOLE_CAP = 25% missing pair evidence.
- **It has never completed a pool on a live model.** The free-tier rehearsal
  (gpt-oss on Groq) stopped at pair batch 570 on provider quota and correctly
  refused to score.
- **Its output reservation will fail on Sonnet.** `pair_reservation` sizes each
  pair batch at 400 + 100 tokens per pair, fitted on gpt-oss. Sonnet's adaptive
  reasoning overran exactly this kind of cap on pool 1.
- No batch path: as written it runs at interactive list price (2× batch).
- Its Sonnet cost is unmeasured: priced under ×1 / ×2.3 / ×5 reasoning multipliers.

**RESOLVED (D7): ready as a decomposed attacker.** Every pair batch runs at the
128k ceiling with one attempt; the batch path (adversaries/hier_batch.py) equals
the offline attacker exactly (G2c); a live batch sample completed a
development pool for $0.50.

**New finding (D8): its blocker is lossy at every k.** On the 25 development
pools at full length, the TF-IDF top-k candidates connect 13% / 46% / 81% of
records and cover 22% / 31% / 41% of truly adjacent pairs at k = 5 / 10 / 20. A
pre-declared rule gave k = 20 with coverage reported inadequate. This attacker
therefore never sees most true neighbour pairs; it is reported as a decomposed,
scalable attacker and a one-shot-ceiling check, and is not called stronger
unless the results support it.

### C3. Classic statistical baselines — Random, Jaccard-Greedy, Jaccard-MST

**Claim.** Free, local floors. After D1: masked presentation, independent RNG
seeded per unit, deterministic truth-independent tie-breaking; renamed
"Jaccard-" because they are not Memon's PPM + tree-pruning method.

**Verified** (`results/harness_results.json`, D1 superseding run):

| baseline | prose O τ | prose L F1 |
|---|---|---|
| Random | −0.001 | 0.002 |
| Jaccard-Greedy | −0.021 | 0.055 |
| Jaccard-MST | −0.011 | 0.055 |

Before D1 the leaked versions scored τ +0.32 and +0.70 on prose; the rerun is
contained (only O moved). Memon/MST determinism was re-verified (MST's
set-iteration nondeterminism fixed by sorted iteration).

**Holds up** as floors. They are weak by design and should be described as floors,
not as competitive attackers.

### C4. Memon-inspired joint attacker

**Claim.** Group with B_stat (TF-IDF cosine + average linkage, `cut_tree` to
exactly N), order within groups with Memon's directional character n-gram
statistic, converted to a bounded antisymmetric weight with no free parameter
(W = tanh(Δ/2)). Masking happens inside `attack()`.

**Verified.** G5a passes; the earlier q = 1.0 raw-id leak (tie rule over raw ids)
was fixed by masking inside the attacker plus `assert_ids_masked`. Free and
deterministic. **Not yet run on frame A or the headline.**

**Holds up.** Run it on all 9 cells and the 46 headline pools (free) so attacker-
dependence is measured across the whole grid. Name it "Memon-inspired".

---

## D. Scoring and integrity

- Metrics: ordered-pair F1 (joint), linkage F1, q = C/K with F1_J = F1_L × q,
  analytic one-bucket baseline T/(P+T), per-pool advantage, O reconstruction
  detail (τ, pairs ok, exact, shift, longest run, run%). Identities tested (G0).
- Integrity gate refuses a game with a transport hole or a unit over POLICY_CAP
  (25% of fragments placed by the completion policy). Never scores around holes.
- D6: a call that exhausts 128k is a resource-bounded non-completion, recorded in
  `<game>.rbnc.jsonl`, never scored, never refused, never re-asked. Tested (G1e).
- Reports: per-cell integrity + O + J (with the F1 breakdown) + completion, then
  summary tables and a column legend (`REPORT.txt`).

**Holds up.**

---

## E. Run formatting

### E1. Units and what is sent

| game | unit | unit id | the model sees | the model returns |
|---|---|---|---|---|
| O | one document | its record id (`prose_0383`) | that document's fragments, masked and shuffled | one ordered label list |
| J | one pool of 7 documents | pool id (`pool_000`) | all fragments of all 7, mixed, masked, shuffled | 7 ordered label lists |

Every prompt: `present()` masks ids to `m_0000000…` labels and shuffles the
presentation (see B for the seeding fix), then `prompt_O` / `prompt_J` builds the
text, then `preflight()` refuses it if any raw id survives.

Request parameters: `model = claude-sonnet-5`, one user message,
`max_tokens = 128000` for every J and O request (D6), default sampling and default
adaptive reasoning. Temperature, top-p and effort are not set (the model rejects
sampling parameters; RUN_PLAN found effort "low" returns invalid output).

### E2. The spec (one JSON file per wave, `runs/*.json`)

```
{ "tag": "grid-A-pool1",
  "model": "claude-sonnet-5",
  "build": { docs, pool_size: 7, seed: 42, margin, arm: "masked", games,
             cells: [...], pools: [[pool_id, [record ids]]...], o_docs: [...],
             forbidden_docs: <headline guard count> },
  "requests": [ { cell, game, unit, prompt, max_tokens } ... ],
  "sidecar":  { <custom_id>: { custom_id, base_cid, round, cell, cell_dir, game,
                unit, n_records, n_fragments, max_tokens,
                alias_map,     # label -> fragment id: the only way back
                shown_order,   # what the model actually saw
                prompt, prompt_sha, unmasked_control, model,
                [cut_off_at]   # on a raised-cap resubmission only
              } },
  "expected_usd": <forecast at measured rates> }
```

`custom_id = <cell-slug>__<game>__<unit-slug>`, at most 64 characters,
`[A-Za-z0-9_-]`; a repair unit carries `-r<round>`. Results come back in
arbitrary order and the id is the only attribution, so it is validated at build.

### E3. Submission (`batch_submit.submit`)

1. Every prompt through preflight (a leak aborts the whole wave).
2. Estimate: input from prompt length; worst case = every request to its cap.
3. Ledger check: the **tripwire** sees 2 × the measured-rate forecast; the
   **hard limit** sees the worst case, so the wallet cannot be breached even in
   principle (a wave too big to be safe must be split).
4. Reserve in the ledger → `batches.create` → attach the batch id → write
   `results/batches/<tag>.state.json` before anything else.
5. Nothing is ever submitted without an explicit go.

### E4. Fetch (`batch_submit.fetch`)

Streams results into `results/batches/<tag>.results.jsonl`, one durable row per
answer, resumable after a crash:

```
{ custom_id, cell, game, unit, fetched_at, result_type,
  usage: {input_tokens, output_tokens}, stop_reason,
  text                      # a finished answer
  | error + detail          # ZeroAnswerError, TruncatedAnswerError, provider error
  [+ partial_text] }        # text of a cut-off answer, kept aside, never scored
```

When every request is back, the ledger step is settled to the actual bill, and
`harvest()` files every finished answer in the answer store (key =
sha256(model + NUL + prompt)[:32]). Errored, empty and cut-off answers are never
filed; a wrongly filed one is removed with `drop()` and a record in
`answer_store.jsonl.removed.jsonl`.

### E5. What happens to each kind of failure

| result | what it is | what happens |
|---|---|---|
| finished answer, any length ≤ 128k | a model answer | scored |
| errored / expired / canceled | transport hole | resubmitted unchanged (once) |
| malformed or incomplete answer, budget not exhausted | model answer needing repair | one repair round: original prompt (+ bookkeeping feedback if parseable), at 128k |
| exhausted 128k (stop_reason max_tokens) | resource-bounded non-completion | recorded, not scored, never re-asked (D6) |
| repair call exhausts 128k | repair failed | unit keeps its earlier real answer |
| unit still without any real answer | hole | the cell's game is refused |

### E6. Scoring (`batch_game.score`)

`merge_waves` → `finalise_row` → per cell: `<out>/<cell>/O.jsonl`, `J.jsonl`,
`O.rbnc.jsonl`, `J.rbnc.jsonl` → `integrity_gate` → `report` → `REPORT.txt`
(per-cell sections, predeclared checks, O and J summary tables with the F1
breakdown, the column legend). Re-scoring from stored answers is reproducible and
checked byte-for-byte (predeclared check 6).

### E7. Order and gating (the plan of record, pending sign-off)

| step | content | released when |
|---|---|---|
| 0 | G3 masking side-channel diagnostic, development pool_000 (D8) | before the final price |
| 1 | Headline J, 46 pools (confirmatory) | after the user approves the final price |
| 2 | Grid J, 9 cells × pools 2–25, pool order, 4 batches of 6 pools | same |
| 3 | Hierarchical, 12 prespecified headline pools, k = 20 (batch path) | re-forecast after the first grid batch shows it fits |
| 4 | Headline O, 100 documents, length-stratified | same |
| 5 | Grid O, 30 documents / cell, same documents in every cell | same |
| 6 (optional) | Hierarchical out to 20 pools | same |
| 7 (optional) | Grid O out to 60 documents / cell | same |
| 8, 9 (optional) | Repeats of the reference cell, small then full | same |

If the forecast worsens, steps are dropped from the bottom: 9, 8, 7, 6, 5, 4,
3; then grid J pools from the end of the pool order. Headline J is never dropped.

Samples are fixed by a seeded sha256 order, never by outcome
(`analysis/budget_final.py`). Pool-order submission means any stop leaves every
completed pool paired across all 9 cells.

### E8. Freeze and provenance

Before each paid wave, a manifest records: git commit (and any uncommitted code),
every `cell_manifest.json`, sha256 of every fragment and answer-key file, the
spec's sha256, the prompt templates' and sizing function's source hashes, the
model id, the masking seed, the preflight count, and the estimate. Resubmissions
and repairs get amendment manifests. Decisions go to `docs/RUN_DECISIONS.md`.

### E9. Budget

The final price is `results/budget_final.txt` (`analysis/budget_final.py`),
recomputed after every fix and the k choice were frozen: per-part expected and
95th-percentile cost, the cumulative cost in run order, and the remaining
balance under the wall. The wall is $167 **out of pocket**; credits are bought
plus sales tax, so the ledger's hard limit is $167 ÷ (1 + tax rate).

---

## F. Before pool 2 — status

| item | status |
|---|---|
| presentation seeded per unit (B) | done (D7) |
| coherence-sever fixed and re-cut (A4) | done (D7) |
| subject-verb whitespace-legal cuts, re-cut (A1, A5) | done (D7) |
| hierarchical: 128k pair caps, batch path, live sample (C2) | done (D7) |
| hierarchical k from blocker coverage; 12 pools prespecified | done (D8): k = 20, coverage inadequate at every k |
| G3 masking side-channel diagnostic | D8, development pool_000 |
| grid J and headline J specs built, dry-run, frozen | done: runs/final_gridJ_w1..w4.json, runs/final_headlineJ.json (not submitted) |
| code and records committed | D8 |
| final price approved by the user | **open** |
| tax rate → ledger hard limit = $167 ÷ (1 + rate); tripwire ≈ $160 | **open** |
| headline unlock (D2) recorded at submission | **open**, on approval |
| Memon-inspired joint on all 9 cells and the headline (free) | recommended |

## H. Resolved the same day (RUN_DECISIONS D7)

| finding | resolution | verified by |
|---|---|---|
| coherence-sever × clause cut 95% of boundaries | topic shift = no shared content word; re-cut: 72.3% of clause boundaries, 3,926 fragments | exact fidelity 175/175 |
| coherence-sever × token-window on a spaCy-token ruler | whitespace-word windows; re-cut: 11.88 words / fragment (random / semantic 11.86) | exact fidelity 175/175 |
| subject-verb cut inside "patient’s" / "MP™" | cuts only on whitespace; both cells re-cut | exact fidelity 175/175 each |
| fixed presentation permutation per size | per-unit seeds, independent label and order streams | rebuilt pool-1 prompts: τ(shown, true) mean +0.015, no repeated pattern |
| hierarchical attacker had no batch path | adversaries/hier_batch.py: waves by replay, D6 rules per pair batch | G2c: equals the offline attacker exactly, incl. multi-wave bridge rounds |
| hierarchical output caps sized for gpt-oss | every pair batch at 128k, one attempt | G2c; live sample on grid pool_000 |
| hierarchical never completed a live pool | live batch sample: 24/24 pair batches, 467/467 pairs, $0.50, pool scored | msgbatch_01NUXxhBgUzdLnz6fyYYeuRD |
| hierarchical k unset | pre-declared blocker rule on development data: no k adequate; fallback k = 20 (80.6% of records connected, 41.4% adjacent recall) | results/audit/hier_blocker_calibration.json (D8) |
| G3 never run | run: raw ids in true order → joint F1 0.994 / 1.000 (leak fully exploited); masked → answer order agrees with label numbers and shown order only as its accuracy implies (gaps ≤ 0.016): no side channel. $0.55 | results/audit/g3_diagnostic.json (D8) |

Live sample result (one development pool, semantic × sentence): hierarchical
joint F1 0.380 / advantage +0.285 (linkage F1 0.529, q 0.718) against one-shot
J's 0.642 / +0.587 on the same pool. On this pool the pairwise attacker is the
WEAKER one: its linkage evidence comes from k = 5 TF-IDF candidates per
fragment, one pair at a time, without the whole pool in view. Its value in the
design is completing pools the one-shot attacker cannot (non-completions), and
attacker-dependence, not a higher score.

One documented difference remains: in the batch path a pair the model left
unanswered is not re-asked when a bridge round proposes it again; the
interactive path would ask it again. With every pair answered the two paths ask
identical questions (G2c).

## G. Findings I want challenged

1. **The one-shot ceiling is confounded with fragment count.** The cells most
   likely to exhaust 128k (subject-verb × clause; subject-verb × sentence;
   random × token-window) are also those with the most fragments per pool. A
   non-completion there is partly the defence and partly pool size.
2. **The hierarchical attacker cannot fully separate that confound.** Its
   blocker covers 41% of adjacent pairs even at k = 20 (D8), so a pool it
   completes is completed with most neighbour evidence missing. It shows
   whether a decomposed attacker finishes where one-shot cannot, not whether
   the defence holds against a strictly stronger attacker.
3. **coherence-sever is a new cell definition (D7).** Its fix was chosen from
   text statistics alone, but the re-cut cells were never screened; D5's reason
   to keep them is the complete clause row.
4. **Resolved and kept for the record:** coherence-sever as built was not a
   distinct strategy; the fixed presentation permutation produced no measured
   leak. Both are fixed (D7).
