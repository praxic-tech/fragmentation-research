# Week 7 — methods sections

**Due: Wednesday 17 September 2026.** Internal freeze is 19 November; the paper
gets written in the gaps between runs, not after them.

## Why writing, and why now

The experiment moved to a **joint threat model** (game J: recover membership AND
order from one mixed pool). That change invalidated a chunk of week 6's
*results* work. It invalidated **none** of the two things below, which are
frozen, gate-verified, and the parts of the paper that do not depend on a single
number coming back from the run.

So this week is methods. Everything assigned here can be written from code that
is committed and tests that pass today. Nothing here is at risk of being
rewritten when the grid lands.

**The single rule: no numbers from experiments that have not run.** If a claim
needs the grid, it is not this week's work. Write the method, leave the result
as `[TBD]`. A methods section that is correct and numberless is finished work; a
methods section with placeholder numbers that turn out wrong is negative work.

---

## Michael — §3 Fragmentation strategies (the defence)

You own the defence. `random_cut.py`, `coherence_sever.py`, `subject_verb.py`
and the grid driver are yours, and they are still exactly what the paper tests.

**Write:**

1. **The four strategies.** For each: the algorithm, and — more importantly —
   *the linguistic assumption it encodes about where meaning lives*. random
   assumes nothing. semantic assumes topic shifts are the seams. coherence-sever
   assumes discourse links are. subject-verb assumes grammatical predicates are.
   The paper's interest is in which assumption survives contact with an
   attacker, so state each one sharply enough to be wrong.

2. **The three granularities, and the menu argument.** sentence / clause /
   token-window are not "how aggressive the cut is" — they are *which boundaries
   are on offer*. A strategy picks among the boundaries its granularity exposes.
   This matters because "never cuts mid-clause" is partly true **by
   construction** when the unit is the clause, and the paper must not claim
   judgement where it only has a menu. Say so explicitly. It is the kind of
   thing a reviewer finds, and we would rather find it first.

3. **Fragment yield per strategy × granularity.** You now have measured counts
   on a shared 8-document sample (`results/o_probe/`, cells named
   `<strategy>__<granularity>`). Report the table. Flag that yield varies by
   roughly 3× across the grid (16 to 53 fragments/document), because that is a
   confound the analysis has to handle, not a footnote.

4. **The fidelity guarantee.** `f1 ‖ f2 ‖ … ‖ fm = R(D)` exactly — the defence
   is lossless; no content is dropped or altered, only split.
   `analysis/verify_fragments.py` is the gate that enforces it per cell. Say
   what it checks and that it runs on every cell. This gate already caught a
   real misconfiguration (27% apparent content loss that turned out to be a
   wrong `--raw` path), which is worth one sentence: it shows the check is
   load-bearing rather than ceremonial.

5. **llm-cut.** The cell where the *defender* is an LLM. Cover the prompt
   lineage — v1 produced the published profile in `docs/llm_cut_profile.md` and
   is retained for reproducibility; v3-strategist is live — and what v3 actually
   bought: **consistency, not better cuts.** v1 was a mixture, not a condition:
   it cut at every available boundary on 7 of 11 documents. v3 nearly halves the
   cut-rate variance and eliminates the degenerate cases. Report the cut-rate
   distribution beside the cell, never the mean alone.

**Source of truth:** `datagen/*.py`, `harness/run_grid.py`,
`analysis/verify_fragments.py`, `docs/llm_cut_profile.md`,
`results/llm_cut_decisions.jsonl`, `results/o_probe/`.

**Target: 1,200–1,800 words.**

---

## Arafat — §4 Metrics and experimental design

You own measurement. `scoring.py` is the ancestor of the current metric package,
and the pool sampling frame you built is unchanged — it is still the frame the
whole grid runs on.

**Write:**

