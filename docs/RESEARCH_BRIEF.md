# Research brief — fragmentation prose arm

Self-contained handoff. Everything below is either **[MEASURED]** (observed in a
real run), **[DERIVED]** (computed from measurements via a stated model), or
**[OPEN]** (unresolved). Do not treat derived figures as measurements.

---

## 1. Project

A privacy paper targeting **PoPETs**. Thesis: fragmenting a document into pieces
and scattering them does not protect it, because an LLM adversary can reassemble
and re-link the pieces.

Two adversary games, both scored against ground truth:

- **Game O (ordering)** — given the shuffled fragments of ONE document, restore
  their original order. Scored by Kendall's τ, one τ per document.
- **Game L (linkage)** — given a pool of fragments from MANY documents with IDs
  masked, partition them back into per-document groups. Scored by pairwise F1,
  one F1 per pool.

Defense side: a grid of **cut strategies × granularities** — where the defender
slices, and how big the pieces are.

| | sentence | clause | token-window (k=25) |
|---|---|---|---|
| random | run | run | run |
| semantic | run | run | run |
| coherence-sever | run | run | run |
| subject-verb | run | run | skip (degenerate — collapses to random) |
| llm-cut | — 1 cell, model picks its own granularity — | | |

= 12 prose cells. Identifiers corpus gets no strategy sweep (atomic fields, every
cell identical).

Strategies: **random** = arbitrary offsets, the no-strategy floor (not built
yet). **semantic** = clean self-contained units, current default. **coherence-
sever** = cut at discourse links (pronoun-antecedent, "however"/"therefore",
topic shifts), targeting the exact signal the LLM uses — best shot at dropping τ.
**subject-verb** = cut between subject and predicate via spaCy, deterministic.
**llm-cut** = hand it to a model told to cut for maximum unlinkability.

---

## 2. Corpus — `data/prose_v4/` [MEASURED]

500 real clinical case narratives pulled from PMC Open Access, **published
February 2026 or later** — after the model's January 2026 training cutoff. This
is the paper's strongest novelty claim: a high score cannot be memorization, so
it is a genuine reconstruction result rather than a possible recall result.
Licence-filtered to commercial-use-permitted (all `CC BY-NC*` variants rejected).

| | |
|---|---|
| Documents | 500 |
| Total sentences | 16,524 |
| Total characters | 2,222,587 |
| Length: min / p25 / median / p75 / p90 / p95 / max | 5 / 21 / 28 / 40 / 56 / 71 / 287 |
| Measured clause ratio (spaCy) | 1.81 clauses per sentence |
| Measured tokens per sentence | 19.4 (308,532 tok / 15,914 sents) |

Length bands:

| band (sentences) | docs | fragments | mean k |
|---|---|---|---|
| 5–15 | 48 | 564 | 11.8 |
| 16–30 | 245 | 5,650 | 23.1 |
| 31–60 | 171 | 7,189 | 42.0 |
| 61–300 | 36 | 3,121 | 86.7 |

Files: `prose_documents.jsonl`, `prose_fragments.jsonl`, `prose_answer_key.jsonl`,
`prose_meta.jsonl`.

---

## 3. Prior finding — the Memon baseline is degenerate [MEASURED]

Documented in `README.md`. The harness's Memon grouping collapses nearly
everything into one cluster and pads the count with singletons:

| corpus | largest cluster | Memon F1 | trivial "one big cluster" F1 |
|---|---|---|---|
| synthetic prose (25 rec) | 53/104 (51%) | 0.0459 | **0.0615** |
| prose_v2 (96 rec) | 1039/1148 (91%) | 0.0190 | 0.0189 |
| prose_v3 (500 rec) | 5401/5936 (91%) | 0.0037 | 0.0037 |

It **loses to doing nothing** on synthetic and **exactly equals it** on real
corpora. Cause: `greedy_grouping` is single-linkage, chaining through a
similarity matrix that is 83.5% exact zeros. `mst_grouping` fails identically.

