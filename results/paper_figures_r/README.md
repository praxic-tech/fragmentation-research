# Paper figures (R / ggplot2)

The publication figures, rebuilt in R. The earlier matplotlib versions stay in
`results/paper_figures/` for audit; this directory supersedes them for the paper.
This is a visualization rewrite only: no analysis, metric, CI, baseline, sample
size or statistical decision changed, and every plotted value is read from a
frozen artifact.

## Rebuild

From the repository root:

```bash
Rscript results/paper_figures_r/make_all.R
```

That runs every figure script, then `validate_figures.R`, which checks each
figure's CSV against the frozen sources independently of the plotting code
(values, CIs, sample sizes, attacker names, post-hoc flags, output files) and
stops on any failure. Any single figure can be rebuilt with
`Rscript results/paper_figures_r/<script>.R`.

Requires R 4.4 with `ggplot2`, `patchwork`, `svglite`, `jsonlite`.

## Files

Each figure has `<name>.R` (the script), `<name>.pdf` (vector, fonts embedded),
`<name>.svg` (vector, text kept as text), `<name>.png` (600 dpi) and `<name>.csv`
(exactly the data frame the plot is drawn from).

- `theme_paper.R`: shared sizes, fonts, palette, marker encoding, theme and the
  `save_figure()` export helper. Edit here to change every figure.
- `make_all.R`: rebuilds everything and validates.
- `validate_figures.R`: the independent checks.

## Figures

| Figure | Script | Placement | Width | Status | Demonstrates | Frozen source |
|---|---|---|---|---|---|---|
| 1 | `fig1_headline_attackers.R` | Main | 1 column | Prespecified; embedding row post hoc | The one-shot generative attacker reconstructs far more than the tested statistical and similarity-based attackers | `results/final_analysis/TABLES/table_B_headline_J.csv` |
| 2 | `fig2_grid_reconstruction.R` | Main | 1 column | Prespecified | Joint reconstruction varies with strategy and granularity; subject-verb cuts are the most resistant tested condition | `TABLES/table_C_grid_J.csv` |
| 3 | `fig3_linkage_vs_ordering.R` | Main | 2 columns | Prespecified | Strategies differ in how much they affect linkage versus ordering | `TABLES/table_C_grid_J.csv` |
| 4 | `fig4_identifiers.R` | Main | 1 column | (a) prespecified; (b) exploratory post-hoc diagnostic; embedding row post hoc | The record template is visible, but cross-field record association is not recovered in this setup | `TABLES/table_E_identifier_J.csv`, `TABLES/table_E3_identifier_membership.csv` |
| 5 | `fig5_single_token.R` | Main | 1 column | **Post-hoc exploratory** (D16) | On identical text and pools, single-token cuts drove null-adjusted joint reconstruction to about its random-shuffle reference | `results/single_token_edge/analysis/per_pool.csv`, `summary.json` |
| A | `figA_gameO_vs_gameJ.R` | Appendix | 1 column | Prespecified | Ordering with membership given is much easier than joint recovery | `TABLES/table_D_game_O.csv`, `table_C_grid_J.csv`, `table_B_headline_J.csv` |
| B | `figB_resource_scaling.R` | Appendix | 1 column | Prespecified; single-token points post hoc | Output grows with fragment count, but fragment count does not determine completion | `results/final_analysis/MASTER_RESULTS.csv`; `results/batches/single-token-edge-J*.results.jsonl`; `results/final/singleTokenEdgeJ/edge__token/J.jsonl` |
| C | `figC_token_raw_vs_null.R` | Appendix | 1 column | **Post-hoc exploratory** (D16) | What A_VJ ≈ 0 means in raw terms | `results/single_token_edge/analysis/per_pool.csv` |

Retired from the matplotlib set: the "tested landscape" figure (it put A_J from
different corpora, lengths and tasks on one axis, and used the id-level A_J for
the token arm, which the frozen D16 design treats as secondary). Its content is
covered by Figs. 2, 4 and 5 and the tables.

## Visual system

- Sizes: one column 3.33 in, two columns 7.0 in (ACM sigconf); fonts Arial,
  8 pt titles, 7 pt ticks, 6 pt direct labels; set in `theme_paper.R`.
- One encoding for the whole paper (Okabe–Ito colours, validated for
  colour-vision deficiency, plus distinct shapes so figures survive grayscale):
  One-shot Sonnet blue filled circle; Memon-inspired vermillion filled square;
  Embedding (post-hoc exploratory) green open diamond; baselines grey.
- **Post-hoc exploratory results always use open (white-filled) markers**, and
  the caption says so.
- Baselines are reference lines or ticks, never attacker rows. Dashed =
  analytic one-bucket baseline or a null; solid = schema-order baseline;
  dotted = template-respecting chance.
- Bounded 0–1 metrics use the full 0–1 axis, except Fig. 4, which runs 0–0.3
  (starting at zero) because every estimate lies below 0.25.

## Plotting-input correction (Appendix B)

The matplotlib resource figure plotted, for the 20 single-token units, the
output tokens of the first call. For 8 of them the scored answer came from the
repair call; for 3 others the repair call exhausted 128k and the unit kept its
first answer. Appendix B now plots the call whose answer was scored, the same
definition MASTER_RESULTS uses for prespecified units. No reported result changes.

## Draft captions

