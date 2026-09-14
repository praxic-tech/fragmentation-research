# Paper-writing packet: results and methodology reference

**Purpose.** A self-contained reference for drafting the PoPETs paper from the
project as it exists at commit a60f3f6 (2026-09-14). Every number below is read
from a committed artifact; the source is named beside each table. Nothing here
launched, tuned or altered an experiment. Where the project record disagrees with
itself, the disagreement is flagged in §20 rather than resolved silently.

**Authorities (read these before overriding anything here):**
`docs/RUN_DECISIONS.md` (D1–D17, the frozen decisions), `docs/adversaries.md`
(attacker names; binding), `docs/results_plan.md` (the analysis plan, committed
unchanged), `docs/embedding_adversary_design.md` (D14), `docs/single_token_edge_design.md`
(D16), `results/final_analysis/` (the analysis package: `RESULTS_SUMMARY.md`,
`CLAIM_EVIDENCE.md`, `BOOTSTRAP_NOTE.md`, `TABLES/`, `MASTER_RESULTS.csv`),
`results/single_token_edge/analysis/` (the frozen D16 analysis).

**Deliverables that accompany this packet:** `results/paper_figures/` (Figs. 1–8:
PDF, SVG, PNG, the plotting script and one CSV per figure; `README.md` with draft
captions) and `results/paper_tables/` (Tables 1–7 in Markdown and LaTeX, plus
`make_tables.py`). Both regenerate from the frozen artifacts with no arguments.

**Labels used throughout.** *Prespecified*: frozen in RUN_DECISIONS before the
paid run it describes. *Development-informed*: a design choice made on
development / screening data (never on headline outcomes). *POST-HOC EXPLORATORY*:
designed after prespecified results were seen, then frozen before its own
evaluation (the embedding attacker, D14; the single-token edge experiment, D16).

---

## 1. Executive summary of the study

**The problem.** Fragmentation-as-privacy: cut a document into pieces, strip the
order and the grouping, scatter the pieces. If an adversary later obtains the
pieces in plaintext, how much of the original can they put back together? The
study treats fragmentation as a *measured* mechanism, not an assumed one, and
asks the question for two content types (clinical prose and structured
identifier records), several cutting rules, and several attackers of increasing
strength.

**Why linkage and ordering are separate.** A fragmented database has two secrets:
*which pieces belong together* (linkage / membership) and *in what order*
(ordering). For prose, both matter; for a record of {name, SSN, account,
address}, order is nearly irrelevant and the association is the whole secret.
The metrics are built so the two can be read separately (§7).

**Games.** *Game O* gives the attacker one document's fragments and asks only for
the order; membership is an oracle. It is the classical sentence-ordering
problem and a reference point. *Game J* gives the attacker every fragment from a
pool of seven documents, mixed, and asks for membership **and** order at once.
J is the threat model's own setting: an adversary holding a fragmented store has
everything mixed and is told nothing. J is harder, and its linkage component
(F1_L) is extracted from the same answer, so no separate linkage experiment was
needed.

**Main result, prose.** Against the strongest attacker tested, a one-shot LLM
(claude-sonnet-5) given all 7 documents' fragments at once, fragmented prose
stayed substantially reconstructable in every tested condition. On the 46
headline pools (full-length case reports, sentence cut) it reached F1_J 0.723
[0.702, 0.743] against an analytic baseline of 0.149: it recovered most membership
(F1_L 0.882) and most order (q 0.792). Across the nine strategy × granularity
cells F1_J ran 0.498–0.801, never near baseline. Strategy mattered: cutting
between subject and verb was the most resistant at both granularities (F1_J
0.498 / 0.553); finer cuts helped modestly within a strategy. The output was a
strong *partial* reconstruction: exact whole-document recovery was rare (1 of
322 headline documents).

**LLM versus everything else.** The classical and statistical attackers sat at
their floors. The Jaccard orderers were at chance in Game O (τ ≈ 0) once an
id-order leak was fixed. The Memon-inspired joint attacker (TF-IDF grouping plus a
directional character-model orderer) scored F1_J 0.168 on the headline, 0.023
above baseline, and ordered at chance (q ≈ 0.5). A post-hoc exploratory sentence-
embedding attacker (all-mpnet-base-v2 grouping with the same orderer) recovered
slightly more linkage than TF-IDF (F1_L 0.364 vs 0.339 on the headline, paired
difference 0.024 [0.005, 0.044]) and remained far below Sonnet (0.882). The gap
between similarity-based grouping and the generative attacker is the paper's
attacker story.

**Identifiers behaved qualitatively differently.** On 20 pools of 7 synthetic
records (28 fields), Sonnet's F1_J was 0.083 [0.068, 0.099]: below the analytic
baseline (0.10) and below the trivial schema-order baseline (0.20) that any
attacker gets by reading field formats. It recognised the record template
perfectly (all 140 groups had one name, one SSN, one account, one address) but
paired fields across records at 0.132 [0.113, 0.154], consistent with 1/7 =
template-respecting chance. The frozen rule's 90% CI on the schema advantage was
[−0.162, −0.129]: not "near" the baseline; below it. Schema is visible; record
association was not recovered under the tested setup.

**Post-hoc single-token boundary experiment.** With the same four-sentence
excerpts from 20 headline pools cut two ways (28 sentence fragments per pool vs
438–669 single whitespace tokens), Sonnet's null-adjusted visible joint
reconstruction fell from A_VJ 0.588 to 0.016 (paired difference 0.572 [0.539,
0.607]; 20/20 pools lower; exact sign test p ≈ 1.9 × 10⁻⁶). Joint reconstruction
at single-token granularity was essentially at its random-shuffle reference,
while a reduced linkage signal survived (A_VL 0.159, positive in 19/20 pools).
Binary, not dose–response: no threshold was located.

**Conclusion.** Fragmentation resistance is not binary. It depends on the data
type (prose vs identifier records), on the retained local structure (boundary
strategy and granularity), on the attacker (similarity-based methods vs a
generative reasoner), and on the attacker's resource budget. The paper's claim
is a characterisation and a contrast, not "fragmentation works" or "fails".

SCRMBL and product implications are kept out of the scientific claims; see §16.

---

## 2. Complete experimental design history

Chronological and conceptual, from the project record. Format for each
important decision: **Decision → reason → alternative rejected → consequence.**

### 2.1 Motivation and the original frame (docs/paper_section3.md, RESEARCH_BRIEF.md)

The starting hypothesis (pre-registered in `paper_section3.md` §3.7): ordering
recovery exploits linguistic signal, which prose has and identifiers lack;
association recovery needs database signal that fragmentation removes. So prose
should be reconstructable and atomic identifiers should not. The paper was
always framed as *characterisation and contrast*, with prose resistance
"expected to be weak"; the contribution is the map, not a defence claim.

### 2.2 Corpus construction (docs/corpus_build.md; datagen/pull_prose.py, pull_prose_v4.py)

