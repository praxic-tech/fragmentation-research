# Final writing assignments — Michael and Arafat

**Due: your last day on the project** (Aiden confirms the date). This
supersedes the week-7 methods assignment; if you drafted week 7, keep it and
apply the "what changed" notes in your section. Who owns what, and the evidence
for it, is recorded in `docs/CONTRIBUTIONS.md`.

**Aiden writes everything not listed here:** introduction, threat model,
related work, **the corpus** (including why the synthetic corpus was rejected),
**coherence-sever** (its design and the D7 fix), the experimental design, the
hierarchical attacker, results, discussion, budget and limitations.

## The rules

1. **No numbers from experiments that have not run.** The headline and grid
   pools 2–25 have not run: write the method, leave the result as `[TBD]`.
   Properties of the *defence* (fragment counts, fidelity, cut rates) and of
   the *design* are not experiment results and are fine.
2. **Pool 1 is screening data, not a result** (RUN_DECISIONS D5). Never quote a
   pool-1 attack score as a finding.
3. **Every claim traceable to a committed file or a passing test.** Cite the
   path inline while drafting; we strip them before submission.
4. **End your section with "what I am not sure about."**
5. Read `docs/RUN_DECISIONS.md` (D1–D10) and `docs/audit_packet_final_run.md`
   first. They record every decision and every fix.

---

## Michael — the defence's cutters, the metrics, and the statistical baselines

You wrote `random_cut.py`, `subject_verb.py` and the grid driver
(`harness/run_grid.py`), the original scorers (`harness/scoring.py`: Kendall τ,
pairwise precision / recall / F1), the harness and loader, the random baseline,
and `memon.py`.

### §3.2 The cutters you own (900–1,300 words)

1. **random.** Structure-blind cuts at whitespace word boundaries, with the
   count matched per document to the reference cut at the same granularity, so
   a difference between strategies is not a difference in count. Verified:
   counts match on 175/175 documents; it ends a sentence 5.5% of the time
   against 5.1% chance.
2. **subject-verb.** Within each unit, cut immediately before the governing verb
   of the first nominal subject; units with no subject stay whole, never faked.
   Fires on 66.7% of sentences and 57.0% of clauses; 99% of cuts land before a
   VERB/AUX head. A cut now falls only on whitespace (D7 fixed four cut points
   inside "patient’s" / "MP™"). Flag the passive-subject exclusion as a
   limitation for clinical text.
3. **The granularity menu.** sentence / clause / token-window are *which
   boundaries are on offer*, not how aggressive the cut is; "never cuts
   mid-clause" is true by construction at clause granularity, so the paper must
   not claim judgement where it only has a menu. Token-window is 12 whitespace
   words for every strategy.
4. **The grid that runs (D5): 9 cells.** random × {sentence, clause,
   token-window}; semantic × {sentence, clause}; coherence-sever × {clause,
   token-window}; subject-verb × {sentence, clause}. Clause is a complete
   head-to-head row; random at all three granularities is the control sweep.
   subject-verb has no token-window cell by design.
5. **Fragment yield** (frame A, from `results/grid_A/*/cell_manifest.json`):

   | cell | fragments | per document |
   |---|---|---|
   | random / semantic × sentence | 4,267 | 24.4 |
   | random / semantic × clause | 5,363 | 30.6 |
   | random × token-window | 6,987 | 39.9 |
   | coherence-sever × clause | 3,926 | 22.4 |
   | coherence-sever × token-window | 6,977 | 39.9 |
   | subject-verb × sentence | 7,115 | 40.7 |
   | subject-verb × clause | 8,418 | 48.1 |

   Yield varies about 2× across the grid; say it is a confound the analysis
   handles. Include the coherence-sever rows as numbers only — Aiden writes that
   strategy.
6. **Fidelity: the defence is lossless.** `f1 ‖ … ‖ fm = R(D)` exactly. The gate
   (`analysis/verify_fragments.py`) checks invented tokens, dropped tokens,
   exact reconstruction and key structure, per cell; all 9 cells rejoin their
   source exactly, 175/175. It caught a wrong `--raw` path (27% apparent loss)
   and the subject-verb whitespace cuts.

### §4.2 Metrics — your scorers and what they became (900–1,200 words)

Your `scoring.py` is where the metric package started (`score_ordering`,
`score_linkage`, `trivial_baseline` are still imported by the scorer today).
Write the lineage and the current definitions:

1. **Kendall τ (game O) and pairwise precision / recall / F1 (game L)** — your
   originals, and what each does and does not say.
2. **Why J is the headline**; O survives as a second threat model (membership
   leaked, content still fragmented).
3. **Ordered-pair F1** (`harness/joint_metrics.py`) and its two identities,
   verified in `harness/test_joint_metrics.py`: ignore direction → linkage F1;
   perfect membership → (1+τ)/2, **not** τ. Then **F1_J = F1_L × q**, with the
   precision / recall / pair-count breakdown every report now prints.
4. **The analytic baseline** T/(P+T) — a baseline, not a floor.
5. **Advantage per pool, then averaged**, and why normalising a grand mean is a
   different quantity.
6. **q undefined at K = 0**; aggregate with q_micro = ΣC/ΣK.
7. **Beyond τ**: exact placement, mean shift, longest intact run, run%
   (`joint_metrics.reconstruction_detail`).
8. **Completion rate and the integrity gate**: a unit that exhausts the model's
   128k output is a non-completion, reported beside every score and never
   scored (D6); a cell with a transport hole or a unit over 25% placed by the
   completion policy is refused.

### §5.1 The statistical baselines (400–700 words)

