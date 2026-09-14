# POST-HOC EXPLORATORY — CONTROLLED SINGLE-TOKEN EDGE-CASE EXPERIMENT (frozen design)

**Status: frozen 2026-09-14 (RUN_DECISIONS D16). Not submitted.** Nothing runs
until the user gives explicit launch approval. This experiment is post hoc and
exploratory. It must never be represented as prespecified or confirmatory, and
it stays separate from the prespecified grid. It supersedes the unsubmitted D15
excerpt design.

## Question
On identical source text, how does joint reconstruction change between
sentence fragmentation and single whitespace-token fragmentation, the extreme
end of the granularity axis? This is a binary edge case, not a grid. The
difference in fragment count and search complexity is intentional: the
experiment asks about granularity as an operational knob. It does not isolate
the causal mechanism of semantic-context removal, and no claim may attribute
an effect to reduced semantic context alone.

## Sample (frozen; see results/single_token_edge/DESIGN_REPORT.md for every ID)
- **Pools.** The 46 headline pools (data/pools/pools.json, built 2026-08-28
  with seed 42, before any pool-level attack; membership byte-identical since)
  are ordered by SHA-256 of UTF-8("single-token-edge-v1" + pool_id), with no
  separator. The first 20 are taken, 140 documents in total. Existing
  7-document membership is kept. No selection uses any score, difficulty,
  topic, length or attack outcome.
- **Provenance.** Some selected documents are among the 21 headline documents
  with documented prior scored development contact (RUN_DECISIONS, development
  history); they are listed in the design report. This is provenance only:
  nothing is excluded, replaced, reordered or resampled. **Wording:** these
  pools are not "untouched" in a literal sense. They are the headline pools,
  fixed before any attack, with the documented development contact, and they
  have since been attacked in steps 1–5. Say "headline pools", not "untouched
  pools".
- **Sentences.** The corpus's own segmentation (pull_prose_v4.split_sentences:
  spaCy, per paragraph) on the original source text (data/prose/prose_raw.jsonl)
  with the minimum-length filter disabled (min_chars=1). Four consecutive
  sentences are therefore four consecutive source sentences. The corpus
  reference cut is the same function with min_chars=15, reproduced on 500/500
  documents. The selection happens before any length filtering, so genuine
  short source segments (for example figure-citation stubs such as "2B).") stay
  in the excerpt.
- **Excerpt.** Valid starts are 0 … n−4. The start is valid[SHA-256(UTF-8(
  "single-token-edge-v1" + document_id)) mod len(valid)], and exactly 4
  consecutive sentences are taken. There is no word-count target and no
  inspection of content. The per-document record holds the document and pool
  IDs, the sentence count, the start and end indexes, the relative position,
  the word count, and the excerpt and source SHA-256.

## Conditions (identical underlying text)
- **Sentence:** the 4 sentences are 4 fragments, so 28 fragments per pool.
- **Single-token:** the identical excerpt text split on whitespace, one
  fragment per token, verbatim. No normalisation, no punctuation stripping, no
  case folding.

## Attackers
- **Frozen one-shot Sonnet game J.** Unchanged prompt, N = 7 knowledge, masked
  aliases, per-unit presentation shuffle, model and settings, 128k rule,
  repair and finalisation policy, scorer path, and RBNC policy. No special
  word-level prompt.
- **Memon-inspired J and MPNet J, run locally.** They are reported, but neither
  was designed for isolated single tokens, so a weak token-level result from
  them is **not** evidence of security.
- **Specialised or adaptive token-level attackers** (frequency or
  language-model based) are not in this arm. They are an explicit limitation
  and a future adversary class.

## Metrics
- **Compatibility, secondary for this arm:** F1_J, F1_L, q, analytic b_J, A_J
  (the ordinary id-level scorer). At single-token granularity the id-level
  scorer can penalise a visibly correct reconstruction, because identical
  visible tokens carry distinct hidden ids.