- **Decision:** 500 real PMC Open Access clinical case reports, published
  **February 2026 or later**, i.e. after claude-sonnet-5's January 2026 training
  cutoff → so a high LLM score cannot be memorisation → the alternative, a
  hand-written synthetic prose corpus (25 notes), was retired on 2026-08-10
  because its lexical signal was *inverted* (same-record sentences less similar
  than different-record ones, TF-IDF Cohen's d −0.077 vs +0.458 on real prose):
  it made linkage structurally impossible and misstated the LLM-vs-statistical
  gap → consequence: the corpus is post-cutoff by construction (verified 500/500
  against NCBI, 0 unresolved dates) and the "synthetic corpora can invert the
  attack signal" finding is itself reportable.
- Eligibility: PubMed `"case reports"[Publication Type]`, PMC OA subset,
  commercial-use CC licence only (`CC BY-NC*` rejected), publication date ≥
  2026/02; full text via the BioC endpoint; only paragraphs under a
  case-narrative heading are kept (PMC tags whole reports as `INTRO`, so heading
  tracking separates narrative from framing).
- Segmentation: spaCy `en_core_web_sm` sentence boundaries per paragraph, with a
  ≥15-character rule that drops figure-citation debris (`'1A-D).'`); 0.12% of
  tokens dropped, 0 invented (fidelity gate). Token-window cells drop nothing.
- Size: 500 documents, 16,524 sentence fragments, ~315k words; document length
  5–287 sentences (median 28).
- Three earlier bugs are recorded (invalid OA filter, bare PMC id, licence
  prefix test) — history, not results.

### 2.3 Pool construction (datagen/build_pools.py; data/pools/manifest.json)

- **Decision:** pools of exactly 7 documents, 71 pools, built once (seed-42
  shuffle of the sorted document ids, dealt consecutively; 497 documents
  pooled, 3 held out: prose_0012, 0057, 0327) → the pool is the independent
  unit and every cell is a comparison of the *same* pools cut differently →
  rebuilding pools per cell would silently change the true-pair set → the
  partition ships with the paper; membership has been byte-identical since
  2026-08-28 (commit c7a1b43), before any pool-level attack (D16 verification).
- **Why N = 7.** Ten documents in one shot already failed (>48k output tokens),
  and pool size sets the chance baseline, so it never varies: an earlier
  pools-of-5 run reported F1 0.22 that was indistinguishable from its ~0.20
  baseline. Fixing N = 7 everywhere is what makes cells comparable.
- **Why 71 pools, not 10.** Per-pool baselines range 0.251–0.503, so pools are
  not interchangeable; SEM over 71 pools ≈ 0.010 vs 0.026 over 10.

### 2.4 Development / grid versus headline split (D2, D5; development history)

- **Decision (D2, 2026-09-10, "frame A"):** 25 pools (`linkage_grid.json`, 175
  documents) are DEVELOPMENT / GRID; the other 46 (322 documents) are HEADLINE,
  untouched by any request until the headline run → keeps the confirmatory
  estimate free of prompt or strategy selection → consequence: the headline
  guard (`build_spec` refuses any request touching a headline document) was
  enforced in code from commit 7ac35ad until the D12 unlock.
- **Prior development contact.** Before frame A existed, development work
  (an 8-document free-tier probe, a 25-document pilot, the llm-cut prompt cache,
  week-6 llm-cut cells) used documents later assigned to the headline: **21
  headline documents in 18 of the 46 pools; 28 pools never touched.** What that
  contact informed: operational design (pool size, max_tokens sizing, repair,
  integrity checks), the choice of J as the headline game, and an llm-cut prompt
  (re-selected later on development documents). No strategy was chosen and no
  headline estimate computed on them. Decision: all 46 pools are the headline
  set; the 28 never-touched pools are available as a robustness check (not run).
  **Wording rule (D16):** do not describe the headline pools as literally
  "untouched".
- **Pool 1 is screening (D4 clarification → D5).** The first grid pool was paid
  for as a staged slice; after its results, two cells were cut (semantic ×
  token-window, coherence-sever × sentence) and the LLM-cutter cell left the
  confirmatory grid. Because that selection used pool 1's scores, pool 1 is
  *development-informed screening data* and is excluded from every final
  table; the grid is pools 2–25 (24 pools, 168 documents). The dropped cells'
  pool-1 results are preserved in `results/audit/pool1_screening/`.
- **Grid corpus.** The 175 development documents are truncated to the first N
  sentences such that the reference cut yields ≤30 fragments (62 documents
  truncated; `data/grid_corpus_A/manifest.json`), so granularity remains the
  independent variable rather than the cap. The headline uses full length. Grid
  documents therefore average 478 words vs 659 for the headline.

### 2.5 Why Game O, why Game J, why no standalone L (adversaries/joint_game.py; results_plan §29)

- **Game O exists** as the membership-oracle reference and to place the
  classical orderers, whose literature is sentence ordering.
- **Game J exists** because it is the threat model: a stolen fragment store is
  mixed and unlabeled. Information flows one way (L is derivable from J; J is not
  derivable from O or L), so data were collected jointly.
- **No standalone final Game L** → F1_L is the linkage component of the J answer
  (drop the order) → running L separately would buy a number already contained
  in J → **wording rule:** "the linkage component of game J", never "a game L
  experiment".
- **O is a reference, not a ceiling** → for a prompted model, changing the task
  can hurt as well as help, and O and J are differently prompted on different
  units → the old "J minus O gap" was replaced by the F1_J = F1_L × q
  decomposition as the clean evidence of where J fails.

### 2.6 Metrics decisions (harness/joint_metrics.py; D11, D13)

- **Raw F1_J is primary** → it is on one scale for every attacker and every
  condition, and it generalises both older metrics (direction ignored → F1_L;
  perfect membership → (1 + τ)/2) → the normalized advantage A_J = (F1_J −
  b_J)/(1 − b_J) exists because each pool's trivial baseline differs with its
  fragment-count distribution; A_J is computed per pool then averaged.
- **The analytic baseline is a baseline, not a floor** → the all-singleton
  answer scores 0, lower than one bucket → "floor" is reserved for the
  classical attackers' *observed* level.
- **Bootstrap units** → pools for J, documents for O (results_plan §2): the
  pool is the sampling unit and its pairs are not independent evidence.
- **RBNC is excluded rather than scored 0** (D6) → exhausting the 128k output
  budget without an answer is a resource event, not a wrong reconstruction →
  scoring 0 conflates capability with resource exhaustion; re-asking would
  most likely repeat the bill → completion / RBNC rates are reported separately
  from scores; paired comparisons use pools where both conditions completed;
  an RBNC in one cell never removes the pool from other cells.

### 2.7 Presentation, masking, repair and retry policy (D6, D7, harness/repair.py, adversaries/batch_game.py)

- **Masking.** Fragment ids leak position (`prose_0002_frag_000`), so the
  attacker sees 9-character aliases (`m_0000153`) drawn as a collision-free
  permutation (an earlier `randint` masker silently dropped ~128 fragments per
  16,524 by birthday collisions; fixed 2026-08-10). A preflight refuses any
  prompt containing a raw id.
- **Per-unit shuffling (D7).** Label assignment and presentation order are
  seeded from SHA-256 of the unit's fragment ids and texts, the run seed and the
  purpose, as independent streams. Before D7 the shown order correlated
  negatively with truth (τ −0.137); after, +0.015.
- **The masking side-channel check (G3, D8).** On development pool_000, the same
  prompts were sent masked and with raw ids in true order. Raw ids: F1_J 0.994 /
  1.000 (the planted leak is exploited completely). Masked: the answer's
  agreement with label numbers and with the shown order equalled what its
  accuracy alone implies (every gap ≤ 0.016): no measurable id or presentation
  side channel; masked reconstruction is high because the model reads content.
- **Repair (one structural round).** An answer is repaired iff it is unparseable
  or its labels are missing, duplicated or not in the input; the repair prompt is
  the original plus bookkeeping the attacker could compute itself (which of
  *its own* labels are missing / duplicated / invented). Never: any truth, and
  not N when N was withheld. After the round: invalid ids discarded, duplicates
  first-wins, unplaced valid ids become singletons (costs recall, never inflates
  precision), all counted. A unit with no real model answer is never scored
  around; its cell would be refused.
- **Transport / provider retry.** One resubmission, unchanged, for a request that
  errored, expired, or was refused before inference (48 requests were refused for
  insufficient prepaid credit in the final run: 0 token usage, resent once from a
  provider-record manifest, all answered). Order rule (user, 2026-09-13): every
  resend before any repair, so a credit shortfall can only cost repairs.
- **The 128k rule (D6).** Every request gets the model's full 128,000-token
  output ceiling, one attempt. Measured on pool 1: ≥96.7% of every J answer's
  output is the model's internal reasoning (visible answers ≤ ~2k tokens), so
  output scales with how long the model thinks, not with the answer; the only
  levers that cut reasoning change the attacker (a lower effort setting returned
  invalid output in development). Paper wording: *the 128k cap is a prespecified
  attacker resource budget, not a fundamental limit of modern AI.*
- **Model settings frozen in the manifest** (`runs/final_headlineJ_manifest.json`
  and siblings): `claude-sonnet-5`, Message Batches API, `max_tokens` 128000,
  prompt-template SHA-256 5107194b…, masking seed 42, per-unit presentation
  seeds. The API rejects `temperature` / `top_p` for this model, so none was
  set; reasoning is the model's default adaptive setting. Output cut off at
  `max_tokens` is a hole, never an answer (G1e).

### 2.8 The old Pool-1 permutation flaw and its correction (D4 clarification, D7)

Pool 1's first submission had two operational defects found *before* any
confirmatory pool: (i) 30 of 88 answers were cut off at undersized `max_tokens`
caps (the caps were sized at 2× a cost model whose anchors Sonnet exceeded);
diagnosed as TRANSPORT, so requests were resubmitted byte-identical with larger
caps and the 58 finished answers stayed; (ii) presentation shuffles were seeded
once per run rather than per unit, so shown order correlated with truth (τ
−0.137, never positive). D7 fixed the seeding per unit, every prompt changed,
pool-1 answers could not be reused, and pool 1 became screening data (D5). Both
fixes preceded every headline and grid request. A parser fix (an answer with a
bracketed clinical phrase before the JSON was misread) was a SCORING fix: stored
answers re-scored, nothing re-bought.

### 2.9 The Jaccard / Memon naming issue and its correction (D1; docs/adversaries.md)

Michael's classical Game O orderers were labelled "Memon-Greedy / Memon-MST" in
the harness. They score pairs by word-bigram Jaccard (symmetric) and share
nothing with Shanmugasundaram & Memon beyond "build a path through fragments".
They also received raw fragment ids in true file order, and since Jaccard is
exactly 0 for 86.7% of within-document pairs, ties fell to the id and reproduced
the truth: their τ of +0.32 / +0.70 was leakage. D1 (2026-09-10): masked labels,
shuffled presentation, truth-independent deterministic tie-breaking (MST also
iterated Python sets, non-deterministic across processes). Corrected: τ −0.030 /
−0.018 on prose, chance. Renamed **Jaccard-Greedy / Jaccard-MST**; the legacy
behaviour exists only behind an audit flag. Their historical "game L" numbers
were a shared TF-IDF grouper, not a Jaccard attack, so they appear in Game O
only; no Game J version was built to make tables symmetrical.

**Never write:** "Memon" alone, "faithful Memon", or "pre-LLM state of the art"
(the latter was an overclaim in an earlier draft and is corrected with a dated
note in `paper_section3.md`).

### 2.10 What "Memon-inspired" means technically (adversaries/memon_joint.py; D12, D13)

Grouping: TF-IDF cosine similarity → average-linkage agglomerative clustering →
cut to exactly the known N = 7 (tiny seeded jitter for exact ties). Ordering: a
directional character-bigram boundary likelihood (a fixed-order smoothed
character model trained on the pool's own fragments; successor B of A scored by
the log-probability of B's first two characters given the characters across the
boundary; s(A→B) ≠ s(B→A)) → antisymmetric weight W = tanh((s_AB − s_BA)/2) → a
deterministic insertion local search over orderings from three deterministic
starts. Settings n = d = 2 frozen (D12; development evidence showed ordering at
chance for every n from 2 to 8, so the choice cannot favour the attacker).
Inherited from Memon: only the idea of judging adjacency by how well a
statistical character model predicts text across a candidate boundary. Ours: no
PPM, no Hamiltonian-path / tree-pruning reassembly, TF-IDF grouping, the tanh
weighting, the local search, the masking controls. **SHA-256 seed fix (D13,
commit 0621396):** the third search start used Python's `hash()`, which varies
per process; replaced before any analysis used the results. Effect: 9 of 282
pools changed F1_J / q (max |Δ| 0.023, no condition mean by > 0.0003); F1_L
unchanged in all 282; post-fix runs identical across hash seeds. The pre-fix run
is kept in `results/audit/memon_joint_pre_sha256`.

### 2.11 The embedding attacker and why it is post hoc (D14 + addenda; docs/embedding_adversary_design.md)

Designed after the final one-shot and Memon-inspired results were visible, to
answer "would sentence embeddings have done it?" and to locate the gap between
lexical grouping and the LLM. **The embedding representation is the only
architectural change** relative to Memon-inspired: `sentence-transformers/
all-mpnet-base-v2` (109M parameters, 768-d mean-pooled, L2-normalised, cosine),
pinned to revision e8c3b32e… with per-file hashes, no fine-tuning, 384 word-piece
limit (1 fragment of 62,527 was truncated by 2 word pieces, kept as run);
average-linkage cut to exactly N; the frozen Memon-inspired orderer unchanged.
Every parameter is a standard default or inherited; nothing was tuned. The
development smoke test was score-blind (pipeline, word-piece lengths, bit-identical
embeddings on repeat, batch-size stability ≤ 5.3e-7, cross-process determinism,
measured throughput 22.5 fragments/s). One correctness fix, not tuning: cosine
distance clamped at 0 after floating-point rounding made 1 − sim slightly
negative. Run once on all 282 final J pools (~90 min CPU); first complete result
kept. **Required disclosure wording:** motivated by the observed gap between
Memon-inspired and one-shot Sonnet; fully designed and frozen before its own
evaluation; no final-data tuning and no model selection from its scores; F1_L is
its primary comparison, F1_J and q secondary. Contamination: the model's training
pairs (e.g. S2ORC) predate the post-cutoff corpus, which reduces but does not
exclude concern; make only that limited claim.

### 2.12 Why the hierarchical full run was dropped (D7, D8, D10, D11, D13, D17)

A decomposed attacker (TF-IDF candidate blocking at k = 20 → Sonnet pairwise
judgements → exactly-N clustering → rank aggregation) was built, tested, and
priced as the architecture that has no per-call ceiling. Its k was chosen from
blocker coverage on development data, never from F1; coverage was inadequate at
every tested k (13–28% of same-record pairs exposed), though an oracle-ceiling
diagnostic showed the downstream architecture could still reach F1_J ≈ 0.88 if
the pair judgements were perfect. Its role was frozen as (a) rescue of headline
one-shot RBNCs and (b) a 12-pool paired comparison, never averaged into the
headline. **No headline pool hit an RBNC (0 of 46)**, the rescue set was empty,
budget priority put it last, and the user dropped it (D17, 2026-09-14). One
development live sample exists (k = 5, pool_000 semantic × sentence: F1_J 0.380
vs one-shot 0.642 on the same pool; $0.50) and is development data only. **Paper
wording:** the hierarchical attacker was not run (dropped); do not call it
"pending" (the analysis package's Table F / `HIERARCHICAL.csv` still say
"pending" — see §20).

### 2.13 Identifier corpus and why it is synthetic (docs/identifier_corpus.md; D11; paper_section3 §3.7)

- 500 records from a seeded Faker generator (seed 42): `name` (first + last),
  `ssn` (###-##-####), `account` (10 digits), `address` (street address). One
  fragment per field; 2,000 fragments. 499/500 names unique; two records share a
  name (unlinkable by any attacker; lowers the ceiling, leaks nothing).
- **Why synthetic** → the closed-world property must hold *by construction*: no
  synthetic identifier corresponds to a person, so no breach corpus, public
  record or SSN-prediction trick (Acquisti & Gross 2009) can corroborate a link;
  any correct linkage is provably intrinsic signal → real SSNs / account data
  would be an ethics, privacy and API-governance problem, and real identities
  could violate the closed world through external lookup → consequence: the
  external validity of the *synthetic structure* is a limitation (§15).
- **Records r_0050–r_0499 only** (the first 50 were shown to an LLM in week-2/3
  exploratory runs and are excluded for that exposure, not for their results);
  ordered by SHA-256('identifier-J|' + record_id), dealt into pools of 7; primary
  sample = the first 20 pools, fixed before any result and not extended.
- **The schema-order baseline** (D11): every fragment in one bucket, ordered by
  the published field order with each field's type read from its *format*
  (`^\d{3}-\d{2}-\d{4}$` → SSN, 10 digits → account, leading street number →
  address, else name), within-type order by a text hash. It reads only the
  prompt, never the key; verified truth-free, invariant to shuffling and
  relabelling, classifier 2,000/2,000 correct, F1_J exactly 0.2000 = 2T/(P+T)
  with q = 1.000 on all 20 pools. So identifier **q measures the template, not
  reconstruction**, and J is reported against two baselines: analytic 0.10 and
  schema-order 0.20.
- **Frozen claim rule (D11):** "near the schema-order baseline" iff the whole 90%
  CI on A_schema = (F1_J − 0.20)/(1 − 0.20) lies within ±0.10 (raw difference
  reported alongside; the verdict does not depend on the choice). Nonsignificance
  is never read as equivalence.

### 2.14 The single-token experiment (D15 → D16; docs/single_token_edge_design.md)

- **Motivation.** The grid's finest cut (12-word windows) still left F1_J ≥ 0.63.
  The user asked what happens at the extreme end of the granularity axis. A
  naturally short extension corpus was investigated and stopped (no PMC document
  is short enough: minimum 99 words). A first excerpt design (D15, ~40-word
  excerpts, 10 pools) was built but never submitted and was superseded.
- **Design (D16, frozen at commit 7d01938, launched 2026-09-14).** 20 headline
  pools chosen by SHA-256 of UTF-8("single-token-edge-v1" + pool_id), no separator;
  their existing 7-document membership kept (140 documents). Per document: the
  corpus's own segmenter on the original source text with the ≥15-character
  filter *disabled*, four consecutive sentences starting at
  SHA-256("single-token-edge-v1" + document_id) mod the number of valid starts.
  Selecting before the length filter guarantees genuine contiguity; 27 of 140
  excerpts differ from what the filtered sequence would give, and 7 contain a
  sub-15-character source stub (e.g. a figure citation), kept. **Two arms on
  identical text:** sentence cut (4 fragments per document, 28 per pool) and
  single whitespace-token cut (verbatim tokens, no normalisation; median 523 per
  pool, range 438–669). Same prompt, N knowledge, masking, per-unit shuffle,
  model, 128k rule, repair policy and scorer as every J run; no word-level
  prompt. No Game O. Nothing dropped or replaced for any reason; RBNC would have
  stayed RBNC.
- **The duplicate-token identifiability problem.** The id-level scorer treats
  each hidden id as distinct, but at token granularity many *visible* tokens are
  identical ("the", "of"); an attacker that places a visibly correct "the" in
  the right place with the wrong hidden id is penalised for something it could
  not know. So a **visible, duplicate-invariant scorer** was frozen
  (`harness/visible_metrics.py`): hidden ids are mapped back to visible text,
  both arms are converted to token sequences; V_L = one-to-one (Hungarian)
  assignment of predicted groups to true documents maximising matched token
  occurrences (multiset intersection) / total true tokens; V_J the same with
  token-level LCS length; invariant V_J ≤ V_L; dropped fragments read as
  singletons; duplicates counted once. 29 scorer tests on constructed data.
- **Permutation nulls** (the analytic b_J does not apply to visible metrics):
  10,000 deterministic draws per pool × condition × null type (numpy PCG64 seeded
  by SHA-256 of a namespace string). *Oracle-size* (PRIMARY): permute labels, cut
  into 7 groups of the true sizes, keep permuted order. *Predicted-structure*
  (ROBUSTNESS): permute into the attacker's own group sizes and positions.
  A_V = (V − null mean)/(1 − null mean).
- **Why post hoc.** Designed after all prespecified results; a boundary case on
  a different task (4-sentence excerpts), separate from the grid; exploratory
  throughout, with claim restrictions frozen in advance (§12).

### 2.15 Budget and spend controls (D9, D11, D13, D17)

A ledger with a $182 credit tripwire and a $197.64 hard limit ($210 cash at 6.25%
tax); each submission's worst case (every request at 128k) checked against the
wall, so grid J and grid O went out in waves. Spend priority: headline J → grid
J → identifier J → headline O → grid O; hierarchical last (dropped). Final
one-shot run $119.37 credit; all paid calls in the project $144.32 (Table 7).

---

## 3. Threat model (paper-ready)

**Setting.** A fragmentation scheme cuts each document into contiguous pieces and
withholds their order and grouping. We deliberately give the adversary the
*plaintext* pieces: the question is what order- and membership-deprivation alone
withholds, independent of any encryption or hardware layer. A scheme that resists
reassembly on plaintext resists it a fortiori when the pieces are also encrypted.

**Main closed-world Game J.** The attacker receives *all* fragments of a finite
pool of N = 7 source documents, with fragment contents, masked aliases, knowledge
of N, and a shuffled presentation; without true memberships, true order, or raw
fragment ids. It must output a partition into 7 ordered groups. Scoring is
against the hidden key (§7). The attacker is denied auxiliary context: no web
access, external corpus or named-record set (the closed world is enforced by the
harness for prose, whose sources are public papers, and by construction for the
synthetic identifiers).

**Game O.** The same, for one document with membership given; asks only for order.

**Attacker-favourable relative to deployment.** Relative to a distributed,
partial-compromise deployment, Game J is attacker-favourable in four ways: every
fragment of every pooled document is available; every represented source is
complete; the number of sources (7) is known; and the pool is small (≈140–540
fragments) rather than a global population of thousands or millions of fragments
from unknown numbers of sources, many partially represented. **This study does not
evaluate that deployment-level partial-compromise problem.** Its numbers bound
what an attacker with complete, small-pool access can do; they do not estimate
leakage under partial compromise or global shuffling.

**Why the high prose linkage matters for that untested setting.** Linkage in J is
achieved from content alone with masked ids and a shuffled presentation (the G3
control shows no side channel). A membership signal of F1_L 0.88 on 7-document
pools means content-based linkability is *present*; a global shuffle over many
more documents changes the search problem, not the existence of the signal. So
one cannot *assume* that global shuffling eliminates semantic linkability; that is
a hypothesis for a future experiment (§17), and the direction of the change is
not established here.

**Resource model.** The one-shot attacker's per-call output budget (128,000
tokens, one attempt) is a prespecified resource bound; larger budgets or future
models could reduce non-completions. Only one of 652 prespecified units hit it.

---

## 4. Datasets

### 4.1 Clinical prose (`data/prose/`)

| item | value | source |
|---|---|---|
| documents | 500 PMC OA case reports, case-narrative paragraphs only | corpus_build.md |
| publication date | ≥ 2026-02 (after claude-sonnet-5's 2026-01 cutoff); 500/500 verified post-cutoff | corpus_build.md |
| licence | commercial-use CC only (CC BY-NC* rejected) | pull_prose.py |
| language | English (PubMed / PMC English full text; no explicit language filter was applied) | — |
| reference cut | spaCy sentences per paragraph, ≥15 chars (= semantic × sentence) | prose_cutter.py |
| fragments / words | 16,524 sentence fragments; ~315k words; 2.22M characters | corpus_build.md |
| document length | 5–287 sentences, median 28; headline documents mean 659 words, 33.5 fragments | RESEARCH_BRIEF, table_D/H |
| pools | 71 × 7 = 497 documents (3 held out), seed 42, fixed 2026-08-28 | manifest.json, D16 |
| development / grid | 25 pools (175 docs); pool 1 = screening; grid = pools 2–25 (24 pools, 168 docs), documents capped at 30 reference sentences (62 truncated; mean 478 words) | D2, D5, grid_corpus_A/manifest.json |
| headline | 46 pools (322 docs), full length | D2 |
| prior development contact | 21 headline documents in 18 pools (28 pools never touched) | RUN_DECISIONS development history |
| fingerprints | answer key sha256 1a05fef4…; headline fragments a59b87a1…; grid corpus A 66b646c9… | manifests |
| fidelity | 0 invented tokens; 0.12% of source tokens dropped by the ≥15-char rule (figure-citation stubs); token-window drops 0.00% | corpus_build.md |

**Caveats to state:** (i) real published papers; the closed world for prose is a
harness assumption (an attacker with a search engine could look up co-occurring
sentences), which post-cutoff does not remove; (ii) English clinical narrative
only; (iii) the 0.12% dropped debris is disclosed.

### 4.2 Synthetic identifiers (`data/identifier/`)

| item | value |
|---|---|
| records | 500, Faker `en_US`, seed 42; fields name, SSN, account (10 digits), street address; one fragment per field |
| held-out range | r_0050–r_0499 (450 records; r_0000–r_0049 excluded for prior LLM exposure) |
| pools | ordered by SHA-256('identifier-J\|' + id), pools of 7 → 64 pools; primary = first 20 (140 records, 28 fragments per pool); reserve never run |
| baselines | analytic one-bucket 0.10 (F1_L 0.20); schema-order 0.20 (F1_L 0.20, q 1.0); random partition 0.056 |
| why synthetic | closed world by construction; no real PII; no governance problem; any correct link is intrinsic signal |
| limitation | synthetic field formats and Faker distributions; real records carry correlated structure (names ↔ addresses ↔ region, reused values, free text) that this corpus does not |

### 4.3 Single-token excerpts (`results/single_token_edge/`, `data/pools/single_token_edge_pools.json`)

| item | value |
|---|---|
| pools / documents | 20 headline pools × 7 = 140 documents |
| selection | pools: first 20 by SHA-256(UTF-8("single-token-edge-v1" + pool_id)), no separator; membership as in pools.json |
| excerpt | 4 genuinely consecutive source sentences; segmenter `pull_prose_v4.split_sentences(prose_raw, min_chars=1)`; start = SHA-256("single-token-edge-v1" + doc_id) mod valid starts; selected **before** the ≥15-char filter (27/140 excerpts differ from the filtered rule; 7 contain a short stub) |
| words | median 73 per excerpt (34–153) |
| arms | sentence: 4 fragments/doc, 28/pool; token: median 523/pool (438–669), verbatim whitespace tokens; same text asserted per document |
| prior development contact | 9 of the 140 documents, in 8 of the 20 pools (provenance only) |
| dropped / replaced | none, for any reason; completion 20/20 in both arms |

---

## 5. Fragmentation conditions

**Granularities.** *Sentence*: one spaCy sentence per unit. *Clause*: clause-level
splits inside each sentence (same spaCy base; strictly finer than sentence, never
fewer fragments). *Token-window*: fixed 12-whitespace-word windows, structure-blind
(cuts mid-clause 93% of the time).

**Strategies** (all deterministic, all partition the source exactly; verified by
`analysis/verify_fragments.py`):

- **semantic** — cut at every boundary of the granularity unit. *Semantic × sentence
  is standard sentence splitting and the reference cut*; it is not evidence for a
  distinct "semantic" cutter.
- **random** — cut at random whitespace positions, with the fragment count matched
  to the semantic reference count for the same document and granularity (per-document
  SHA-256 seed). Controls for count so a difference reflects boundary placement.
- **coherence-sever** — keep only the granularity boundaries that carry a discourse
  link (the next unit opens with a connective or an antecedent-needing pronoun, or
  the two units share no content word), merging the rest; at token-window
  granularity, window edges snap to the nearest discourse-bearing token. Re-cut in
  D7 after the original topic-shift rule fired at 82–84% of boundaries.
- **subject-verb** — within each granularity unit, cut immediately before the
  governing verb of the first nominal subject (`nsubj`; whitespace cut points only),
  producing (subject) | (verb onward); units without an `nsubj` are emitted whole.
  Fires on ~72% of sentences and ~65% of clauses.

**Retained cells (9):** random × {sentence, clause, token-window}; semantic ×
{sentence, clause}; coherence-sever × {clause, token-window}; subject-verb ×
{sentence, clause}.

**Dropped before final evaluation:** semantic × token-window and coherence-sever ×
sentence (D5, after pool-1 screening; development-informed, disclosed);
subject-verb × token-window was never built (degenerate: collapses to random);
the LLM-cutter cell (Kimi K3 / earlier Sonnet) left the confirmatory grid on
design grounds (the paper is about deterministic, reproducible cuts); its
development profile (`docs/llm_cut_profile.md`: an LLM asked to cut for
unlinkability never breaks a clause) is available as development material only.

**Mechanics per cell** (`TABLES/table_C2_grid_mechanics.csv`; 24 pools, documents
mean 478 words):

| cell | frags / doc | frags / pool (min–max) | words / frag mean (median) | frags per 1,000 words |
|---|---|---|---|---|
| random / sentence | 24.6 | 172 (136–205) | 19.5 (14.0) | 51.5 |
| semantic / sentence | 24.6 | 172 (136–205) | 19.5 (17.6) | 51.5 |
| subject-verb / sentence | 40.9 | 287 (236–344) | 11.7 (9.3) | 85.9 |
| random / clause | 30.9 | 216 (178–257) | 15.5 (10.9) | 64.8 |
| semantic / clause | 30.9 | 216 (178–257) | 15.5 (13.5) | 64.8 |
| coherence-sever / clause | 22.6 | 159 (125–200) | 21.3 (14.2) | 47.5 |
| subject-verb / clause | 48.5 | 339 (288–414) | 9.9 (7.5) | 101.7 |
| random / token-window | 40.3 | 282 (238–336) | 11.9 (8.6) | 84.3 |
| coherence-sever / token-window | 40.2 | 282 (236–333) | 11.9 (12.0) | 84.2 |
| headline (semantic / sentence, full length) | 33.5 | 239 (143–537) | 19.3 | — |

Note that coherence-sever / clause is *coarser* than semantic / clause (it merges
non-link boundaries), and subject-verb roughly doubles the fragment count of its
granularity. Granularity is confounded with fragment count and fragment size by
design; the analysis treats those as associations (§9F).

---

## 6. Attackers

Names are binding (`docs/adversaries.md`). Every J attacker goes through the same
scorer (`joint_game.score_row`) on the same frozen pools, aliases and shown order.

### Analytic baselines (harness/joint_metrics.py)

"Put every fragment in one bucket in an arbitrary order", computed in closed form
from the pool's true group sizes. With T = Σ_d C(m_d, 2) true within-document
pairs and P = C(M, 2) pairs in the bucket: E[F1_L] = 2T/(P + T) (recall 1,
precision T/P) and E[F1_J] = T/(P + T) (a random direction is right half the
time). In English: F1_L ≈ 0.30 on the headline is what you get by saying "they
all belong together" — every true pair is claimed, along with six times as many
false ones. It is a *baseline*, not a floor: an all-singleton answer scores 0.
Per pool: headline b_J mean 0.149 (range 0.126–0.251 across the 46 pools), grid
cell means 0.128–0.132, identifiers exactly 0.10 (28 fragments, 7 × 4).

### Jaccard-Greedy and Jaccard-MST (harness/orderers.py; Game O only)

Michael's original classical orderers. Pair score = word-bigram Jaccard overlap
(symmetric, no direction). *Greedy*: start at one of the two least-similar
fragments, repeatedly append the most similar unvisited fragment, keep the better
chain. *MST*: maximum spanning tree (Prim), start at a leaf, walk the heaviest
unvisited edge. Earlier labelled "Memon-*"; that was wrong (§2.9). With masked
labels, shuffled presentation and truth-independent tie-breaking (D1) they are at
chance (Table 4): headline τ −0.005 [−0.032, 0.022] and 0.012 [−0.016, 0.041].
They have no linkage mechanism of their own and appear in Game O only.

### Memon-inspired joint attacker (adversaries/memon_joint.py; Game J)

As in §2.10: TF-IDF cosine + average linkage cut to exactly N; directional
character-bigram boundary likelihood; antisymmetric tanh weights; deterministic
local search; n = d = 2; SHA-256-seeded. Inspired by, not faithful to, Memon (no
PPM, no Hamiltonian-path search). Result: linkage slightly above baseline
(headline F1_L 0.339 vs 0.299), ordering at chance (q 0.493), F1_J 0.168. Its
role is a statistical floor.

### MPNet embedding attacker (adversaries/embedding_joint.py; Game J; POST-HOC EXPLORATORY)

As in §2.11: all-mpnet-base-v2 (768-d, cosine), average linkage to N = 7, the
same deterministic directional orderer, no fine-tuning, pinned revision,
score-blind smoke tests, deterministic across processes. It is a
*semantic-similarity* attacker: it can only group fragments that embed alike; it
has no mechanism to reason about narrative continuity, entity persistence or
clinical plausibility, and no ordering signal beyond the inherited character
model. That is exactly why it separates "semantic similarity" from "generative
reasoning" in the attacker comparison.

### One-shot Sonnet (adversaries/joint_game.py, batch_game.py; Games O and J)

- Model `claude-sonnet-5` through the Message Batches API; `max_tokens` 128,000;
  no temperature (rejected by the API); default adaptive reasoning; prompt
  template hash 5107194b…; masking seed 42; per-unit presentation seeds.
- **J prompt (verbatim skeleton):** "Below are {M} shuffled fragments taken from
  7 different records and mixed together. You are given no information about
  which fragment came from which record. Do two things at once: 1. Work out which
  fragments belong to the same record (7 records in total; they may contain
  different numbers of fragments). 2. Within each record, put its fragments back
  into their original order. Use every item exactly once. Fragments: {alias:
  text lines} Return ONLY a JSON array of 7 arrays. Each inner array holds the
  item labels of one record, IN THEIR RECONSTRUCTED ORDER. No explanation, no
  markdown."
- **O prompt:** "These fragments are pieces of ONE record, shuffled. Put them back
  in their most likely original order. … Return ONLY a JSON array of the item
  labels in your best order."
- N is given; raw ids never; aliases 9 characters; output parsed as the longest
  JSON list (fenced first); one structural repair round; one transport resend;
  RBNC at 128k never re-asked.
- **Units and cost (final run):** 652 one-shot units (282 J: 46 headline, 216
  grid, 20 identifier; 370 O: 100 headline, 270 grid), 651 completed, 1 RBNC;
  48 credit refusals resent; 51 repairs; 3.9M input / 23.1M output tokens;
  $119.37 credit. Plus the post-hoc single-token run: 40 units, 40 completed, 11
  repairs, $14.15.

### Random (Game O floor; identifier J baseline, D11 / D13)

O: expectation τ = 0 exactly. Identifier J: shuffle, deal round-robin into the
known 7 groups, keep the shuffled order; mean over 10,000 seeded draws per pool.

### Hierarchical (decomposed) Sonnet — not run (dropped, D17). Do not tabulate.

---

## 7. Metrics, in English first

- **Kendall τ (Game O).** For one document: of all pairs of fragments, the share
  whose relative order the attacker got right minus the share it got wrong.
  +1 perfect, 0 random, −1 reversed. Formula: scipy `kendalltau` between the
  guessed and true ranks (no ties, so τ-a). "Pairs correct" = (1 + τ)/2.
- **F1_L (linkage component).** Treat the answer as a set of claimed "these two
  fragments share a document" pairs. Precision = the share of claimed pairs that
  are real; recall = the share of real pairs that were claimed; F1_L their
  harmonic mean. **F1_L = 0.30 is not "30% of documents recovered"**: it is what
  claiming *every* pair gives on a 7-document pool (recall 1, precision ≈ 0.18).
  F1_L 0.88 means the claimed same-document pairs are mostly right *and* most
  real pairs were claimed. It says nothing about order.
- **F1_J (joint, primary).** The same, but a pair counts only if the two fragments
  share a document **and** the attacker put them in the right relative order
  (ordered pairs). Precision C/|guessed|, recall C/|true|, F1 harmonic mean.
- **q (direction accuracy).** Among the pairs the attacker correctly linked (K),
  the share it also directed correctly (C): q = C/K. Reported micro-averaged over
  a condition, q_micro = ΣC/ΣK (a pool with K = 0 has undefined q, reported as
  such, never as 0). Chance is 0.5.
- **The identity F1_J = F1_L × q** holds exactly per pool (max residual 2e-16) and
  is the clean split of "which half failed".
- **Why perfect membership gives F1_J = (1 + τ)/2, not τ.** With membership
  perfect, every real pair is claimed and F1_J is the concordance fraction: the
  share of pairs in the right direction. Random order gives 0.5 (τ = 0); full
  reversal gives 0 (τ = −1). A perfectly grouped but fully reversed document
  therefore scores 0; disclosed edge case for the Methods.
- **Analytic baseline b_J, b_L.** §6. **A_J = (F1_J − b_J)/(1 − b_J)**: 0 at the
  trivial baseline, 1 at perfect, negative below the baseline; computed per pool
  and then averaged. **A_schema** (identifiers): the same with b = 0.20.
- **Exact reconstruction.** A document counts as exact only if its group is
  exactly its fragments in exactly the true order.
- **Completion / RBNC.** Completed = a real answer within the 128k budget; RBNC =
  the budget was exhausted with no complete answer (recorded, not scored, never
  0). Completion rate is reported next to every score, never merged with it.
- **Visible-text metrics (single-token experiment only).** V_L: map every id back
  to its visible token(s); match predicted groups to true documents one-to-one
  (Hungarian) to maximise the total number of token occurrences in common; divide
  by the total true tokens. V_J: the same with the longest common subsequence
  instead of the multiset intersection, so order counts. V_J ≤ V_L always. q_V =
  V_J / V_L is a diagnostic only. **Why they need their own null:** the analytic
  baseline is defined on hidden-id pairs, not on visible tokens, and V is
  duplicate-invariant, so "what does a random shuffle score?" must be measured:
  10,000 permutations per pool × condition. **Oracle-size null** (primary):
  random labels into 7 groups of the true sizes, random order within. **Predicted-
  structure null** (robustness): random labels into the attacker's own group sizes
  and positions. **A_VL, A_VJ** = (V − null mean)/(1 − null mean): the fraction of
  the gap between the pool's random-shuffle reference and perfect visible
  reconstruction that the attacker achieved. A_VJ(sentence) − A_VJ(token) is a
  difference of null-adjusted advantages, **not** "the fraction of reconstruction
  lost".

---

## 8. Statistical analysis (frozen plan, D13 / D16)

- **Units.** Pool (Game J, 7 documents; 46 headline, 24 per grid cell, 20
  identifier, 20 edge) and document (Game O; 100 headline, 30 per cell). Fragment
  pairs are never treated as independent.
- **Intervals.** Percentile bootstrap, 10,000 resamples, seed 42 with a fresh
  generator per interval; 95% throughout; 90% for the frozen identifier rule.
  The t-interval is a sensitivity check only (it agrees everywhere it is
  reported; e.g. headline F1_J t-interval [0.701, 0.744]).
- **Paired comparisons** (strategy vs strategy, granularity vs granularity,
  attacker vs attacker, sentence vs token) resample the unit id once and carry
  both conditions' scores, bootstrapping the per-unit difference. Conditions are
  never resampled independently. Only units where both conditions completed
  enter a paired comparison (complete-case).
- **Spearman ρ** for associations (length, fragment count, fragment size,
  resources), bootstrapped over unit rows; when a pool appears in several cells,
  the pool id is resampled with all its rows (cluster bootstrap).
- **No multiplicity adjustment**; intervals are unadjusted and labelled so.
  Nonsignificance is never read as equivalence.
- **Identifier rule.** "Near the schema-order baseline" iff the entire 90% CI on
  A_schema lies within [−0.10, +0.10]; raw F1_J − 0.20 reported alongside.
- **Single-token experiment.** Primary: paired A_VJ(sentence) − A_VJ(token) over
  the 20 pools (oracle-size null); paired percentile bootstrap as above; **exact
  two-sided sign test** on the paired differences, zero differences treated as
  ties and omitted from the denominator (none occurred: n_selected = n_effective
  = n_nonzero = 20). Raw-vs-normalised sign disagreements per pool are reported.
- **RBNC selection-effect caveat.** A complete-case paired analysis conditions on
  the units the attacker could finish; if non-completion correlated with
  difficulty this could bias comparisons in an unknown direction. In the
  prespecified run it affects one comparison set (random / token-window, 23 of 24
  pools); in the edge experiment it did not arise (20/20).
- **Post-hoc labelling.** The results plan (§28) requires any analysis designed
  after results were seen to be labelled exploratory; the plan itself was
  committed after descriptive point results were visible but before any interval
  or test was computed (D13 disclosure).

One sentence for the paper (BOOTSTRAP_NOTE.md): "Uncertainty is quantified with
percentile-bootstrap confidence intervals (10,000 resamples) over the independent
experimental units (pools for Game J, documents for Game O); paired comparisons
resample units jointly across conditions, and t-intervals are reported as a
sensitivity check."

---

## 9. Complete results

All means with 95% percentile-bootstrap CIs over the stated units unless marked.
Sources: `results/final_analysis/TABLES/` (B, B2, C, C3, C4, C5, D, D2, E, E2, E3,
G, G2, H, I, R), `results/single_token_edge/analysis/summary.json`, the D16
`RESULTS.md`. Publication versions: `results/paper_tables/table{1..7}`.

### A. Primary: headline prose, Game J (46 pools, full length, sentence cut)

| attacker | F1_J [95% CI] | b_J | A_J [95% CI] | F1_L [95% CI] | q_micro [95% CI] | P_J / R_J | exact docs | completed |
|---|---|---|---|---|---|---|---|---|
| **One-shot Sonnet** | **0.723 [0.702, 0.743]** (median 0.713; t-CI [0.701, 0.744]) | 0.149 | 0.673 [0.649, 0.698] | 0.882 [0.861, 0.901] | 0.792 [0.772, 0.819] | 0.724 / 0.721 | 1 / 322 | 46/46 |
| Embedding (post hoc) | 0.182 [0.167, 0.198] | 0.149 | 0.039 [0.026, 0.052] | 0.364 [0.335, 0.397] | 0.500 [0.493, 0.508] | 0.126 / 0.367 | 0 / 322 | 46/46 |
| Memon-inspired | 0.168 [0.156, 0.183] | 0.149 | 0.023 [0.011, 0.035] | 0.339 [0.314, 0.368] | 0.493 [0.486, 0.504] | 0.129 / 0.265 | 0 / 322 | 46/46 |
| Analytic one-bucket | 0.149 [0.143, 0.157] | 0.149 | 0 | 0.299 [0.286, 0.313] | 0.5 (expected) | — | — | — |

Paired, same 46 pools: Sonnet − Memon-inspired F1_J 0.554 [0.529, 0.579], F1_L
0.543 [0.517, 0.566], q 0.324 [0.303, 0.346], Sonnet higher on 46/46 pools.
Sonnet − analytic F1_J 0.573 [0.551, 0.596]. Memon-inspired − analytic F1_J 0.019
[0.010, 0.029] (higher on 65% of pools). Sonnet repairs 2; credit resends 6;
answer-call output mean 52k tokens; $0.276 per pool.

### B. Full prose grid, Game J, One-shot Sonnet (pools 2–25; 24 per cell)

| cell | frags/doc | words/frag | F1_J [95% CI] | b_J | A_J [95% CI] | F1_L [95% CI] | q_micro [95% CI] | exact | Memon / Embed F1_L | Game O τ [95% CI] | completed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| random / sentence | 24.6 | 19.5 | 0.801 [0.772, 0.829] | 0.128 | 0.772 [0.739, 0.804] | 0.862 [0.837, 0.886] | 0.926 [0.905, 0.946] | 10/168 | 0.253 / 0.248 | 0.935 [0.892, 0.968] | 24/24 |
| random / clause | 30.9 | 15.5 | 0.754 [0.724, 0.784] | 0.130 | 0.718 [0.683, 0.752] | 0.835 [0.811, 0.857] | 0.899 [0.879, 0.919] | 2/168 | 0.258 / 0.246 | 0.905 [0.852, 0.945] | 24/24 |
| random / token-window | 40.3 | 11.9 | 0.634 [0.599, 0.670] | 0.132 | 0.579 [0.538, 0.619] | 0.747 [0.718, 0.775] | 0.845 [0.818, 0.870] | 0/161 | 0.262 / 0.246 | 0.909 [0.875, 0.942] | **23/24 (1 RBNC)** |
| semantic / sentence | 24.6 | 19.5 | 0.739 [0.707, 0.769] | 0.128 | 0.700 [0.665, 0.735] | 0.879 [0.851, 0.904] | 0.838 [0.820, 0.856] | 0/168 | 0.285 / 0.315 | 0.841 [0.792, 0.887] | 24/24 |
| semantic / clause | 30.9 | 15.5 | 0.679 [0.643, 0.714] | 0.130 | 0.631 [0.591, 0.671] | 0.823 [0.784, 0.858] | 0.823 [0.802, 0.844] | 0/168 | 0.256 / 0.260 | 0.791 [0.725, 0.851] | 24/24 |
| coherence-sever / clause | 22.6 | 21.3 | 0.726 [0.702, 0.749] | 0.131 | 0.684 [0.657, 0.711] | 0.849 [0.832, 0.864] | 0.851 [0.830, 0.873] | 2/168 | 0.249 / 0.274 | 0.816 [0.745, 0.874] | 24/24 |
| coherence-sever / token-window | 40.2 | 11.9 | 0.700 [0.670, 0.730] | 0.132 | 0.655 [0.620, 0.689] | 0.860 [0.829, 0.889] | 0.810 [0.790, 0.830] | 2/168 | 0.265 / 0.268 | 0.943 [0.917, 0.967] | 24/24 |
| subject-verb / sentence | 40.9 | 11.7 | 0.553 [0.527, 0.579] | 0.130 | 0.487 [0.457, 0.516] | 0.689 [0.659, 0.719] | 0.800 [0.782, 0.819] | 0/168 | 0.257 / 0.251 | 0.733 [0.666, 0.794] | 24/24 |
| subject-verb / clause | 48.5 | 9.9 | **0.498 [0.476, 0.521]** | 0.131 | 0.422 [0.397, 0.449] | 0.646 [0.621, 0.670] | 0.768 [0.746, 0.791] | 0/168 | 0.259 / 0.250 | 0.724 [0.652, 0.792] | 24/24 |

Memon-inspired F1_J on the grid: 0.126–0.142 (A_J −0.006 to +0.016); embedding
F1_J 0.125–0.158; both q ≈ 0.49–0.52.

**Strategy at fixed granularity (paired Sonnet, a − b, ΔF1_J [95% CI]; ΔF1_L; Δq):**

| granularity | a − b | ΔF1_J | ΔF1_L | Δq | pools |
|---|---|---|---|---|---|
| sentence | random − semantic | 0.062 [0.025, 0.099] | −0.017 [−0.047, 0.014] | 0.090 [0.069, 0.111] | 24 |
| sentence | random − subject-verb | 0.248 [0.216, 0.281] | 0.173 [0.145, 0.202] | 0.126 [0.106, 0.145] | 24 |
| sentence | semantic − subject-verb | 0.185 [0.164, 0.210] | 0.190 [0.166, 0.216] | 0.036 [0.022, 0.050] | 24 |
| clause | random − semantic | 0.075 [0.050, 0.102] | 0.012 [−0.016, 0.041] | 0.078 [0.065, 0.090] | 24 |
| clause | random − coherence-sever | 0.029 [0.001, 0.056] | −0.014 [−0.036, 0.008] | 0.048 [0.030, 0.065] | 24 |
| clause | random − subject-verb | 0.256 [0.230, 0.284] | 0.189 [0.169, 0.211] | 0.130 [0.111, 0.152] | 24 |
| clause | semantic − coherence-sever | −0.047 [−0.078, −0.018] | −0.026 [−0.060, 0.004] | −0.030 [−0.045, −0.017] | 24 |
| clause | semantic − subject-verb | 0.181 [0.154, 0.209] | 0.177 [0.153, 0.201] | 0.053 [0.036, 0.071] | 24 |
| clause | coherence-sever − subject-verb | 0.228 [0.200, 0.256] | 0.203 [0.180, 0.227] | 0.083 [0.064, 0.102] | 24 |
| token-window | random − coherence-sever | −0.063 [−0.093, −0.034] | −0.109 [−0.134, −0.083] | 0.033 [0.012, 0.054] | 23 |

**Granularity within strategy (coarser − finer):** random: sentence − clause 0.046
[0.021, 0.072]; sentence − token-window 0.166 [0.134, 0.198]; clause − token-window
0.117 [0.091, 0.142]. semantic: sentence − clause 0.060 [0.033, 0.088].
coherence-sever: clause − token-window 0.025 [−0.007, 0.059] (not distinguishable).
subject-verb: sentence − clause 0.055 [0.036, 0.075].

**Sonnet − Memon-inspired F1_J per cell** (paired): 0.367 [0.345, 0.389]
(subject-verb / clause) to 0.670 [0.642, 0.698] (random / sentence); Sonnet higher
on every one of the 215 paired grid pools.

**Headline vs grid reference (unpaired; table_H):** F1_J −0.016 [−0.054, 0.021]
despite 67 more fragments per pool and 181 more words per document: full-length
documents were not harder than the capped grid reference.

### C. Game O (ordering with membership given)

| condition | docs | Sonnet τ [95% CI] | median | pairs correct | exact order | mean / median displacement | Jaccard-Greedy τ [95% CI] | Jaccard-MST τ [95% CI] |
|---|---|---|---|---|---|---|---|---|
| headline (full length) | 100 | 0.769 [0.735, 0.802] | 0.810 | 0.885 | 0.01 | 3.35 / 2.17 | −0.005 [−0.032, 0.022] | 0.012 [−0.016, 0.041] |
| random / sentence | 30 | 0.935 [0.892, 0.968] | 0.984 | 0.967 | 0.47 | 0.73 / 0.43 | −0.061 [−0.109, −0.012] | −0.049 [−0.091, −0.010] |
| random / clause | 30 | 0.905 [0.852, 0.945] | 0.923 | 0.953 | 0.27 | 1.40 / 0.92 | −0.036 [−0.090, 0.018] | −0.007 [−0.064, 0.052] |
| random / token-window | 30 | 0.909 [0.875, 0.942] | 0.927 | 0.955 | 0.23 | 1.68 / 0.73 | −0.026 [−0.071, 0.019] | 0.024 [−0.015, 0.063] |
| semantic / sentence | 30 | 0.841 [0.792, 0.887] | 0.878 | 0.921 | 0.07 | 1.66 / 1.00 | −0.012 [−0.064, 0.041] | −0.016 [−0.088, 0.059] |
| semantic / clause | 30 | 0.791 [0.725, 0.851] | 0.826 | 0.895 | 0.07 | 2.75 / 1.60 | 0.009 [−0.038, 0.056] | 0.009 [−0.038, 0.059] |
| coherence-sever / clause | 30 | 0.816 [0.745, 0.874] | 0.874 | 0.908 | 0.07 | 1.88 / 1.10 | −0.055 [−0.103, −0.001] | 0.010 [−0.049, 0.073] |
| coherence-sever / token-window | 30 | 0.943 [0.917, 0.967] | 0.979 | 0.972 | 0.23 | 1.18 / 0.60 | 0.007 [−0.035, 0.048] | −0.006 [−0.042, 0.034] |
| subject-verb / sentence | 30 | 0.733 [0.666, 0.794] | 0.777 | 0.866 | 0.03 | 4.46 / 2.83 | −0.018 [−0.055, 0.020] | −0.050 [−0.108, −0.001] |
| subject-verb / clause | 30 | 0.724 [0.652, 0.792] | 0.734 | 0.862 | 0.03 | 5.37 / 3.35 | −0.041 [−0.072, −0.009] | −0.009 [−0.045, 0.027] |

Random: τ = 0 by expectation. 370 O units, 370 completed, 0 RBNC, 19 repairs.
Paired Sonnet − Jaccard floors: headline +0.774 [0.731, 0.817] (Greedy), +0.757
[0.711, 0.802] (MST); grid cells +0.733 to +0.996; Sonnet higher on 100% of
documents everywhere.

### D. Attacker comparison (headline, F1_L primary for the embedding row)

| attacker | F1_L | F1_J | q |
|---|---|---|---|
| Analytic one-bucket | 0.299 [0.286, 0.313] | 0.149 [0.143, 0.157] | 0.5 |
| Memon-inspired | 0.339 [0.314, 0.368] | 0.168 [0.156, 0.183] | 0.493 |
| Embedding (post hoc) | 0.364 [0.335, 0.397] | 0.182 [0.167, 0.198] | 0.500 |
| One-shot Sonnet | 0.882 [0.861, 0.901] | 0.723 [0.702, 0.743] | 0.792 |

Paired F1_L: embedding − Memon-inspired **0.024 [0.005, 0.044]** (higher on 32/46
pools); Sonnet − embedding **0.518 [0.487, 0.547]** (46/46); Sonnet − Memon 0.543
[0.517, 0.566]. On the grid, embedding − Memon-inspired F1_L ranged −0.016 to
+0.030: higher with the CI excluding 0 in 2 of 9 cells (semantic / sentence +0.030
[0.005, 0.057]; coherence-sever / clause +0.024 [0.013, 0.039]), lower in 5
(random / sentence, subject-verb / sentence, random / clause, subject-verb /
clause, random / token-window; each −0.006 to −0.016), indistinguishable in 2.
Embedding q is at chance in every condition (0.49–0.52). Rule for "strongest
attacker" (results plan): highest mean headline F1_J among prespecified attackers
completing ≥ 90% of pools → One-shot Sonnet; the embedding attacker is reported
alongside but is outside that rule.

### E. Structured identifiers (20 pools; Table 5)

| attacker / baseline | F1_J [95% CI] | F1_L [95% CI] | q | linkage precision [95% CI] | A_J (analytic) | A_schema [90% CI] | F1_J − 0.20 [90% CI] | verdict |
|---|---|---|---|---|---|---|---|---|
| Schema-order baseline | 0.200 | 0.200 | 1.000 | — | 0.111 | 0 | 0 | (baseline) |
| Analytic one-bucket | 0.100 | 0.200 | 0.5 | — | 0 | −0.125 | −0.100 | (baseline) |
| Random partition | 0.056 [0.055, 0.056] | 0.111 | 0.500 | 0.111 | −0.049 | −0.181 [−0.181, −0.180] | −0.144 | not near: below |
| Memon-inspired | 0.054 [0.042, 0.066] | 0.125 [0.109, 0.142] | 0.426 | 0.111 [0.096, 0.128] | −0.051 | −0.182 [−0.195, −0.169] | −0.146 [−0.156, −0.135] | not near: below |
| Embedding (post hoc) | 0.054 [0.043, 0.065] | 0.109 [0.100, 0.120] | 0.492 | 0.073 [0.068, 0.079] | −0.051 | −0.183 [−0.195, −0.171] | −0.146 [−0.156, −0.137] | not near: below |
| **One-shot Sonnet** | **0.083 [0.068, 0.099]** | 0.132 [0.113, 0.154] | 0.631 | 0.132 [0.113, 0.154] | −0.019 | **−0.146 [−0.162, −0.129]** | −0.117 [−0.130, −0.104] | **not near: entire 90% CI below −0.10** |

Field-type grouping behaviour: Sonnet's 140 groups each held exactly one name, one
SSN, one account and one address (template-perfect; that is why its q = 0.63 is a
template diagnostic, not reconstruction); the share of its within-group pairs that
truly share a record is 0.132 [0.113, 0.154] against 1/7 = 0.143 for
template-respecting random assignment ("consistent with template chance", E3,
exploratory). Memon-inspired, embedding and random are below template chance. The
embedding hypothesis (cluster by field type) is consistent with its F1_L 0.109 <
0.20 but was not separately tested. Interpretation: **on this corpus no attacker
recovered record membership beyond what the schema gives for free; every attacker
scored below the trivial schema-order baseline.** Error taxonomy: 140 records, 0
exact, 139 merged / 139 split — total cross-record mixing inside template-correct
groups. Cost $0.93; 0 repairs; 0 RBNC; 20/20.

### F. Resource behaviour (Table 7; table_R; Fig. 8)

- Prespecified one-shot units 652 (282 J + 370 O); completed 651; **RBNC 1**
  (grid random / token-window pool_002, 322 fragments, 128,000 output tokens,
  visible JSON cut off after 250 of 322 labels; rank 23 of 24 by size in its
  cell). Largest completed prespecified J unit: 537 fragments (headline).
- Post-hoc edge run: 40 units, 40 completed (token arm 438–669 fragments); 3
  *repair* calls exhausted 128k and the units kept their earlier answers.
- Provider refusals for credit: 48 (6 headline, 42 grid), resent once, all
  answered. Repairs: 51 prespecified (2 headline J, 30 grid J, 0 identifier, 3
  headline O, 16 grid O) + 11 in the token arm (8 fixed).
- Spearman ρ(fragments, answer-call output tokens): J 0.739 [0.683, 0.787] (n =
  282); O 0.786 [0.737, 0.827] (n = 370). ρ(prompt chars, output) J 0.296. Cost
  per completed J pool: headline $0.276, grid $0.419 (subject-verb / clause $0.66,
  semantic / sentence $0.20), identifier $0.047; O $0.019–0.051 per document.
- Tokens: 3.89M input, 23.1M output in the final run; output is ≥96.7% internal
  reasoning.
- **Why fragment count is not a hard ceiling:** the non-completion was not the
  largest unit (322 vs 537 completed, and 669 in the token arm); output scales
  with how long the model reasons about a pool, which correlates with size but is
  not determined by it (the same 141-fragment size took 31k on one pool and 68k
  on another in development).
- Cost: final run $119.37; project ledger $144.32 (pool-1 screening $9.75,
  hierarchical live sample $0.50, G3 $0.55, single-token $14.15).

### G. POST-HOC EXPLORATORY: MPNet embedding attacker (D14)

All numbers are in A, B, D and E above. Summary: headline F1_L 0.364 [0.335,
0.397] (vs Memon 0.339, Sonnet 0.882); grid F1_L 0.246–0.315; identifier F1_L
0.109; q 0.49–0.52 everywhere; F1_J headline 0.182, grid 0.125–0.158, identifier
0.054. Paired F1_L vs Memon-inspired: headline +0.024 [0.005, 0.044]; grid +0.030
and +0.024 (2 cells, CI > 0), −0.006 to −0.016 (5 cells, CI < 0), 2
indistinguishable. Paired vs Sonnet: headline −0.518 [−0.547, −0.487]; grid
−0.395 to −0.614. One fragment truncated at 386 word pieces. Runtime ~90 min CPU.

### H. POST-HOC EXPLORATORY: single-token edge case (D16)

Design: 20 pools / 140 documents; sentence vs single-token; identical
four-sentence excerpts; one-shot Sonnet; completion **20/20 in both arms**; cost
$14.15 (sentence $0.57, 20 rows; token $13.58, 31 rows = 20 base + 11 repairs);
malformed first answers 11, all in the token arm: 8 repaired, 3 repair calls hit
128k (units keep the earlier answer); 0 in the sentence arm. Fragments: sentence 28
per pool; token median 523 (438–669).

**One-shot Sonnet (means; paired sentence − token [95% CI]; sign test):**

| metric | sentence | token | paired diff | median | pools s > t | p |
|---|---|---|---|---|---|---|
| **A_VJ (primary, oracle-size null)** | **0.588** | **0.016** | **0.572 [0.539, 0.607]** | 0.563 | **20/20** | **1.9 × 10⁻⁶** |
| raw V_J | 0.762 | 0.155 | 0.607 [0.586, 0.628] | 0.601 | 20/20 | 1.9 × 10⁻⁶ |
| oracle-size null V_J (mean) | 0.423 | 0.141 | — | — | — | — |
| A_VL | 0.777 | 0.159 | 0.618 [0.552, 0.695] | 0.581 | 20/20 | 1.9 × 10⁻⁶ |
| raw V_L | 0.889 | 0.427 | 0.462 [0.425, 0.508] | 0.437 | 20/20 | 1.9 × 10⁻⁶ |
| oracle-size null V_L (mean) | 0.503 | 0.317 | — | — | — | — |
| A_VJ, predicted-structure null (robustness) | 0.592 | 0.027 | 0.565 [0.532, 0.599] | 0.558 | 20/20 | 1.9 × 10⁻⁶ |
| F1_J (id-level) | 0.585 | 0.116 | 0.469 [0.437, 0.501] | 0.477 | 20/20 | 1.9 × 10⁻⁶ |
| F1_L (id-level) | 0.761 | 0.223 | 0.538 [0.482, 0.595] | 0.544 | 20/20 | 1.9 × 10⁻⁶ |
| A_J (id-level) | 0.539 | −0.016 | 0.555 [0.520, 0.590] | 0.560 | 20/20 | 1.9 × 10⁻⁶ |

Per-pool effect range (A_VJ difference): 0.413 to 0.722. Token-arm A_VJ per pool:
−0.119 to 0.053 (positive in 18/20, all small); sentence-arm A_VJ 0.414–0.730.
Token-arm A_VL positive in 19/20 pools (−0.369 to 0.389). q_V (diagnostic only):
0.860 vs 0.376. Raw-vs-normalised sign agreement: no disagreement for Sonnet
(V_J and A_VJ differences have the same sign in all 20 pools); Memon-inspired
disagrees in pool_017, pool_032, pool_041 (all three reported). Id-level scorer
detail (`results/final/singleTokenEdgeJ/REPORT.txt`): the finalised token-arm
answers had exactly 7 groups in 14/20 pools (mean 24.5 groups per pool, i.e.
several answers returned more groups than the 7 asked), with 100% of fragments
placed and no policy fill; exact records 0/140 vs 23/140 in the sentence arm.

**Memon-inspired and MPNet (not designed for isolated tokens; NOT security
evidence):** A_VJ sentence 0.043 → token −0.067 (Memon; diff 0.110 [0.047,
0.178], 17/20, p 0.0026) and 0.104 → −0.090 (MPNet; diff 0.194 [0.155, 0.233],
20/20). Both were near or below their nulls in the token arm.

**Descriptive cross-check (common metric only):** excerpt sentence-arm F1_J 0.585
vs full-document headline F1_J 0.723. Different tasks; not a comparison of
conditions.

**In English.** With sentences as the atoms, the attacker recovered about 59% of
the gap between a random shuffle and perfect visible reconstruction. With single
words as the atoms, on exactly the same text, it recovered about 2% of that gap:
its raw score (0.155) was almost what randomly dealing the words into seven
piles of the right sizes scores (0.141). It could still tell, imperfectly, which
words came from the same excerpt (A_VL 0.159, positive in 19 of 20 pools), so
some source-linkage signal survives even when joint reconstruction has collapsed.
**This does not locate a threshold**: two points were tested, not a curve.

---

## 10. Publication figures

`results/paper_figures/` — Figs. 1–8 (PDF / SVG / PNG / CSV each), the script
`make_figures.py`, and `README.md` with draft captions and the demonstrandum of
each figure. Design: Okabe–Ito palette with distinct markers (grayscale-safe);
filled = prespecified, open = post-hoc exploratory; 0–1 axes for every bounded
metric; no grids; conditions ordered by strategy then granularity; 95% CIs where
frozen; nothing connected into a granularity curve. See §19 for placement.

| fig | file | shows |
|---|---|---|
| 1 | fig1_headline_attackers | dot + 95% CI, F1_L and F1_J, four attackers, pool points behind |
| 2 | fig2_grid_reconstruction | 9 cells + headline: Sonnet F1_J with CI, Memon / embedding / baseline markers; panel (b) A_J |
| 3 | fig3_linkage_vs_ordering | F1_L and q side by side, same rows |
| 4 | fig4_gameO_vs_gameJ | O (1 + τ)/2 vs J F1_J and q per condition |
| 5 | fig5_identifiers | F1_L, F1_J, linkage precision vs analytic / schema / 1/7 lines; prose reference |
| 6 | fig6_single_token_edge | paired A_VJ slope chart; paired-difference estimation plot; raw V_J vs null; A_VL |
| 7 | fig7_landscape | A_J for grid, headline, identifiers, excerpt arms; not connected |
| 8 | fig8_resource_scaling | fragments vs output tokens, RBNC ringed, 128k line, token arm open |

---

## 11. Publication tables

`results/paper_tables/` — `table1_design`, `table2_headline_attackers`,
`table3_grid`, `table4_gameO`, `table5_identifiers`, `table6_single_token`,
`table7_resources`, each `.md` and `.tex` (booktabs; compiled together without
error), built by `make_tables.py` from the frozen CSVs. Footnotes carry the
post-hoc labels, the RBNC rule and the paired comparisons. Tables 3 and 5 are
wide; in the paper, drop the Memon / embedding column from Table 3 (it is in Fig.
2–3) and the raw-difference column from Table 5 if width is short.

---

## 12. Claim–evidence matrix

### A. Directly supported claims (safe wording → evidence → caveats)

1. **"In every tested prose condition, a one-shot LLM attacker given all
   fragments of seven documents recovered most source membership and most
   order."** Headline F1_J 0.723 [0.702, 0.743] (b 0.149), F1_L 0.882, q 0.792;
   grid F1_J 0.498–0.801, all CIs far above b ≈ 0.13; smallest A_J 0.422 [0.397,
   0.449]. *Caveats:* one model, 7-document closed-world pools, complete
   fragment availability, English clinical case reports.
2. **"Reconstruction was a strong partial reconstruction, not verbatim
   recovery."** Exact documents 1/322 headline, 16/1505 grid; error taxonomy
   dominated by local order errors inside mostly-correct groups.
3. **"The one-shot LLM attacker greatly outperformed the tested classical,
   statistical and embedding attackers."** Paired Sonnet − Memon-inspired F1_J
   +0.554 [0.529, 0.579] headline, +0.367 to +0.670 per cell, higher on 261/261
   paired pools; Sonnet − embedding F1_L +0.518 [0.487, 0.547]; Sonnet − Jaccard
   floors τ +0.73 to +1.00 in Game O. *Caveat:* "tested" attackers; do not
   generalise to all non-LLM methods.
4. **"The classical and statistical attackers performed at their floors."**
   Jaccard orderers τ ≈ 0 (CIs include 0 in most cells); Memon-inspired A_J ≤
   0.023, q ≈ 0.5. *Caveat:* never call them state of the art or faithful Memon.
5. **"Boundary strategy changed reconstructability at fixed granularity;
   subject-verb cutting was the most resistant of the tested prose conditions at
   both granularities, though still far above baseline."** Paired ΔF1_J vs every
   other strategy 0.18–0.26 at sentence and clause, CIs exclude 0; subject-verb /
   clause F1_J 0.498, A_J 0.422.
6. **"Within three of four strategies, finer cuts were associated with modestly
   lower reconstruction."** random 0.046 / 0.166 / 0.117; semantic 0.060;
   subject-verb 0.055 (CIs exclude 0); coherence-sever 0.025 [−0.007, 0.059]
   (not distinguishable). *Caveat:* granularity is confounded with fragment count
   and size; no causal attribution to the boundary rule.
7. **"Strategy effects acted on linkage and on ordering in strategy-specific
   ways."** semantic − subject-verb (sentence): ΔF1_L 0.190 [0.166, 0.216] but Δq
   0.036; random − semantic (sentence): ΔF1_L −0.017 [−0.047, 0.014], Δq 0.090
   [0.069, 0.111]. Game O confirms ordering given membership is high everywhere
   (τ 0.72–0.94).
8. **"Structured identifiers behaved qualitatively differently from prose: the
   record template was visible, record association was not recovered, and every
   attacker fell below a trivial schema-order baseline."** Sonnet F1_J 0.083
   [0.068, 0.099] < 0.10 < 0.20; A_schema 90% CI [−0.162, −0.129]; template-perfect
   groups; linkage precision 0.132 [0.113, 0.154] vs 1/7. *Caveats:* synthetic
   records; one schema; not "identifiers are protected".
9. **"On the tested identifier corpus, fragmentation substantially limited joint
   source-linkage and ordering reconstruction under the evaluated attackers."**
   (The frozen narrow wording, D11 / CLAIM_EVIDENCE.)
10. **"Fragment count, fragment size and (for ordering) document length were
    associated with reconstruction."** ρ(fragments, F1_J) pooled grid −0.695
    [−0.745, −0.641], negative in 9/9 cells (CI excludes 0 in 5); ρ(fragment
    words, F1_J) 0.654 [0.590, 0.716]; ρ(document words, q) −0.451 [−0.695, −0.155]
    on the headline; ρ(words, τ) −0.351 in O; ρ(words, F1_J) −0.129 [−0.404,
    0.162] (no clear association with overall J). *Caveat:* associations only.
11. **"Resource limits rarely bound the one-shot attacker at this scale."** 1
    RBNC in 652 units; the RBNC was not the largest unit.
12. **POST-HOC EXPLORATORY: "On identical four-sentence excerpts from
    seven-document pools, single-token fragmentation reduced the one-shot
    attacker's null-adjusted visible joint reconstruction to near its
    random-shuffle reference, relative to sentence fragmentation."** A_VJ 0.588 →
    0.016; diff 0.572 [0.539, 0.607]; 20/20; p 1.9e-6; robust to the
    predicted-structure null (0.565 [0.532, 0.599]). *Caveats:* exploratory, four
    sentences not full documents, one attacker, binary.
13. **POST-HOC EXPLORATORY: "Some token-level source-linkage signal remained
    despite near-chance joint reconstruction."** A_VL 0.159, positive in 19/20;
    raw V_L 0.427 vs null 0.317.
14. **POST-HOC EXPLORATORY: "Sentence embeddings recovered slightly more linkage
    than lexical TF-IDF grouping on the headline and remained far below the LLM."**
    +0.024 [0.005, 0.044]; on the grid higher in 2/9 cells and lower in 5/9.
15. **"Synthetic prose can invert the lexical signal an attack depends on."**
    TF-IDF Cohen's d −0.077 (synthetic) vs +0.458 (real) — a methods finding.

### B. Defensible interpretations (say how strongly)

1. *"The generative attacker exploited information beyond pairwise semantic
   similarity."* **Moderate.** Evidence: the similarity-based attackers (TF-IDF,
   MPNet) with the same clustering reach F1_L 0.34–0.36 while the LLM reaches
   0.88 on the same pools. This is an inference from the attacker contrast, not a
   mechanism measurement; phrase as "consistent with" and note the embedding arm
   is exploratory and used one model and one clustering rule.
2. *"Semantic redundancy in narrative prose makes it especially reconstructable."*
   **Weak–moderate.** Supported by the prose/identifier contrast and by the LLM
   reading content under masking (G3), but "redundancy" was not manipulated;
   subject-verb's effect and the token experiment change search complexity as
   well as context. Phrase as a plausible explanation.
3. *"Fine atomization can substantially reduce exploitable joint structure under
   the tested attacker."* **Moderate, exploratory.** From the token experiment
   alone, on excerpts; say "in a controlled post-hoc experiment".
4. *"Linkage and ordering are distinct failure modes."* **Strong** (it is a
   property of the metric and it is observed: strategies move F1_L and q
   differently; token cut collapses V_J while V_L survives).
5. *"Fragmentation should be viewed as data-dependent compromise containment
   rather than a universal confidentiality primitive."* **Moderate**, as a
   framing conclusion of the whole pattern; not a measured quantity.
6. *"Ordering given membership is largely recoverable for prose."* **Strong**
   (Game O τ 0.72–0.94, exact-order rate up to 0.47).
7. *"Full-length documents were not harder than 30-sentence documents for joint
   reconstruction."* **Moderate** (unpaired headline vs grid reference, F1_J
   −0.016 [−0.054, 0.021]; different documents).