1. **Random floors**, and the analytic one-bucket baseline.
2. **Jaccard-Greedy and Jaccard-MST**: word-bigram Jaccard orderers, **not**
   Memon's PPM + tree-pruning method, hence the rename (D1). The old versions
   leaked through raw ids and list order (τ +0.32 / +0.70 on prose); masked and
   shuffled per unit with truth-independent tie-breaking they sit at chance
   (τ −0.02 / −0.01, `results/harness_results.json`). Floors, not competitive
   attackers, and **game O only**: their historical game L column is the shared
   TF-IDF grouper, not a Jaccard linkage attack (docs/adversaries.md, 2026-09-13).
3. **The Memon-inspired joint attacker** (`adversaries/memon_joint.py`): TF-IDF
   cosine + average-linkage grouping to exactly N (the grouper the repo calls
   "B_stat"), ordering by your directional character-bigram boundary statistic
   as W = tanh(Δ/2), then a deterministic local ordering search. It borrows only
   the context-model idea from Shanmugasundaram & Memon: no PPM, no
   Hamiltonian-path / tree-pruning search. Not a faithful Memon implementation.
   Results: `results/final_analysis/` (the SHA-256-seeded canonical run).

**Source of truth:** `datagen/random_cut.py`, `datagen/subject_verb.py`,
`harness/run_grid.py`, `harness/scoring.py`, `harness/joint_metrics.py`,
`harness/test_joint_metrics.py`, `analysis/verify_fragments.py`,
`harness/harness.py`, `adversaries/memon_joint.py`, `results/grid_A/*/cell_manifest.json`,
RUN_DECISIONS D1, D5, D6, D7.

**Target: 2,200–3,200 words in total.**

**What changed since week 7:** metrics are now yours (week 7 assigned them to
Arafat in error); coherence-sever is Aiden's; the yield table is frame A, not the
8-document probe; semantic × sentence is sentence splitting (Arafat writes it).

---

## Arafat — the reference cutter and the one-shot LLM adversary

You wrote the LLM adversary (`run_llm_adversary.py` → `adversaries/llm_adversary.py`,
now driven by `adversaries/joint_game.py` and `adversaries/batch_game.py`), the
record generator, and the cutter that became `datagen/prose_cutter.py`.

### §3.1 The reference cutter and the shared splitters (400–600 words)

1. **semantic**: cut at every boundary of the unit. **semantic × sentence is
   ordinary sentence-boundary splitting**, the reference condition, and the
   headline's cut — not evidence for a distinct "semantic" cutter (D5).
2. **One tokenizer, one sentence base.** Every strategy imports its sentence and
   clause splitters from `prose_cutter.py`, and clauses subdivide the same
   sentence units, so the granularity axis runs strictly coarse → fine. Say why
   this mattered: two tokenizers once made clause produce *fewer* fragments than
   sentence on 500 documents (`docs/corpus_build.md` §3).

### §4.1 The one-shot adversary (700–1,000 words)

1. **What the model is asked.** One prompt per unit. J: every fragment of a pool
   of 7 records, mixed, "return ONLY a JSON array of 7 arrays … in their
   reconstructed order" (`joint_game.prompt_J`). O: one record's fragments,
   order only. `claude-sonnet-5`, default sampling and adaptive reasoning,
   Batches API.
2. **Masking and presentation.** Labels are a shuffled permutation `m_0000000…`;
   presentation is shuffled; `preflight()` refuses any prompt with a raw id.
   Both shuffles are seeded per unit (D7) — a fixed seed had made the
   permutation depend only on fragment count.
3. **The masking side-channel diagnostic (G3, D8).** On a development pool, raw
   ids in true order reach joint F1 ≈ 1.0 (a planted leak is fully exploited);
   masked, the model's order agrees with label numbers and presentation order
   only as its accuracy implies (every gap ≤ 0.016). Methods validation on
   development data — citable. It does not require masked scores to be low.
4. **Repair and parsing.** One repair round with bookkeeping-only feedback
   (never ground truth); the parser takes the longest decodable JSON list.
5. **The 128k ceiling (D6).** Full budget, one attempt. At least 96.7% of every
   J answer's output was hidden reasoning, so a pool that exhausts 128k is
   reasoning-bound: a non-completion, recorded and never re-asked. Why not 64k:
   it would have cut off 5 of 11 J answers seen in screening, mostly in the
   strongest defences.

**Source of truth:** `datagen/prose_cutter.py`, `adversaries/joint_game.py`,
`adversaries/batch_game.py`, `adversaries/llm_adversary.py`, `harness/masking.py`,
`harness/test_truncation.py`, `harness/test_parser.py`,
`results/audit/g3_diagnostic.json`, RUN_DECISIONS D5–D8.

**Target: 1,100–1,600 words in total.**

**Unconfirmed:** if you built the pool sampling frame (`datagen/build_pools.py`),
add one paragraph on how the 71 pools were drawn. Aiden writes the rest of the
design.

**What changed since week 7:** metrics moved to Michael; the corpus is Aiden's;
the design is Aiden's; your part is the reference cutter and the adversary.

---

## DO NOT WRITE

- Any grid or headline result, strategy ranking, attacker score or
  non-completion count: `[TBD]`.
- Any pool-1 attack score as a finding.
- Coherence-sever, the corpus, the experimental design, the hierarchical
  attacker, cost or budget — Aiden's.
- Introduction, threat model, related work, discussion, limitations — Aiden's;
  put your limitations in your "not sure about" list.

## Definition of done

- [ ] Prose in the shared doc, sectioned as above.
- [ ] Every methodological claim cites a committed file or a passing test.
- [ ] Zero numbers from unrun experiments.
- [ ] "What I am not sure about" at the end of each section.
- [ ] A one-paragraph handover note: anything about your code that is not written
      down anywhere in the repo. After you leave, nobody can ask.

## If you finish early

Cross-check the other person's section: mark every claim you cannot verify from
the repo yourself.