- **Visible, duplicate-invariant (harness/visible_metrics.py).** Hidden ids are
  mapped back to the visible text shown to the attacker, and both conditions
  are converted to whitespace-token sequences.
  - **V_L:** multiset intersection of visible tokens for each predicted-group /
    true-document pair, then a one-to-one Hungarian assignment maximising the
    total matched occurrences, divided by the total true tokens.
  - **V_J:** the same with token-level LCS length.
  - **q_V = V_J / V_L:** diagnostic only.
  - **Invariant:** V_J ≤ V_L.
  - The reported V values are optimal totals, so they do not depend on
    Hungarian tie-breaking (which is deterministic anyway).
  - Dropped fragments are read as singletons (the J scorer's reading); a
    repeated id counts once; unknown ids are ignored.
- **Nulls** (the analytic b_J does not apply to visible metrics). Each is
  **10,000 deterministic permutation draws per pool × condition × null type**,
  from a numpy PCG64 generator seeded by SHA-256("single-token-edge-v1|" +
  pool + "|" + condition + "|" + kind).
  - **Oracle-size permutation null (PRIMARY).** Permute all fragment labels,
    cut them into 7 groups with the TRUE per-document fragment counts, and keep
    the permuted order within groups. It is called oracle-size because it is
    given the true source sizes.
  - **Predicted-structure permutation null (ROBUSTNESS).** Permute the labels
    into the attacker's own predicted group sizes and output positions, after
    the same cleaning.
- **Advantage.** A_VJ = (V_J − mean null V_J) / (1 − mean null V_J), and
  A_VL likewise. A_VJ is the fraction of the gap between the pool-specific
  oracle-size null mean and perfect visible reconstruction that the observed
  reconstruction achieves. A_VJ(sentence) − A_VJ(token) is the difference in
  null-adjusted visible reconstruction advantage. It is **not** the "fraction
  of reconstruction lost". Raw and normalised values are both reported. If raw
  and normalised paired differences disagree in sign for any pool, that
  disagreement is reported.

## Outcomes and statistics
- **Primary (exploratory):** the paired difference A_VJ(sentence) − A_VJ(token)
  by pool, using the oracle-size null.
- **Secondary / descriptive:** raw V_J, A_VL, raw V_L, F1_J, F1_L, A_J,
  completion / RBNC, and resources and cost. q_V is diagnostic only.
- **Unit and methods.** The pool is the unit. Paired percentile bootstrap:
  10,000 resamples, seed 42, 95% CI, each pool resampled once with both
  conditions. Exact two-sided sign test on the paired A_VJ differences; zero
  differences are ties, omitted from the denominator. Report n selected, n
  effective (completed pairs) and n nonzero. No new multiplicity machinery.
- **RBNC.** Never scored as 0. The paired analysis uses completed pairs and
  reports n_effective; the completion / RBNC rate is itself a result.
  **Limitation:** a complete-case paired analysis conditions on the pools the
  token arm can finish, which may introduce selection bias of unknown
  direction.
- **Descriptive cross-check.** The excerpt sentence arm's F1_J against the
  existing full-document headline F1_J, on that common metric only (never
  headline F1_J against V_J). It cannot be used to alter the experiment.

## Scorer validation (score-free, constructed data only; harness/test_visible_metrics.py)
- The fast LCS equals the reference dynamic programme.
- Perfect reconstruction scores 1 in both representations.
- Swapping hidden ids of identical visible tokens changes nothing.
- Relabelling predicted groups changes nothing.
- Wrong membership lowers V_L; correct membership in the wrong order keeps V_L
  and lowers V_J; reversal lowers V_J.
- V_J ≤ V_L.
- Edge cases: everything in one group, an empty group, unbalanced groups,
  identical tokens repeated across sources, Hungarian ties.
- Nulls are reproducible from their seed.
- Controlled membership and order corruption on synthetic ground truth, in
  both representations.

## Claim scope
- **May support:** "On identical four-sentence excerpts from seven-document
  pools of PMC clinical case reports, single-token fragmentation reduced /
  changed null-adjusted visible joint reconstruction under the frozen one-shot
  Sonnet attacker relative to sentence fragmentation."
- **May not support:**
  - "single-token fragmentation is secure" or "prevents reconstruction";
  - any fragmentation threshold;
  - causal attribution to reduced semantic content;
  - generalisation to full documents, or to other corpora, languages or pool
    sizes;
  - claims about specialised, adaptive or multi-pass attackers.
- Single-token fragmentation is an extreme boundary condition on the
  granularity axis, not a proposed deployment setting.