### C. Hypotheses / future work only (not established here)

- *Global shuffling over thousands of documents would further reduce
  reconstruction.* Untested; pool size was fixed at 7; the direction is
  plausible for joint reconstruction but the linkage signal's persistence (F1_L
  0.88) is a reason not to assume it.
- *Partial compromise would improve protection.* Untested; every fragment was
  always available.
- *High-entropy secrets (keys, seed phrases) are more resistant than prose.*
  Untested; the identifier result is for a four-field Faker schema.
- *There is a granularity threshold.* Two granularities were tested on excerpts;
  no curve.
- *Increasing fragment count monotonically lowers reconstruction.* An
  association (ρ −0.695) within a confounded design; coherence-sever / token-window
  (282 fragments/pool) reconstructed better than subject-verb / sentence (287).
- *Specialised token-level attackers could recover more than Sonnet did.* None was
  run; the token arm used an unchanged sentence-era prompt.
- *Embedding similarity clusters identifiers by field type.* Stated as a
  hypothesis in D14; consistent with F1_L 0.109 but not separately tested.
- *Other models behave like Sonnet.* One model.
- *The hierarchical (decomposed) attacker completes what one-shot cannot.* Dropped
  unrun; development sample only.

### D. Claims you must not make

- "Fragmentation is secure" / "prevents reconstruction" (prose: it does not;
  identifiers: only "substantially limited under the evaluated attackers on a
  synthetic corpus").
- "Single-word fragmentation defeats LLMs" (exploratory; one attacker; excerpts;
  linkage signal survived).
- "There is a threshold below N words" (binary design).
- "Semantic context is the proven causal mechanism" (context and combinatorial
  complexity change together; not isolated).
- "All embeddings fail" / "embeddings cannot link fragments" (one model, one
  clustering rule, post hoc; it did beat TF-IDF on the headline).
- "All LLMs behave like Sonnet" / any statement about model families.
- "Identifiers are protected in real breaches" (synthetic; closed world; complete
  availability; one schema).
- "SCRMBL is proven secure" or any product security claim (§16).
- "Global shuffling guarantees safety" (untested).
- Generalisation from the four-sentence token experiment to full documents,
  other corpora, other pool sizes or adaptive attackers.
- Generalisation to partial-compromise or distributed deployments.
- "Memon" / "faithful Memon" / "pre-LLM state of the art" for any attacker.
- "The hierarchical attacker …" as a result (not run).
- "Untouched headline pools" (21 documents had prior development contact).
- Causal effects of fragment count, size or length.
- Equivalence from a non-significant difference.

---

## 13. What the results mean in English

- **F1_L = 0.882.** Given ~240 shuffled sentences from seven case reports, the
  model's guesses about which sentences belong to the same patient were right
  about 88% of the time by pair-F1: most pairs it grouped together really were
  from the same report, and it found most of the pairs that exist. Nearly all
  membership was recovered.
- **Why analytic F1_L = 0.299 is not "30% reconstructed".** Saying "everything is
  one document" gets every true pair (recall 100%) and about six false pairs for
  every true one (precision ~18%); the F1 of that is 0.30. It contains zero
  information. The number to read is the distance above it.
- **Why embeddings scored only modestly above baseline.** Sentence embeddings
  measure topical similarity. Sentences from the same case report share a topic
  but so do sentences from *different* case reports about similar conditions,
  and adjacent clinical sentences often share no content word at all (that is
  what broke the coherence-sever rule). Similarity alone produces clusters that
  are partly by topic, not by source: F1_L 0.36 vs 0.34 for TF-IDF.
- **Why Sonnet is different.** It appears to use continuity: one patient's age
  and sex, the drug started three sentences ago, "the lesion" that needs an
  antecedent, the plausible clinical sequence. The study measures that it does
  this (masked ids, shuffled order, no side channel), not how; the mechanism
  claim is an inference (§12B).
- **What subject-verb fragmentation appears to disrupt.** Cutting "The patient |
  was admitted with chest pain" leaves a subject phrase without its predicate and
  a predicate without its subject. Linkage fell most (F1_L 0.646–0.689 vs 0.82–0.88
  for other strategies) while ordering fell less: the pieces are harder to
  assign to a patient, not just harder to sequence. It also doubles the fragment
  count, so the two are confounded.
- **What happened with identifiers.** The model could see what each fragment
  *is* (an SSN looks like an SSN) and built 140 perfect templates. It could not
  tell *whose* SSN goes with whose name: its pairings were right about 1 time in
  7, which is what guessing within the template gives. Because the trivial
  "one bucket in schema order" strategy scores 0.20 and the model scored 0.083,
  the model did *worse* than the trivial baseline on the joint metric. Read: the
  schema leaks; the association did not, on this synthetic corpus.
- **What happened at single-token granularity.** Same text, cut into words. The
  model's reconstruction of the excerpts was about what you would get by
  shuffling the words into piles of the right size. But it still grouped words
  by source better than chance (A_VL 0.16): "hemodialysis", "biopsy",
  "left-ventricular" still point at the excerpt they came from.
- **"Near the random-shuffle baseline" means:** for each pool we simulated
  10,000 random answers that know only the true document sizes; the model's
  visible score in the token arm was barely above their average (0.155 vs
  0.141; about 2% of the way from random to perfect).
- **Why surviving linkage matters.** Linkage is the privacy-relevant half for
  identifier-like content: knowing that two fragments share a source is a
  breach even without order. A defence that destroys ordering but leaves
  membership recoverable has removed the less sensitive secret. Fig. 6(d) and
  the prose F1_L numbers are the reason the paper should not describe token
  fragmentation as "defeating" reconstruction.

---

## 14. Main paper story

**Candidate A (attacker-first; recommended).**
1. Similarity-based methods (classical Jaccard, statistical TF-IDF/character
   models, sentence embeddings) underestimate reconstruction risk: they sit at
   the floor. 2. A strong generative LLM reconstructs most membership and order
   of fragmented clinical prose in every ordinary fragmentation condition. 3.
   Reconstruction varies materially with strategy and granularity; subject-verb
   disruption is strongest; strategy effects split between linkage and ordering.
   4. Structured identifiers behave differently: the schema is visible, record
   association is not recovered, every attacker is below a trivial baseline. 5.
   A post-hoc controlled boundary experiment shows extreme single-token
   atomization drives joint LLM reconstruction to its random-shuffle reference on
   excerpts while a linkage signal survives. 6. Therefore resistance is
   data-type-, granularity-, attacker- and budget-dependent, not binary.
   *Supported by the data:* yes, point for point (§12A 3–4, 1–2, 5–7, 8–9,
   12–13). Keep point 5 explicitly exploratory and keep the hierarchical attacker
   out.

**Candidate B (data-type-first).** Lead with the prose/identifier contrast as the
pre-registered hypothesis (paper_section3 §3.7), then the strategy grid as
"how much does the cut matter for prose", then attackers, then the boundary
experiment. Faithful to the original hypothesis and strong for a privacy
venue; risk: the attacker-strength result, which is the most novel evidence,
arrives late.

**Candidate C (threat-model / measurement-first).** Lead with the games and
metrics (J vs O, F1_J = F1_L × q, baselines, RBNC) as a methodological
contribution, then present results as a map. Good for reviewers who ask "what
is the security definition"; risk: reads as a methods paper.

**Recommendation:** A, with B's pre-registered hypothesis stated in the
introduction and C's measurement apparatus in Methods. The one adjustment to
the user's draft narrative: phrase point 1 as "the tested similarity-based
attackers" (not "classical methods" in general) and point 5 as "in a controlled
post-hoc experiment on excerpts".

---

## 15. Limitations (reviewer-facing; what each threatens / does not)

| limitation | threatens | does not invalidate |
|---|---|---|
| Closed-world, N = 7 known, one pool at a time | external validity to large stores, unknown source counts; absolute leakage numbers | the attacker contrast; the prose/identifier contrast; the strategy ranking (all within the same setting) |
| Complete fragment availability in J | generalisation to partial compromise | the existence and size of content-based linkage signal |
| No deployment-level distributed / partial-compromise evaluation | any statement about a deployed system | anything in the paper (it makes none) |
| Single corpus and domain (PMC case reports), English | generality across genres, languages, writing styles | the within-corpus comparisons |
| One strong generative model (claude-sonnet-5), one prompt, default reasoning | "LLMs in general"; the absolute level | the qualitative gap to similarity attackers (a lower bound on what generative attackers can do) |
| One embedding pipeline, post hoc, no fine-tuning, one clustering rule | "embeddings cannot do this"; exploratory status | the descriptive finding that this widely used model did not close the gap |
| Memon-inspired, not faithful Memon | comparison to the literature's method | its role as a statistical floor with a directional orderer |
| No specialised / adaptive token-level attacker; unchanged prompt in the token arm | the strength of the single-token result as a security statement | the paired within-pool difference under the frozen attacker |
| Synthetic identifiers (Faker; four fields; two duplicate names) | external validity to real records with correlated structure, free text, reused values | the closed-world guarantee that any link is intrinsic; the template-visibility finding |
| Post-hoc embedding experiment | confirmatory status | its inclusion as clearly labelled exploratory evidence |
| Post-hoc single-token experiment, 20 pools, four-sentence excerpts | generalisation to full documents, other corpora, pool sizes; confirmatory status | the paired effect on these excerpts (20/20; CI far from 0; robust to the alternative null) |
| Binary edge test | any threshold claim | the existence of a regime where joint reconstruction collapses |
| Semantic context and combinatorial search complexity change together (token arm; subject-verb) | mechanism attribution | the operational effect of the cut |
| Prior development contact in 21 headline documents (18 pools; 9 documents in the token experiment) | "untouched" wording; a purist's confirmatory status | the estimates (no strategy or prompt was tuned on those documents' performance; contact informed operations) |
| Resource-budget dependence (128k, one attempt) | the RBNC rate and cost figures under other budgets | scores on completed units; one RBNC in 652 units makes the completion caveat small |
| Repair / finalisation behaviour (one structural round; singletons for unplaced ids) | comparability to attackers with unlimited retries | the disclosed, counted, truth-free repair (51 + 11 repairs; policy share 0) |
| Grid documents capped at 30 reference sentences | full-length grid claims | the headline (full length) and the headline-vs-grid check (−0.016) |
| Cells dropped after pool-1 screening (development-informed) | the grid's preregistered status for those two cells | the nine retained cells (pools 2–25 are post-selection data) |
| Real published papers for prose | the closed world is a harness assumption | post-cutoff removes memorisation, not lookup; state the assumption |
| Possible future threat models (global shuffle, partial compromise, unknown N) | none of the paper's claims, which are scoped to Game J / O | — |

