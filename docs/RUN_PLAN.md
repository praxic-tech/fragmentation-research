# Run plan — reconstruction-resistance experiment

Costing from [`cost_model_v2.py`](../analysis/cost_model_v2.py), which is built on
**measured** API calls rather than a fitted curve. Total **$149.82** against a
$200 budget, leaving ~$50 of headroom.

Design follows the threat model document (§3.x references below), with the
divergences noted in *Open items*.

---

## 1. Settings — fixed before anything runs

| Setting | Value | Why |
|---|---|---|
| Model | `claude-sonnet-5` | Calibrated. Pin the exact ID in the paper. |
| Submission | Message Batches API | 50% off input and output. |
| Deadline | Submission **2026-11-30** (internal freeze 11-19) | Sonnet 5 introductory pricing is now permanent — the old 2026-08-31 pricing wall no longer exists and must not be quoted. |
| Sampling | API default | `temperature` / `top_p` / `top_k` are **rejected** on this model. Do not claim temperature 0 — you cannot set it. |
| Effort | Default | `low` returned an invalid ordering in testing; upward is unmeasured. |
| Documents per pool | **7, everywhere** | Sets the linkage floor. Never varies — headline, every grid cell, every baseline. |
| `max_tokens` | 32,000 ordering / 48,000 linkage | A cap, not a reservation. Costs nothing unless emitted. |
| Token-window size | **k = 12** | Below the 19.4-token mean sentence, so token-window is the *finest* cut, per the design. |
| Grid truncation | First **30 fragments** per document | Cost control. Every cell sees identical documents, so the contrast is unaffected. |

**Not used:** reduced-effort modes (three of four configurations tested failed to
produce usable output) and prompt caching (saves ~$0.30, adds failure modes,
and batch gives no timing control).

### Nesting — build once, never rebuild

```
all 500 documents  =  71 pools of 7   -> headline, both games
   25 of those pools = 175 docs       -> linkage grid
      180 documents                    -> ordering grid (superset of the 175)
```

Write the pool partition and both subset selections to disk and load that file
in every run. If pools get rebuilt between cells, the same documents stop
co-occurring and every linkage comparison silently becomes meaningless. Release
the partition with the paper.

### How comparisons work

| Comparison | Runs on | Reference is | Matched by |
|---|---|---|---|
| Headline | 500 docs / 71 pools | random floor, trivial, `B_stat` | — |
| Ordering grid, 11 cells | same 180 docs, capped 30 | the capped reference cell | document |
| Linkage grid, 6 cells | same 25 pools, capped 30 | the capped reference cell | pool |
| Truncation effect | 180 docs | same 180 docs at full length, **free** from the headline | document |

**Because the grid documents are truncated, the reference cell cannot be scored
out of the headline** — the headline's documents were not capped, so it is a
different task. The reference is its own run. That is one extra cell per game,
and it buys something: filtering the headline to those same 180 documents at
full length is free, so *reference-at-full-length vs reference-at-cap-30*
measures the effect of truncation itself on identical documents. The reviewer's
question gets a number rather than a paragraph.

Capping also lowers the linkage floor slightly (truncating long documents
compresses group sizes toward equal), which is a second reason the reference
must be run on capped pools.

---

## 2. What was measured

All figures below are real API calls, `claude-sonnet-5`, default effort.
Diagnostics cost **$1.26** in total.

**Ordering output tokens**

| fragments | output | note |
|---|---|---|
| 13 | 323 | valid permutation |
| 22 | 579 | valid |
| 31 | **4,444** and **2,437** | same document, two runs — **1.82× apart** |
| 76 | 24,001 | valid |

Not a power law. Roughly linear at ~26 tokens/fragment below ~22 fragments, then
reasoning switches on and it goes superlinear (log-log slope 1.88 above 31). An
earlier single-exponent fit overstated the cheap end by 3–4×.

**Linkage output tokens** — the two configurations in this plan are direct
anchors, not extrapolations.

