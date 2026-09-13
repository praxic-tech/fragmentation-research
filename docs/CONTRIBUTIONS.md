# Contributions — who built what, and the evidence

The record of ownership for the paper's author contributions and for the final
writing assignments (`docs/deliverables/final_writing/ASSIGNMENTS.md`). Each
line cites where the ownership is recorded. AI assistance is disclosed in the
paper, not here or in the git log.

| component | owner | evidence |
|---|---|---|
| Random baseline (week 1): random guessers, Kendall τ / pairwise-F1 scoring, Monte Carlo | Michael | docs/deliverables/week1_random_baseline/deliverable.md |
| Scorers: `harness/scoring.py` (Kendall τ, pairwise precision / recall / F1), `harness.py`, `loader.py` | Michael | docs/deliverables/week3_unify_and_prose/michael_manifest.md; Arafat's `score_llm.py` reused them ("formulas copied from Michael's", arafat_manifest.md) |
| `memon.py` (n-gram baseline) | Michael | docs/deliverables/week2_first_adversary/deliverable.md |
| Cutters `random_cut.py`, `subject_verb.py`; grid driver `harness/run_grid.py` | Michael | docs/deliverables/week7_methods/DELIVERABLE.md; week5 / week6 hand-offs |
| LLM adversary (`run_llm_adversary.py` → `adversaries/llm_adversary.py`) | Arafat | docs/deliverables/week2_first_adversary/deliverable.md; week5_grid_build/deliverable.md |
| Synthetic record generator, identifier cutter (`Record_Generator.py`, `cutter.py`) | Arafat | docs/deliverables/week2_first_adversary/deliverable.md |
| Cutter that became `datagen/prose_cutter.py` (the semantic / reference cutter) | Arafat | docs/deliverables/week5_grid_build/deliverable.md |
| Synthetic prose generator `datagen/generate_prose_raw.py` | Arafat | docs/deliverables/week5_grid_build/deliverable.md |
| **The real prose corpus** (PMC case reports, post-cutoff; `data/prose/`) | **Aiden** | docs/corpus_build.md |
| **Rejecting the synthetic corpus** | **Aiden** | docs/corpus_build.md §1 (below) |
| **coherence-sever fix and re-cut** (D7) | **Aiden** | docs/RUN_DECISIONS.md D7; docs/audit_packet_final_run.md A4 |
| Threat model, joint game J, metric package `harness/joint_metrics.py`, paid path, integrity gates, ledger, answer store, hierarchical attacker and its batch path, run decisions D1–D10, audit packet | Aiden | docs/RUN_DECISIONS.md; git history |
| Pool sampling frame `datagen/build_pools.py` | **unverified** — the week-7 assignment credited Arafat, but no deliverable records it | Aiden to confirm |

## Why the synthetic corpus was rejected (Aiden)

The 25-document hand-written synthetic corpus had an **inverted lexical
signal**: sentences from the same record were *less* lexically similar than
sentences from different records (Cohen's d, same vs different record):

| metric | synthetic prose | real PMC prose |
|---|---|---|
| word-bigram | **−0.370** | +0.217 |
| char-4gram | **−0.275** | +0.359 |
| TF-IDF cosine | **−0.077** | +0.458 |

Within a synthetic note the sentences deliberately covered different things
(history → exam → imaging → diagnosis) and shared no vocabulary, while across
notes every record opened with the same template, so lexical similarity grouped
by section type, not by record. No similarity tuning can fix a signal pointing
the wrong way: it made linkage structurally impossible for lexical attackers
and misstated the LLM-vs-Memon gap. The corpus was replaced on 2026-08-10 by
real case reports published after the model's training cutoff (500/500
verified post-cutoff), and the synthetic set is archived in
`archive/superseded_corpora/synthetic25_*`. This deserves its own subsection in
the paper: evaluating fragmentation defences on synthetic corpora can invert the
signal the attack depends on.

## Corrections to earlier hand-outs

- The week-7 assignment gave the metrics section to Arafat as the author of
  `scoring.py`. The scorer is Michael's (above); metrics are his in the final
  assignment.
- coherence-sever was Michael's cutter as first built; its D7 redefinition and
  re-cut are Aiden's, and Aiden writes that strategy in the paper.