---

## 16. Implications for SCRMBL (not claims of this paper)

Kept separate from the Results and Discussion; product reasoning, stated
cautiously.

- **Do not rely on fragmentation as the sole confidentiality control for prose.**
  Under complete access to a small pool, a one-shot LLM recovered most of the
  membership and order of clinical narratives in every tested cutting rule,
  including the most disruptive one. Encryption (and post-quantum encryption for
  long-lived data) remains the primary control; fragmentation is at most a
  second layer.
- **Fragmentation may function as compromise containment.** What it buys is
  data-dependent: for the identifier-like records tested, joint reconstruction
  fell below trivial baselines; for prose it did not. The system-level value is
  then in limiting *how much* a partial compromise exposes, which this study did
  not measure.
- **Long-lived structured identifiers and secrets are the natural HNDL case.**
  Harvest-now-decrypt-later risk is highest for data whose value persists; the
  identifier result is encouraging but is for a synthetic four-field schema. The
  study **does not** establish resistance for cryptographic keys, seed phrases,
  card data, or live production PII, all of which have their own structure
  (checksums, formats, reuse, adjacency to free text).
- **The high prose F1_L is a warning about shuffling alone.** Content-based
  linkability was recovered with ids masked and order shuffled. A global
  dispersal design cannot assume that shuffling destroys linkability; it must be
  tested at the intended population size and compromise fraction.