| pool | fragments | groups | output | parse |
|---|---|---|---|---|
| 5 docs, full | 179 | 5 | 8,958 | 5/5 groups, 179/179 labels, 0 dups |
| **7 docs, cap 30** | 132 | 7 | 14,144 | 7/7, 132/132, 0 dups ← **grid** |
| **7 docs, full** | 178 | 7 | 21,234 | 7/7, 178/178, 0 dups ← **headline** |
| 10 docs, full | 418 | 10 | >32,000 | **failed** |
| 10 docs, full | 460 | 10 | >48,000 | **failed** |

Group count drives cost harder than fragment count: 179 fragments across 5
groups cost 8,958 tokens, while 178 fragments across 7 groups cost 21,234.

**Input estimator** is sound — measured 1,853 tokens against 2,029 predicted for
one document, 16,078 against 16,956 for a pool. 5–9% conservative.

**Other findings:** `effort: low` returned an invalid ordering (968 tokens,
label list did not match the fragments). An ordering call at `max_tokens=4,000`
hit the cap with zero answer tokens — all reasoning, no output.

---

## 3. Order of work

### Step 1 — Prove the masking works. $0.53

Fragment IDs are `prose_0000_frag_000` — they encode both the source document
and the position. Add a check that refuses to send any prompt matching that
pattern, and log that it ran on every call. Re-label fragments randomly **per
call**, keeping the mapping outside the prompt.

Then demonstrate it: run 2 pools with IDs **deliberately unmasked**. Those
should score near-perfect; your masked pools should not. That gap is evidence
for the paper.

**If both come back near-perfect, stop.** You have a leak and nothing else is
worth running.

Also feed the openings of 100 documents and ask for continuations. They should
fail. §3.3 denies the adversary auxiliary context, and for prose *ordering* the
closed-world property rests on post-cutoff publication — this probe is the
empirical version of that argument, and it covers preprint exposure and silent
model updates that a publication-date argument does not.

### Step 2 — Headline. $21.30

**Ordering, all 500 documents, full length, semantic × sentence.** $13.09
**Linkage, all 71 pools, full length, same cut.** $8.21

One pass per document. You do **not** need repeats here: §3.5's contribution is
the (η, γ) frontier, a distribution over *documents*, and 500 documents gives
you 500 independent observations. Report the ECDF plus specific thresholds
("Pr[τ ≥ 0.9] = …"), not just a mean.

Report the per-document spread (2.5th–97.5th percentile) **and** the confidence
interval on the mean separately — they differ by more than an order of magnitude
and mean different things.

### Step 3 — Stop and look. $0

Three things fall out of Step 2 before you spend the rest:

1. **The frontier.** The distribution is the result. Length enters here as a
   *covariate* — plot τ against document length and say whether the frontier is
   homogeneous or a mixture. This is why there is no length-analysis arm: length
   is not an axis in §3.7's pre-registered hypothesis, and the headline already
   contains the full range at maximum n per band (48 / 245 / 171 / 36 documents
   in the 5–15 / 16–30 / 31–60 / 61–100 fragment bands).
2. **The per-pool floors.** Compute the trivial "one pile" score for each pool
   from its actual group sizes — it is *not* a constant. Report the margin over
   each pool's own floor, and report the worst pool.
3. **Whether the grid is worth running as designed.** If the per-document spread
   is large, plan the grid as a ranked table with intervals rather than
   significance claims.

### Step 4 — Ordering grid. $60.61

Twelve cells, all on the same 180 documents truncated to 30 fragments.

| # | Cut | Granularity | Cost |
|---|---|---|---|
| 1 | semantic | sentence | $1.85 ← **reference cell** |
| 2 | random | sentence | $1.85 |
| 3 | coherence-sever | sentence | $1.85 |
| 4 | subject-verb | sentence | $1.85 |
| 5 | random | clause | $7.75 |
| 6 | semantic | clause | $7.75 |
| 7 | coherence-sever | clause | $7.75 |
| 8 | subject-verb | clause | $7.75 |
| 9 | random | token-window 12 | $6.18 |
| 10 | semantic | token-window 12 | $6.18 |
| 11 | coherence-sever | token-window 12 | $6.18 |
| 12 | llm-cut | model's own | $3.65 |