**Figure 1.** Headline prose, Game J: attacker comparison on the 46 headline
pools (seven full-length PMC case reports each, sentence cut). Points are means
over pools; bars are 95% percentile-bootstrap CIs (10,000 resamples over pools),
some narrower than their markers. (a) Linkage component F1_L: recovery of
same-document fragment pairs, direction ignored. (b) Joint ordered-pair F1_J.
The dashed line is the mean analytic one-bucket baseline, the expected score of
placing every fragment in one group in arbitrary order (per-pool values
0.13–0.25); it is a reference, not an attacker. The embedding attacker (open
marker) is post-hoc exploratory: designed after the Memon-inspired / Sonnet gap
was observed and frozen before its own evaluation; F1_L is its primary
comparison. One-shot Sonnet: F1_L 0.882 [0.861, 0.901], F1_J 0.723 [0.702, 0.743].

**Figure 2.** Joint reconstruction F1_J of one-shot Sonnet across the nine
retained fragmentation conditions, grouped by strategy; within a group, rows run
from sentence to clause to 12-word token window. Points are means over grid
pools 2–25 (24 pools of seven documents; 23 for random / token window, where one
pool exhausted the 128k output budget and is excluded as a non-completion, never
scored 0), with 95% percentile-bootstrap CIs. Grey ticks mark each condition's
analytic one-bucket baseline (0.128–0.132). Prespecified; the nine conditions
were retained after a disclosed screening pool, which is excluded. Subject-verb
cuts give the lowest F1_J at both granularities; every condition remains far
above its baseline.

**Figure 3.** The two components of Game J (F1_J = F1_L × q, exactly, per pool)
for the conditions of Fig. 2, one-shot Sonnet. (a) Linkage component F1_L; grey
ticks mark each condition's analytic linkage baseline. (b) Direction accuracy q:
among fragment pairs the attacker correctly placed in the same document, the
share also placed in the true relative order (micro-averaged); the dashed line
is chance (0.5). Means with 95% percentile-bootstrap CIs over pools, same pools
as Fig. 2. Prespecified. Linkage varies more across strategies than direction
accuracy does, and the subject-verb conditions have the lowest F1_L; paired
comparisons are in Table [X]. The figure shows the decomposition; it does not
identify a mechanism.

**Figure 4.** Synthetic identifier records, Game J (20 pools of seven records,
four fields each). (a) Joint reconstruction F1_J (prespecified) with 95%
percentile-bootstrap CIs over pools. Dashed: analytic one-bucket baseline
(0.10). Solid: schema-order baseline (0.20), the score of ordering one bucket by
field type read from each fragment's format, which needs no knowledge of
records. (b) Linkage precision, the share of an attacker's claimed same-record
pairs that are real, against 1/7 (dotted), the value for groups that respect the
one-field-per-type template but assign records at random. **Panel (b) is an
exploratory post-hoc diagnostic, not the prespecified identifier endpoint**
(the schema advantage with its frozen 90% CI rule; Table [X]). The axis runs
0–0.3 because every estimate lies below 0.25. Random partition is a baseline,
not an attacker; the embedding attacker (open marker) is post-hoc exploratory.
All 140 of Sonnet's groups held exactly one field of each type, yet its linkage
precision sits at template-respecting chance, and every attacker scored below
the schema-order baseline. Synthetic records in a closed world: this does not
establish protection for real identifier data.

**Figure 5.** POST-HOC EXPLORATORY (RUN_DECISIONS D16). The same 20 headline
pools and the same four-sentence excerpts per document, cut into sentences (28
fragments per pool) or single whitespace tokens (438–669 per pool); one-shot
Sonnet, 20 of 20 units completed in each arm. (a) Null-adjusted visible joint
reconstruction A_VJ per pool (grey lines) and arm means (open markers: 0.588
sentence, 0.016 token); the dashed line at 0 is each pool's oracle-size
random-shuffle null (10,000 permutations into the true group sizes). (b)
Per-pool paired differences (grey) and their mean, 0.572, with the 95% paired
percentile-bootstrap CI [0.539, 0.607]. Every pool is lower in the token arm
(20/20; exact two-sided sign test p ≈ 1.9 × 10⁻⁶). A binary comparison on
excerpts, not a dose–response experiment: it locates no threshold, and the cut
changes semantic context and search complexity together.

**Appendix Figure A.** Ordering with membership given (Game O, triangles)
against joint membership-and-order recovery (Game J, circles), one-shot Sonnet,
per condition. Game O is plotted as (1 + τ)/2, the value F1_J takes when
membership is perfect, with its frozen τ CI transformed the same way. Units:
Game O, 100 headline documents and 30 documents per grid condition; Game J, 46
headline pools and 24 (23) pools per condition; 95% percentile-bootstrap CIs
over documents (O) or pools (J). The games use different units and prompts, so
the markers are not joined; Game O is a reference, not an upper bound on Game J.
Prespecified.

**Appendix Figure B.** Output tokens of the answering call (the call whose
answer was scored) against fragments in the pool, for every one-shot Game J
unit: 46 headline, 216 grid and 20 identifier pools (prespecified), and the 20
single-token-arm pools (post-hoc exploratory, open diamonds). Dashed line: the
prespecified 128,000-token per-call output budget. The one resource-bounded
non-completion (ringed; random / token window, 322 fragments) exhausted it; the
largest completed prespecified pool had 537 fragments, and every single-token
unit, up to 669 fragments, completed. Spearman ρ(fragments, answering-call
output tokens) = 0.739 [0.683, 0.787] over the 282 prespecified units. For 8
single-token units the scored answer came from the repair call, whose tokens are
plotted; 3 repair calls exhausted 128k, and those units are plotted at their
first answer.

**Appendix Figure C.** POST-HOC EXPLORATORY (D16). Raw visible joint score V_J
(open circles) and its oracle-size random-shuffle null (grey diamonds) per arm;
faint points are the 20 pools, large markers the arm means. Sentence: 0.762 vs
0.423. Single token: 0.155 vs 0.141. Fig. 5's A_VJ is (V_J − null)/(1 − null)
per pool.