- **Global dispersal / partial compromise is a future SCRMBL-specific system
  experiment** (§17). Nothing here is evidence about SCRMBL's architecture,
  hardware, ordering secret, or storage layout, and the paper deliberately makes
  no such claim.

---

## 17. Future experiments (do not run; list only)

- A global pool of thousands to tens of thousands of fragments from many sources,
  unknown source count, scoring linkage precision / recall as a function of pool
  size.
- Partial record availability: simulated storage-node compromise rates; linkage
  precision / recall versus compromise fraction; whether partially represented
  records are still linkable.
- Specialised and adaptive token-level attackers (frequency models, language-model
  scoring, multi-pass reconstruction) against the single-token arm.
- High-entropy secrets: keys, seed phrases, hashes; financial credentials with
  checksums; real-format PII (with governance).
- Other domains and languages; non-clinical prose; mixed records (prose with
  embedded identifiers) to test the identifier-density hypothesis.
- A controlled granularity dose–response (several cuts of identical text) if a
  threshold question is ever to be answered.
- Additional generative models and prompts; larger reasoning budgets to test the
  RBNC-as-budget claim.
- A decomposed / hierarchical attacker at scale (the dropped design exists).
- An actual SCRMBL end-to-end system evaluation, separate from this paper.

---

## 18. Prespecified vs post-hoc inventory