Subject-verb has no token-window cell — cutting between subject and verb inside
a fixed span is not distinguishable from cutting randomly.

The clause row is $31 of the $60.61. Capping at 30 *sentences* yields ~54
*clause* fragments, which lands past the reasoning regime change. That is
inherent to the granularity axis, not a modelling artifact.

### Step 5 — Linkage grid. $15.37

Seven cells, all on the same 25 pools, documents capped at 30.

| Cut | Granularity | Cost |
|---|---|---|
| semantic | sentence | $1.95 ← **reference cell** |
| random | sentence | $1.95 |
| coherence-sever | sentence | $1.95 |
| subject-verb | sentence | $1.95 |
| llm-cut | model's own | $1.95 |
| semantic | clause | $2.79 |
| semantic | token-window 12 | $2.83 |

Fewer cells than the ordering grid because a linkage observation is a *pool* and
an ordering observation is a *document* — per independent measurement, linkage
costs roughly 25× more. Better to have 25 pools on 7 cells than 12 pools on 12.

### Step 6 — Identifiers. $1.19

Separate corpus, separate finding, **linkage only**. This is where the attack
should fail — atomic fields carry no narrative thread — and that contrast with
prose is the two-regime result in §3.1.

No strategy sweep. One configuration compared across every adversary rung.
Ordering does not apply: a name, an account number and an address have no
natural order.

Assumes the identifier corpus scales from 50 to 500 records. At 4 fields per
record that is 2,000 fragments in 71 pools — cheap, because identifier fields
average ~14 characters.

**The synthetic-guarantee argument in §3.7 still holds here** and only here: no
Faker-generated SSN corresponds to a real person, so no external source exists
to corroborate against, closed-world by construction.

### Step 7 — Repeats. $7.60

Two extra runs of the reference cell (180 documents, 25 pools). Three runs total
gives a bound on run-to-run variation.

You are not putting bands on everything. You need one number you can cite:
*"repeat runs of the reference condition varied by at most X; differences below
X are not interpreted."* Without it, every grid comparison is uninterpretable —
measured run-to-run variance on a single document was **1.82×**.

Methods sentence: *all adversary queries used the model's default sampling
configuration; sampling parameters are not configurable on this model.*
Variation between runs comes from the model's own nondeterminism, including
adaptive reasoning landing differently.

---

## 4. Baselines — free, local, run on everything

No API cost. Report all of these alongside every linkage cell:

- **Random floor** — random partition. ~1/7 at seven documents per pool.
- **Trivial** — everything in one group. **Compute per pool** from actual group
  sizes; it is not a constant.
- **`B_stat` — fixed Memon** (TF-IDF cosine + average linkage + deterministic
  tie-break jitter), from [`memon_linkage.py`](../adversaries/memon_linkage.py) with
  `variant="fixed"`.
- **Embedding clustering** — recommended addition. Embed fragments, cluster.
  Non-LLM, free, and it closes the obvious reviewer question: *did you need a
  language model, or would sentence embeddings have done it?*

**One requirement left on `B_stat`:**

1. **Run it on the identical pool partition the LLM sees** — same 7-document
   pools, same fragments, same masking. The validated fixed-Memon figure of
   0.0222 is from a **500-way** linkage with a floor near 1/500; your pools are
   7-way with a floor of 0.287. Those are different tasks and subtracting one
   from the other gives an advantage figure that is mostly an artifact of pool
   size.

~~2. Do not route through `harness.eval_memon`.~~ **DONE (2026-08-10).**
The degenerate groupings are off the live path entirely.
[`harness.eval_memon`](../harness/harness.py:170) takes `method` for the Game O
**ordering** heuristic only (`greedy` / `mst`); Game L grouping is always the
fixed `B_stat` (TF-IDF cosine + average linkage). There is one grouping
algorithm, so both Memon rows report the same Game L figures and differ only in
ordering τ — which is the truth about what greedy and MST actually are.

