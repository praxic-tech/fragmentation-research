# Paper figures

Regenerate everything with

```bash
python results/paper_figures/make_figures.py
```

Every figure is written as `figN_<name>.pdf` (vector, fonts embedded as Type 42),
`.svg` (text kept as text) and `.png` (400 dpi), plus `figN_<name>.csv`, the exact
values plotted. Nothing is typed by hand: the script reads the frozen analysis
tables (`results/final_analysis/TABLES/*.csv`, D13 bootstrap), the frozen
single-token analysis (`results/single_token_edge/analysis/`, D16) and per-unit rows
from `MASTER_RESULTS.csv`. The only arithmetic in the script is the monotone
transform (1 + τ)/2 of a τ interval (Fig. 4), the linear transform of the
identifier F1_J interval to A_J with the constant b_J = 0.10 (Fig. 7), and reading
per-unit token usage from the provider result records (Fig. 8).

Style: Okabe–Ito colour-blind-safe palette, and every series also differs by marker
shape or fill, so the figures survive grayscale. Filled markers are prespecified
analyses; **open markers are post-hoc exploratory** (the embedding attacker, D14; the
single-token edge experiment, D16). No grids, no in-plot titles beyond panel labels,
0–1 axes for every bounded metric. Widths: 7.0 in (double column) except Fig. 8
(3.4 in). Font 8 pt at those widths; scale to the template's column width.

Attacker names follow `docs/adversaries.md` exactly. "Memon-inspired" is not a
faithful Memon implementation; Jaccard-Greedy / Jaccard-MST are game-O floors only.

| figure | file | what it demonstrates | suggested placement |
|---|---|---|---|
| 1 | `fig1_headline_attackers` | On the 46 headline pools the one-shot LLM attacker sits in a different regime from every non-LLM attacker: F1_L 0.882 vs 0.364 (embedding, post hoc), 0.339 (Memon-inspired), 0.299 (analytic baseline); F1_J 0.723 vs 0.18 / 0.17 / 0.15. Pool-level points show the separation is not driven by a few pools. | main |
| 2 | `fig2_grid_reconstruction` | Sonnet F1_J across the nine retained grid cells, grouped by strategy: every cell stays far above its baseline (0.498–0.801 vs b_J ≈ 0.13), subject-verb cutting is the most resistant at both granularities, and finer cuts lower F1_J modestly within a strategy. Panel (b) is the normalized advantage A_J. | main |
| 3 | `fig3_linkage_vs_ordering` | The decomposition F1_J = F1_L × q. Subject-verb and random token-window cuts act mainly on linkage (F1_L); semantic-style boundaries act mainly on ordering (q). The statistical attackers order at chance (q ≈ 0.5) everywhere. | main |
| 4 | `fig4_gameO_vs_gameJ` | Ordering with membership given (Game O, (1 + τ)/2 over documents) versus joint reconstruction (Game J F1_J and q over pools): knowing membership changes the problem, and O is a reference, not a ceiling (different units and prompts). | main or appendix |
| 5 | `fig5_identifiers` | Identifiers: every attacker's F1_L, F1_J and linkage precision sit at or below the trivial baselines (analytic 0.10 / 0.20, schema-order 0.20, template chance 1/7), while the same attacker reaches 0.88 / 0.72 on prose (open reference circle). Communicates "schema visible, record association not recovered" without implying security. | main |
| 6 | `fig6_single_token_edge` | POST-HOC EXPLORATORY. (a) every one of the 20 pools moves down from the sentence cut to the single-token cut in A_VJ (0.588 → 0.016); (b) the paired difference 0.572 [0.539, 0.607], 20/20 positive; (c) why null normalization matters: raw V_J 0.762 vs null 0.423 (sentence) and 0.155 vs 0.141 (token); (d) A_VL: linkage signal survives, reduced (0.777 → 0.159). | main |
| 7 | `fig7_landscape` | The whole tested landscape on one A_J axis: grid cells, headline, identifiers, and the two post-hoc excerpt arms, deliberately **not connected**: these are different corpora and tasks, not a dose–response curve. | optional main / appendix |
| 8 | `fig8_resource_scaling` | Output tokens of the answering call grow with fragment count (ρ 0.739) but fragment count is not a hard ceiling: the one RBNC had 322 fragments while units of 537 (prespecified) and up to 669 (post-hoc token arm) completed. | appendix |