| analysis / attacker / experiment | prespecified? | development-informed? | post-hoc exploratory? | recommendation |
|---|---|---|---|---|
| Headline J, one-shot Sonnet, 46 pools | yes (D2, D11, D12) | pool composition fixed before any attack; 21 docs had prior dev contact (operations only) | no | main |
| Grid J, 9 cells, pools 2–25 | yes (D5 froze the reduced grid before pool 2) | yes: the 9 cells were retained after pool-1 screening; two cells dropped; coherence-sever re-cut (D7) | no | main (full table appendix) |
| Headline O (100 docs) and grid O (30 × 9) | yes (D11, D12) | sampling rules from the budget script | no | main (condensed) / appendix (full) |
| Game O floors: Jaccard-Greedy, Jaccard-MST, Random | yes (D1 corrected before primary runs) | D1 fix chosen from a leak audit, not scores | no | appendix table; one line in main |
| Memon-inspired J, n = d = 2 | yes (D12; setting frozen from development evidence) | n chosen on a development cell (ordering at chance for all n) | no | main |
| SHA-256 fix and rerun of Memon-inspired | correctness fix before analysis (D13) | — | no | appendix (reproducibility report) |
| Identifier J, 20 pools, ±0.10 rule, schema-order baseline | yes (D11, frozen before scoring) | no | no; the linkage-precision diagnostic (E3) is exploratory | main |
| Analytic baselines; A_J | yes (metrics fixed in code before runs) | — | no | main |
| Bootstrap / paired / Spearman plan | fixed before any interval (D13); the results plan was committed after descriptive means were seen | — | no (disclosed) | methods |
| Relationships (length, count, size) | in the results plan | — | associations, not causal | appendix |
| Error taxonomy, examples | results plan §19 | — | exploratory / descriptive | appendix |
| Resource / completion analysis | results plan §17–18; D6 | — | no | appendix |
| Hierarchical attacker | designed (D7–D11) | k from blocker coverage | **not run; dropped (D17)** | omit; one sentence in limitations / future work |
| Embedding attacker (MPNet) | no | no | **yes (D14)**, frozen before evaluation, first result kept | main tables / figures, marked |
| Single-token edge experiment | no | no | **yes (D16)**, frozen before launch, analysis committed before results | main figure + table, marked; claim scope frozen |
| Naturally-short corpus search; D15 excerpt design | no | — | investigated / built, never run | omit (mention in the design narrative if space) |
| Pool-1 screening slice; llm-cut development cells; G3 masking control; hierarchical live sample | development | yes | — | appendix / audit only; G3 belongs in Methods as the side-channel check |
| 28 never-touched headline pools robustness check | optional (development history) | — | not run | omit or mention as available |