`greedy_grouping` / `mst_grouping` are no longer imported by the harness.
`--grouping legacy-greedy|legacy-mst` reproduces pre-fix tables for audit, and
is the only way to reach them.

The degeneracy finding still earns an appendix — the published implementation
collapses to the trivial solution on real corpora and loses to doing nothing on
synthetic — but it is a methodological contribution, not a live threat to the
headline metric.

---

## 5. Two free measurements

**Track position displacement alongside τ.** τ sits near 0.97, against the
ceiling, so a strategy that halves the model's errors might move it by 0.015 and
look like nothing. Mean absolute distance from correct position has room to
move. Same outputs, scored a second way.

**Report the smallest difference the grid could have detected.** Otherwise a flat
cell reads as "this strategy does nothing" when what you measured was "any
effect is below our resolution."

---

## 6. Budget

| Step | Cost |
|---|---|
| 1. Controls | $0.53 |
| 2. Headline, both games | $21.72 |
| 4. Ordering grid, 12 cells | $60.61 |
| 5. Linkage grid, 7 cells | $15.37 |
| 6. Identifiers | $1.19 |
| 7. Repeats | $7.60 |
| **Base** | **$107.01** |
| Buffer 40% | $42.81 |
| **Total** | **$149.82** |

*Regenerated 2026-08-10 against the promoted corpus. Two changes from the
$138.58 figure this document previously carried: the headline is $0.42 dearer
because the corpus is now the full uncapped cut (16,524 fragments, up from
16,267 — the old build truncated 5 documents at 100 fragments), and the buffer
in `cost_model_v2.py` is 40%, not the 30% quoted here. The model is the source
of truth; re-run it rather than trusting this table.*

**The clause row is probably overpriced.** Its $7.75/cell assumes clause yields
~1.8× the fragments of sentence. Measured on the promoted corpus with the shared
spaCy base, the real ratio is **1.31×**. `analysis/cost_grid.py` still carries
the 1.81× assumption and should be re-measured before the clause row is used to
justify a cut.

**On the buffer.** Random run-to-run variance *averages out* across 500
documents — the total is far more stable than any single call. What does not
average out is systematic error in interpolating between four measured anchor
points. 30% covers that.

**Headroom under $200: ~$50.**

Wire a spend meter before the experiment. Check after Step 2 and after every
four grid cells. If projected spend crosses $170, cut in this order: repeats
($7.60), then the clause row of the ordering grid ($31), then the two
granularity cells from the linkage grid ($5.62).

---

## 7. Optional, against the $61 headroom

| | cost | what it buys |
|---|---|---|
| Embedding-clustering baseline | **$0** | Closes "did you need an LLM". Do this regardless. |
| Signal ablations — 3 cells | ~$11 | Strip discourse markers / shuffle words within fragments / mask named entities. §3.1 claims ordering rides on *linguistic* signal and linkage needs *database* signal. Removing one signal and showing the predicted differential effect turns that hypothesis into a demonstrated mechanism. Best value here. |
| Greedy-adjacency ordering | ~$15 | Specified in §3.7, never built. Pairwise "does A follow B", assembled greedily. Structurally different attack; may beat direct-reorder on long documents where direct-reorder degrades. |
| Capability rung: `max` effort | ~$4 | Untested upward. If it does not beat default, that is a publishable sentence about probing the ceiling. |
| Capability rung: `claude-opus-5` | ~$10 | **Cost curve is Sonnet-derived and unvalidated for Opus** — could be 2–3× that. Calibrate first. |
| Code execution over `S` | ~free | §3.3 denies *auxiliary context*, not *computation*. The sandbox has no network, so it complies. Needed for parity: `B_stat` is statistical computation over `S`, so denying the LLM the same tool tilts the comparison toward the baseline. |

If two: **embedding baseline** (defensive, free) and **the ablations**
(offensive — they are what make §3.1 a finding rather than an observation).

---

## 8. Open items — decide before building