## Draft captions

**Fig. 1.** Headline prose, Game J, 46 pools of seven full-length PMC case reports
under the sentence cut. (a) Linkage component F1_L; (b) joint ordered-pair F1_J.
Large markers: pool means with 95% percentile-bootstrap CIs over pools (10,000
resamples); faint points: individual pools. The embedding attacker (open diamond) is
post-hoc exploratory (designed after the Memon-inspired / Sonnet gap was observed,
frozen before its evaluation).

**Fig. 2.** Game J across the nine retained strategy × granularity cells (grid pools
2–25, 24 pools each; random / token-window 23, one resource-bounded non-completion
excluded and never scored 0) and the full-length headline reference. (a) F1_J for
one-shot Sonnet (95% CI), Memon-inspired, the post-hoc embedding attacker and the
analytic one-bucket baseline b_J; (b) normalized advantage A_J = (F1_J − b_J)/(1 − b_J).

**Fig. 3.** Decomposition of Game J into (a) the linkage component F1_L and (b) the
direction accuracy q on the attacker's own correctly linked pairs; F1_J = F1_L × q
holds exactly per pool. Same units as Fig. 2. The dotted line is chance for q.

**Fig. 4.** Ordering with membership given (Game O, one document at a time; plotted
as (1 + τ)/2, the value F1_J takes when membership is perfect) against joint
reconstruction (Game J F1_J and q) for the same attacker and conditions. O: 100
headline documents, 30 documents per grid cell; J: 46 headline pools, 24 (23)
pools per cell. O is a membership-oracle reference, not an upper bound on J.

**Fig. 5.** Synthetic identifiers, Game J, 20 pools of seven records (28 fragments).
(a) F1_L against the analytic one-bucket baseline; (b) F1_J against the analytic
(0.10) and schema-order (0.20) baselines; (c) linkage precision, the share of an
attacker's claimed same-record pairs that are real, against 1/7 for
template-respecting random assignment. 95% CIs over pools (narrow). Open circles:
the same attacker on the prose headline, for scale. The frozen ±0.10 near-baseline
rule (90% CI on the schema advantage) is reported in Table 5.

**Fig. 6.** POST-HOC EXPLORATORY single-token edge case: the same four-sentence
excerpts from 20 headline pools (7 documents each) under a sentence cut (28
fragments per pool) and a single-whitespace-token cut (438–669), one-shot Sonnet,
20/20 completions in both arms. (a) Null-adjusted visible joint reconstruction
A_VJ per pool (lines) and means (diamonds); 0 is the pool's oracle-size permutation
null (10,000 draws). (b) Paired difference with its 95% paired-bootstrap CI and
exact sign test. (c) Raw V_J against the null mean, showing that the token arm's
raw score is close to what a random shuffle into the true sizes achieves. (d) The
linkage-only analogue A_VL. A binary edge case, not a dose–response design: it
locates no threshold.

**Fig. 7.** Normalized joint advantage A_J of one-shot Sonnet across everything
tested. Filled markers with frozen 95% CIs: the nine prespecified grid cells (R
random, S semantic, C coherence-sever, V subject-verb; s sentence, c clause, t
12-word token window), the headline pools and the identifier pools (A_J is a linear
transform of F1_J there, b_J = 0.10). Open markers: the two post-hoc excerpt arms
(per-pool points, no frozen per-arm CI). Points are not connected: the groups
differ in corpus, document length and task, and no dose–response experiment was run.

**Fig. 8.** Output tokens of the answering call against fragment count for every
one-shot Game J unit. Spearman ρ = 0.739 [0.683, 0.787] over the 282 prespecified
units. The one resource-bounded non-completion (ring) had 322 fragments; the largest
completed prespecified unit had 537, and all 20 post-hoc single-token units (438–669
fragments, open diamonds) completed. Output is almost entirely internal reasoning
(visible answers are ≤ ~2k tokens).