---

## 19. Figure / table placement recommendation

**Main text** (in this order, answering the research questions):
- Fig. 1 — headline attacker comparison (RQ: how strong is the LLM vs the rest).
- Fig. 2 — grid reconstruction (RQ: does strategy / granularity matter).
- Fig. 3 — linkage vs ordering decomposition (RQ: which half fails).
- Fig. 5 — identifiers (RQ: data-type dependence).
- Fig. 6 — single-token edge case (RQ: what happens at the boundary; post hoc).
- Optional sixth: Fig. 7 (landscape) if the Discussion needs one picture; else
  Fig. 4 (O vs J) if reviewers are likely to ask about the oracle reference.
- Tables in main: Table 2 (headline attackers), Table 5 (identifiers), a condensed
  Table 3 (F1_J, A_J, F1_L, q, completion per cell), Table 6 (single-token).
  Table 1 (design) in Methods.

**Appendix:** Table 4 (full Game O incl. floors) and Fig. 4; the full Table 3 with
Memon / embedding columns and the paired strategy / granularity tables (C3, C4,
C5); Table 7 and Fig. 8 (resources, completion, cost, batches); relationships
(table_R; the analysis package's Figs. 6–8); per-pool single-token data (the
figure CSV / per_pool.csv), the scorer validation (29 tests) and null benchmark;
the error taxonomy (I, I2); the SHA-256 reproducibility report; the G3 masking
control; the D1 orderer correction; pool-1 screening and dropped cells; the
synthetic-corpus inversion finding; the corpus fidelity checks; the
development-contact inventory; the budget / ledger record.