1. **§3.7 is stale.** It states the corpus is "wholly synthetic" and that this
   *guarantees* the closed-world property. Synthetic prose was dropped (inverted
   lexical signal: same-record pairs are *less* similar than different-record
   pairs, TF-IDF cosine Cohen's d −0.077 synthetic vs +0.458 real). The
   closed-world argument now needs three separate justifications:
   - *identifier linkage* — guaranteed by construction, no real referent exists
   - *prose ordering* — guaranteed by post-cutoff publication
   - *prose linkage* — guaranteed by the **harness** denying web access. These
     are real published papers; an adversary with a search engine could look up
     which sentences co-occur. Post-cutoff does not help here. This is an
     assumption enforced by the setup, not a property of the data, and should be
     stated as such.
2. **σ / g naming drift.** §3.7 specifies σ ∈ {random, semantic-boundary,
   entity-aware} and g ∈ {sentence, sub-sentence, paragraph} — 3 × 3. The
   working grid is 5 strategies × 3 granularities with *token-window* instead of
   *paragraph*. Decide which is canonical before writing cutters.
3. **`Adv` definition (§3.4).** Sound now that `B_stat` is fixed, but the
   baseline must be recomputed at 7-document pools (see §4).
4. **Mixed-EHR arm.** §3.7 lists it as a third content class and the
   pre-registered hypothesis makes a dose-response claim about identifier
   density. Not in this plan or this budget. If its prose is Faker-templated it
   inherits the inverted-signal problem; if it is real prose with synthetic
   identifiers injected it is the cleanest test of the density hypothesis.
   Decide, or move to future work explicitly.
5. **Fine-tuned reorderer** (§3.7, "optional") — out of budget. Say so rather
   than leaving it implied as untested.
6. **The inverted-signal finding deserves its own subsection**, paired with the
   Memon degeneracy: evaluating fragmentation defenses on synthetic corpora can
   invert the signal the attack depends on, so prior results on synthetic data
   may have systematically misestimated linkage difficulty.

---

## 9. Still to build

*Struck items landed 2026-08-10 — see `docs/deliverables/week5_grid_build/`.*

- `random` cut strategy
- ~~`coherence-sever` cut strategy~~ — built, but **calibrate before use**: on
  short documents the topic-shift test fires at nearly every boundary and the
  cell collapses onto `semantic`. Run
  `datagen/coherence_sever.py --report-boundaries` and check the cut share.
- ~~token-window cutting at k = 12~~ — built; k=12 is now the default and
  measures 11.7 words/fragment.
- ~~llm-cut defender pass~~ — built (`datagen/llm_cutter.py`), sampled on 20
  documents for $0.0956. **Run with `--thinking off`**: adaptive thinking burns
  the whole output cap and returns an empty answer. See
  [`llm_cut_profile.md`](llm_cut_profile.md) — the model never cuts mid-clause
  and leaves 6× more dangling links exposed than token-window, and its cut rate
  varies 0.26–1.00 across documents, so the cell is a mixture rather than one
  condition.
- Pool partition: 500 documents into 71 fixed pools of 7, written to disk, never
  regenerated. Plus the 25-pool and 180-document selections, fixed once.
- ID masker: fresh random labels per call, mapping held outside the prompt, plus
  the pre-flight assertion
- Batch submitter with a per-request tag identifying cell and document/pool
  (results return in arbitrary order)
- ~~Spend meter~~ — `llm_cutter.SpendMeter` has running token/cost accounting
  and a `--budget` hard stop that checks *before* each call. Scoped to one
  script; lift it out when the batch submitter lands.
- ~~Zero-answer detector~~ — `llm_cutter.ZeroAnswerError`. Fires on an empty
  answer and reports the output-token count that was billed for it. Same
  caveat: needs lifting to a shared module.
- ~~Fragment-fidelity gate~~ — `analysis/verify_fragments.py`. Checks for
  invented tokens, dropped content, exact reconstruction, and key/fragment
  structure; exits non-zero so it can gate the pipeline. Run it on every cell
  before scoring.
- Malformed-partition rule (repair or drop-and-penalize), applied identically
  across cells and documented
- Per-pool trivial-floor computation
- Displacement metric alongside τ
- Scaled identifier corpus, 50 → 500 records