1. **The three games, and why J is the headline.** O gives the attacker
   membership for free and asks only for order. L asks only for membership. J
   asks for both from one mixed pool. A real store is a mixed pile with nothing
   given, so O and L each hand the attacker an oracle the real world does not
   provide. State O's surviving role precisely: it is a **second threat model** —
   the metadata layer is compromised, membership leaks, content is still
   fragmented — not a methodological convenience.

2. **Ordered-pair F1.** Definition, then the two identities, both verified in
   `harness/test_joint_metrics.py`:
   - ignore direction and it is exactly the old linkage F1;
   - under perfect membership it equals `(1+τ)/2`, **not** τ. Random ordering
     gives F1_J = 0.5 and τ = 0. This distinction was got wrong once already, so
     state it carefully.
   - the decomposition `F1_J = F1_L × q`, which is how the paper answers "which
     half failed".

3. **The analytic baseline, and the word "baseline".** `E[F1_J] = T/(P+T)`,
   exactly half the linkage baseline, computed in closed form rather than
   sampled — sampling it was measurably noisy and on a small pool landed on 0 by
   luck. It is a **baseline, not a floor**: an all-singleton answer scores lower.
   The word matters, and the old code used the wrong one.

4. **Advantage, and the aggregation trap.** `A_J = (F1_J − b_J)/(1 − b_J)`,
   computed **per pool and then averaged**. Normalising a grand mean by a mean
   baseline is a different quantity, because the baseline moves with each pool's
   fragment-count distribution. One sentence on why, with the counterexample.

5. **q undefined at K = 0.** When linkage recovers no correct pair, ordering
   *could not be evaluated* — which is not the same as ordering being wrong.
   Report undefined, report the fraction of undefined pools, and aggregate with
   `q_micro = ΣC/ΣK`.

6. **Beyond τ: what the attacker actually recovers.** New this week
   (`joint_metrics.reconstruction_detail`). τ is generous — it scores broad
   direction over every pair and can look healthy while nothing is in place.
   Measured: one document at τ +0.430 had **0 of 27** fragments correctly placed
   and a longest intact stretch of 5; another at τ +0.886 had 13 of 21 placed.
   Report **longest intact run** beside τ, because it answers the question a
   reader actually has — how much contiguous readable text leaked.

7. **The sampling frame and the paired design.** 71 pools of 7 documents, pools
   as the unit of analysis (per-pool F1 ranges 0.229–0.703 and each pool's own
   baseline ranges 0.251–0.503 — pools are not interchangeable and the baseline
   is not a constant). Pool-level bootstrap resampling the **same pool indices
   across every strategy and attacker**; independently bootstrapping each cell
   throws away the paired design the shared-pool frame was built to buy.

**Source of truth:** `harness/joint_metrics.py`, `harness/test_joint_metrics.py`,
`datagen/build_pools.py`, `data/pools/`.

**Target: 1,500–2,000 words.**

---

## DO NOT WRITE THIS WEEK

Not because it is unimportant — because it will change.

- **Any grid result, any strategy ranking, any attacker score.** The grid has
  not run. A free-tier 8-document probe exists and is *directional only*: the
  strategy ranking in it already inverted once when a bug was fixed.
- **Cost or scale claims.** The model was rebuilt this week and its two largest
  assumptions stay unmeasured until the sizing run.
- **The blocker section.** Measured, negative, and its framing is still moving.
- **Related work.** Aiden's.

---

## Definition of done

- [ ] Prose in the shared doc, sectioned as above.
- [ ] **Every methodological claim traceable to a committed file or a passing
      test.** Cite the path inline while drafting; we strip them before
      submission. If you cannot point at the thing, it is a claim about what we
      meant to build.
- [ ] Zero numbers from unrun experiments. `[TBD]` is correct and expected.
- [ ] A short list at the end of each section: **what you are not sure about.**
      That list is more useful to me than the polished prose. I would rather
      have three honest uncertainties than none.

## If you finish early

Do not start the results section. Instead, read the *other* person's section and
mark every claim you cannot verify from the repo yourself. Cross-checking is
worth more right now than more words — the two failures that cost us most on
this project were both things that looked reasonable and nobody checked.