Rationale: main figures answer the questions in §1; audit, resource and
per-unit detail moves to the appendix, as security measurement papers usually
do; every post-hoc item stays labelled wherever it appears.

---

## 20. Final sanity audit

Cross-checks performed while building this packet (each number in §9 was read
from the named artifact; the figure and table scripts read the same files):

- Table B / C / D / E CSVs ↔ RESULTS_SUMMARY.md: consistent (the summary is
  generated from them).
- summary.json ↔ RESULTS.md (single-token): consistent; per_pool.csv means
  reproduce the summary means; per-pool effect range 0.413–0.722 computed from
  per_pool.csv.
- Figure CSVs are the plotted values by construction (the script writes what it
  plots); `make_figures.py` and `make_tables.py` run from a clean checkout with no
  arguments; all seven `.tex` tables compile in one document.
- Completion counts: 46/46, 215/216 (1 RBNC), 20/20, 100/100, 270/270; token
  experiment 20/20 + 20/20; total 652 + 40 units. Ledger $144.32 = $130.18 +
  $14.15 (rounding). Table G's final-run total $119.37 + pool-1 $9.75 + hier
  sample $0.50 + G3 $0.55 = $130.17 ≈ $130.18 (ledger rounding).
- Post-hoc labels verified on: the embedding rows in Tables 2, 3, 5, 6 and Figs.
  1, 2, 3, 5, 7, 8; the whole of Table 6 and Fig. 6; the excerpt arms in Fig. 7.
- Units verified: pools (J), documents (O), pools (edge); Spearman clusters as in
  table_R.

**Inconsistencies found in the record (flagged, not silently resolved):**

1. **Hierarchical wording.** `results/final_analysis/RESULTS_SUMMARY.md`, Table F,
   `HIERARCHICAL.csv`, `table_A_design` and `CLAIM_EVIDENCE.md` say "pending";
   D17 says dropped / not run. The analysis package's `write_reports.py` and
   `analyze.py` have not been re-run since D17. This packet, the paper tables
   and figures use "not run (dropped)". Fix the package's wording before it is
   cited, or cite D17.
2. **"Untouched" wording.** `RESULTS_SUMMARY.md` ("46 untouched headline pools"),
   the headline manifest and D2 use "untouched"; D16 rules it out. Use "headline
   pools (fixed before any attack; 21 documents in 18 pools had documented
   development contact)".
3. **Embedding status line.** `RESULTS_SUMMARY.md`'s "Pending" section still says
   the embedding adversary was "designed, not run" while its tables contain the
   run; D14 addendum 3 is the authority (run, kept).
4. **`table_A_design`** lists the headline attackers as "…; Hierarchical
   (pending)" and omits the embedding attacker; Table 1 here supersedes it.
5. **Analysis-package figure numbering vs paper figures.** The package's Figs. 1–10
   (PGFPlots) and this packet's Figs. 1–8 (matplotlib) are different sets; cite
   `results/paper_figures/` for the paper.
6. **RESEARCH_BRIEF.md** describes an earlier plan (12 cells, k = 25 token windows,
   Kimi / gpt-oss cutter, 5 repeats, 120-document grid). It is superseded by
   RUN_DECISIONS; do not cite its design numbers. The final token window is 12
   whitespace words.
7. **Grid document length.** Grid J documents are capped at 30 reference
   sentences (mean 478 words) while the headline is full length (659); the
   analysis package states this in table_H but the results summary's cell table
   does not repeat it. State it in Methods.
8. **Table F "RBNC rescue" line** says "no headline one-shot RBNC occurred (0 of
   46)": correct, and consistent with the single RBNC being a grid pool.
9. **The embedding − Memon F1_J headline difference** is 0.013 [0.003, 0.023]
   (RESULTS_SUMMARY) while F1_L is 0.024 [0.005, 0.044]; both correct; the paper
   should quote F1_L (its primary comparison), not F1_J.
10. **Sign-test p** is reported as "0.0000" in RESULTS.md's tables and as 1.9e-06
    in summary.json / D16; use 1.9 × 10⁻⁶.
11. **No disagreement** was found between the frozen TABLES and the numbers the
    user listed in the packet prompt (0.588 / 0.016 / 0.572 [0.539, 0.607] /
    20/20 / 1.9e-6 / 0.762 vs 0.155 / 0.423 vs 0.141 / 0.889 vs 0.427 / 0.503 vs
    0.317 / 0.777 vs 0.159 / 0.585 vs 0.116 / 0.761 vs 0.223 / 0.539 vs −0.016;
    analytic 0.299 / Memon 0.339 / embedding 0.364 / Sonnet 0.882).

### Remaining issues before drafting

1. Re-run `results/final_analysis/scripts/write_reports.py` (and fix `analyze.py`'s
   Table F / `table_A_design` text) so the analysis package says "not run
   (dropped)" and includes the embedding attacker in Table A; otherwise every
   citation of the package must carry a D17 note. $0, no results change.
2. Decide the wording of the development-contact disclosure for the 46 headline
   pools and the 20 edge pools (this packet's suggested sentence is in §2.4) and
   whether to report the optional 28-never-touched-pool robustness check
   (not run; would be a re-scoring, $0, of existing answers restricted to those
   pools — an analysis, not a new experiment; it would need a dated decision entry).
3. Confirm the model identifier string and reasoning setting to print in the
   paper ("claude-sonnet-5, Message Batches API, default adaptive reasoning,
   no temperature parameter") against the provider's documentation at
   submission time; the manifests record only the model id and `max_tokens`.
4. Confirm the citation for the Memon context-model idea against the source
   before using "inspired by Shanmugasundaram & Memon" (adversaries.md wording
   rule).
5. Table 3 and Table 5 exceed a single column; choose which columns to drop for
   the main text (suggested in §11).
6. The corpus's English-only status is a consequence of the PubMed / PMC
   pipeline, not an explicit filter; say so rather than "filtered to English".