The synthetic corpus additionally has an **inverted lexical signal** — same-record
sentence pairs are *less* similar than different-record pairs (tfidf-cosine
Cohen's d = −0.077 synthetic vs +0.458 real), because every synthetic note opens
with the same template. No similarity tuning can fix a signal pointing the wrong
way.

**Fix, validated:** TF-IDF cosine + average linkage + deterministic tie-break
jitter. prose_v3 F1 0.0037 → 0.0222 (6× trivial); identifiers stay at chance
(0.0171 vs 2σ random ceiling 0.0297), so the two-regime thesis is safe.

**Not yet applied to `harness/orderers.py`.** It moves a baseline the group has
already seen and shrinks the reported LLM-vs-Memon gap. Michael and Arafat must
be told before it appears in a draft.

---

## 4. Calibration [MEASURED, single observation — treat as provisional]

From `calibration_small.json` / `calibration_small_raw.txt`, model
`claude-sonnet-5`, 1 document (28 frags) for Game O, 10-doc pool (280 frags) for
Game L:

| | estimate | actual | factor |
|---|---|---|---|
| Game O input | 1,111 | 1,674 | 1.506 |
| Game O output | 420 | 830 | 1.976 |
| Game L input | 9,552 | 15,054 | 1.576 |
| Game L output | 840 | 25,923 | **30.86** |

Game L quality at that pool size: **precision 0.7302, recall 0.7024, F1 0.716**,
11 groups returned vs 10 expected, 280/280 labels, 0 invalid, 0 duplicates.
Random floor 0.0967; trivial one-cluster 0.1765.

Caveats:
- `"valid_permutation": false, "returned": 1` in the JSON is an artifact of
  `--skip-ordering` (`calibrate_small.py:146` hardcodes 1674/830 from an earlier
  real call). **Not a bug.** But it means the Game O factors were not re-measured
  in that run.
- The 30.86 output factor came from ONE call whose thinking ran to 25,210 tokens.

### Reasoning sweep [MEASURED] — `reasoning_sweep.json`

Same 280-fragment pool, three thinking settings:

| setting | out tokens | thinking | wall s | F1 | result |
|---|---|---|---|---|---|
| baseline (adaptive, default effort) | 25,923 | — | 251 | **0.716** | parsed |
| `thinking: disabled` | 1,749 | 598 | 16 | **0.347** | parsed, but 279/280 labels, 1 dup, 2 missing |
| adaptive + `effort: low` | 26,153 | 25,210 | 243 | — | **parse error** (`Extra data: line 14 col 1`) |
| adaptive + `effort: medium` | 32,000 | 32,000 | 338 | — | **hit max_tokens, ZERO answer tokens** |

Two of three configured runs failed to produce usable output. Cost of the sweep:
$0.69.

---

## 5. Critical correction to the original cost model [DERIVED]

`corpus_sizing.py` computes linkage output as `n_frags × 3 × 30.861`, i.e. it
extrapolates the measured thinking rate linearly with fragment count.

The measured rate is **25,210 thinking tokens / 280 fragments = 90 tokens per
fragment**. Linear extrapolation implies >32,000 output tokens for any call above
**~355 fragments** — which the API cannot emit. The `medium` sweep run already
hit `max_tokens` at exactly 32,000 on that very pool.

**Thinking saturates at the output cap; it does not scale linearly with corpus
size.** The correct bound is `pools × max_tokens`. This changed the headline
estimate for the full grid from **$439 to ~$14 per cell**. Any estimate using the
30.861 multiplier at pool sizes above ~355 fragments is pricing tokens the model
is structurally unable to produce.

`budget_plan.py --ceiling 32000` implements the bound. It is a true ceiling: the
bill cannot land above it.

---

## 6. API facts [MEASURED — from vendor docs, verified 2026-08]

- **Model: `claude-sonnet-5`.** List price **$3 / $15** per MTok. **Introductory
  $2 / $10 expires 2026-08-31.** `corpus_sizing.py` hardcodes the intro rate.
- **Message Batches API: flat 50% off input and output.** This workload
  qualifies — offline, thousands of independent calls, no latency requirement.
  Most batches finish within an hour, max 24. Results return in arbitrary order,
  keyed by `custom_id`.
- **`budget_tokens` is REMOVED on Sonnet 5 — returns 400.** There is no thinking
  budget parameter. The only controls are `output_config.effort`
  (`low`/`medium`/`high`/`xhigh`/`max`, default `high`) and `max_tokens`, which
  is a hard cap on **thinking + answer text combined**. This is why the `medium`
  run produced 32,000 thinking tokens and zero answer.
- **`temperature`, `top_p`, `top_k` are rejected (400).** There is no temperature
  to set. Repeats measure run-to-run variance under default sampling plus
  adaptive-thinking nondeterminism — the paper must not claim "we varied
  temperature."
- **Prompt caching: rejected for this workload.** Discounts input only; input is
  27% of this bill (1.92M in vs 1.02M out per headline run, but output is priced
  5×). Best case at ×5 repeats saves 18%; batch saves 50% including output. They
  do not compose — caching needs call-timing control the batch scheduler does not
  give, and a cache *miss* costs 1.25× (all-miss = 107% of plain). Minimum
  cacheable prefix is 1024 tokens; the mean document is ~1,100, so short
  documents silently never cache.
- Sonnet 5 uses a new tokenizer (~30% more tokens than Sonnet 4.6). The measured
  CAL_IN ≈ 1.54 factor already absorbs this empirically.

---

## 7. Cost model — `corpus_sizing.py` / `budget_plan.py` [DERIVED]

```
o_in  = (chars + n_frags*11)/4 + 150*n_docs      # Game O input
o_out = n_frags * 15                              # Game O output (permutation labels)
l_in  = (chars + n_frags*11)/4 + 200*pools        # Game L input
l_out = pools * max_tokens                        # Game L output — CEILING
```
Calibration multipliers: input ×1.541, Game O output ×1.976.
Granularity scaling: clause = sentence × 1.81; token-window = sentence × 19.4 / k.

Statistical model (Game O): under the null, Kendall τ on a k-fragment document
has Var(τ) = 2(2k+5) / (9k(k−1)). Corpus-mean SE = sd_doc / √n_docs. MDE at 80%
power / α .05 = 2.8 × SE × √2 unpaired; paired across the same documents divides
by √2 assuming cell-to-cell correlation ρ=0.5 (**assumption, not measured**).

---

## 8. Proposed plan [DERIVED]

Two tiers. Headline at full corpus size; defense sweep on a subset, with one
shared cell bridging them.

**Tier 1 — headline.** semantic × sentence, all 500 documents, **full length, no
truncation**, ×5 repeats, thinking on. 15,914 fragments. **$35.00** batched at
intro pricing ($7.00/run). 95% CI half-width on corpus-mean τ = ±0.012.

**Tier 2 — grid.** All 12 cells, one run each, thinking off, on **120 documents
sampled systematically** (every 4th by length — NOT stratified). 3,600 fragments.
**$15.31.** Paired MDE 0.037.

semantic × sentence runs in **both** tiers. That shared cell is the only thing
licensing comparison of grid cells back to the headline corpus.

Free, local, all 12 cells: random baseline + **fixed** Memon.

`k=25` for token-window is chosen to match measured mean sentence length (19.4
tokens), making it a size-matched control for sentence — not chosen for cost.

**Why systematic, not stratified:** stratification forces 40 documents from the
5–15 band, and short documents have higher per-document τ variance (Var ∝ 1/k),
so it *costs* precision (MDE 0.042 vs 0.037) to buy length coverage that is no
longer wanted. Systematic also preserves the corpus length distribution — mean
fragments/document 30.0 vs Tier 1's 31.8 (stratified: 28.2) — making Tier 2 a
scale model of Tier 1 and keeping Game L pools statistically equivalent.

| | Tier 1 | grid | subtotal | +25% contingency |
|---|---|---|---|---|
| ×5 repeats | $35.00 | $15.31 | $52.31 | **~$65** |
| ×3 repeats | $21.00 | $15.31 | $38.31 | **~$48** |

Worst case (every linkage call billed at the full cap, no contingency): $57.45.

**Keep Tier 1 at full length.** Truncating to 30 sentences saves only $4.57
across all five runs and changes the headline claim from "real clinical records"
to "30-sentence excerpts" — an ecological-validity objection a privacy reviewer
will raise. Independent of whether length analysis is wanted.

---

## 9. Open questions [OPEN — resolve before or during the run]

1. **Pool size for Game L.** The unit of analysis is the pool. Pool size must be
   identical across all 12 cells AND both tiers, or linkage rows are not
   comparable. Trade-off:

   | docs/pool | T1 pools | T2 pools | frags/pool |
   |---|---|---|---|
   | 10 | 50 | 12 | 318 |
   | 20 | 25 | 6 | 637 |
   | 30 | 17 | 4 | 936 |
   | 60 | 9 | 2 | 1,768 |

   Larger pools = harder linkage, fewer independent observations, higher risk of
   unparseable output. Only 280 fragments/pool has ever been tested (F1 0.716).
   **4 pools in Tier 2 is thin for a mean.** 20 docs/pool gives 6 pools and 637
   frags/pool — closer to what was calibrated. Resolve empirically.

2. **Game L statistical power is unanalyzed.** Every MDE figure in this brief is
   Game O only. There is no equivalent power analysis for linkage, where the
   observation count is pool count (not document count). Tier 2 carries a ~2×
   SE penalty on linkage regardless of pool size (√(500/120) = 2.04). Needs
   doing.

3. **Does thinking-off preserve strategy RANKING?** The exploratory tier runs
   thinking-off, scoring F1 0.347 vs 0.716 — roughly half quality. The grid only
   needs relative movement between strategies, but nobody has verified that a
   half-quality adversary ranks strategies the same way a full-quality one does.
   **If it does not, all 11 exploratory cells are noise.** Test: run two cut
   strategies both ways on one pool, confirm ordering agrees.

4. **Malformed partition handling.** Thinking-off produced 279/280 labels, 1
   duplicate, 2 missing. Needs a documented repair or drop-and-penalize rule
   applied identically across cells before scoring.

5. **ρ (cell-to-cell correlation) is assumed 0.5.** All paired MDE figures depend
   on it. Measurable once two cells exist.

6. **The `random` cut strategy does not exist yet.** Needs building.

---

## 10. Risks that invalidate results (not just cost money)

1. **Fragment-ID leakage.** IDs are `prose_0000_frag_000`, encoding both record
   and position. The harness masks them before Game L; anything run outside the
   harness must too. Unmasked, **both games are trivially leaked and every number
   is void.** Verify on every code path before spending.
2. **Pool size drifting between cells or tiers** — silently breaks linkage
   comparability, because pool size sets the random floor.
3. **Zero-answer calls billed silently.** One call already burned 32,000 tokens
   producing no text. Flag `stop_reason == "max_tokens"` with no parseable answer.
4. **Reporting the harness Memon as "prior work"** — it scores exactly the trivial
   solution, so it would inflate the LLM-vs-baseline gap with a broken comparator.

---

## 11. Constraints and preferences (from the project owner)

- Undergraduate, self-funded. Original $400+ estimate was not viable. Target is
  the strongest publishable result for minimum spend.
- **500 documents for the headline is wanted** — a previous 25-document corpus
  read as too thin for PoPETs. This is about reviewer perception of n, and it is
  affordable, so it stays.
- **Length analysis is NOT wanted.** Do not spend anything to preserve length as
  an analyzable variable. (Full-length Tier 1 is retained for ecological
  validity of the headline claim, which is a separate reason.)
- **No cross-model arm.** Decided against; single-model design is final. Handle
  the limitation in the writeup: scope claims to "a frontier LLM" (never "LLMs"),
  name the model and version in the abstract, lean on the random → Memon → LLM
  adversary axis for what generality can be shown, and put multi-model
  replication in future work with budget named as the reason.
- The 12-cell grid stays. A 7-cell screening design (all strategies at sentence +
  semantic at the other two granularities) was considered and rejected.
- Deadlines: intro pricing ends **2026-08-31**; batch API must be used.

---

## 12. Files

| file | what |
|---|---|
| `corpus_sizing.py` / `.json` | original one-tier sizing sweep; source of the cost model |
| `budget_plan.py` / `.json` | two-tier planner; `--ceiling`, `--batch`, `--list-price` |
| `RUN_PLAN.md` | the execution plan and pre-flight checklist |
| `calibrate_small.py`, `calibration_small.json/.txt` | the single calibration call |
| `bench_reasoning.py`, `reasoning_sweep.json` | the three-setting thinking sweep |
| `bench_linkage.py`, `memon_linkage.py` | Memon degeneracy analysis and the fix |
| `pull_prose_v4.py` | corpus builder |
| `run_baselines.py` | random + Memon baselines, imports real harness scorers |
| `analyze_length.py`, `timing.py`, `estimate_cost.py`, `cost_grid.py` | earlier analyses |
