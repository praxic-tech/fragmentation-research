# Final analysis package — current results (hierarchical pending)

The analysis directory required by `docs/results_plan.md` §30. Everything here
is regenerated from committed raw results at $0:

```
python results/final_analysis/scripts/build_master.py    # MASTER_RESULTS.csv + per-family CSVs
python results/final_analysis/scripts/analyze.py         # TABLES/, figure_data/, KEY_NUMBERS.json
python results/final_analysis/scripts/figures.py         # FIGURES/ (PGFPlots -> PDF, PNG, SVG)
python results/final_analysis/scripts/write_reports.py   # RESULTS_SUMMARY.md, CLAIM_EVIDENCE.md
```

## Start here
- **`RESULTS_SUMMARY.md`**: the combined current-results report, in plain
  English and with the full tables.
- **`CLAIM_EVIDENCE.md`**: the claim-to-evidence matrix (§25).
- **`BOOTSTRAP_NOTE.md`**: what the bootstrap is and why it is used (a
  write-up aid).
- `docs/adversaries.md` (repo root): the authoritative attacker names and
  definitions.

## Data (full precision; §1)
| file | contents |
|---|---|
| `MASTER_RESULTS.csv` | one row per unit × attacker × condition (2,366 rows), with every metric, scorer count, covariate, completion / RBNC / repair / retry status, token use and cost |
| `HEADLINE_J.csv`, `GRID_J.csv`, `IDENTIFIER_J.csv`, `GAME_O.csv` | the master rows by family |
| `HIERARCHICAL.csv` | PENDING (not run, D13) |
| `KEY_NUMBERS.json` | every summary number the reports quote |

## Tables (`TABLES/`: each as .csv at full precision, .md and .tex booktabs)
| table | contents |
|---|---|
| `table_A_design` | Table A: corpus and design summary |
| `table_B_headline_J`, `_B2_headline_paired`, `_B3_headline_distribution` | Table B: headline J, paired attacker comparisons, pool-level distribution |
| `table_C_grid_J`, `_C2_grid_mechanics`, `_C3_grid_paired`, `_C4_grid_attacker_paired`, `_C5_decomposition` | Table C: grid J, mechanics (§13), strategy / granularity paired comparisons (§7–9), attacker comparison, linkage-vs-order (§14) |
| `table_D_game_O`, `_D2_O_sonnet_vs_floors`, `_D3_O_grid_paired` | Table D: game O |
| `table_E_identifier_J`, `_E2_identifier_rule`, `_E3_identifier_membership` | Table E: identifier J, the frozen ±0.10 decision, and the exploratory membership-beyond-schema diagnostic |
| `table_F_hierarchical` | Table F: pending, plus the frozen oracle ceiling (DIAGNOSTIC CEILING — NOT AN ATTACKER RESULT) |
| `table_G_resource`, `_G2_completion`, `_G3_batches` | Table G: resources, completion / RBNC (replaces Figure 9, D13), every batch |
| `table_H_headline_vs_grid` | headline vs grid reference cell (§15, unpaired) |
| `table_R_relationships` | Spearman associations for length, fragment count, fragment size and resources (§10–12, 17–18) |
| `table_I_error_taxonomy`, `_I2_error_examples` | error taxonomy (§19) and quantile-rule examples |

## Figures (`FIGURES/`; data in `figure_data/`)
Each figure N has `figN.pdf` (vector), `figN.svg`, `figN.png` (preview),
`figN_body.tex` (the PGFPlots picture, which reads its CSV from
`\figdatadir`), `figN.tex` (the standalone build), `figN_figure.tex` (a
manuscript figure environment with the PGFPlots body) and `figN_graphic.tex`
(the same via `\includegraphics`). The PNG, PDF, SVG and LaTeX all come from
the same CSV; no plotted value is typed anywhere.

| figure | content |
|---|---|
| 1 | headline J attacker comparison with pool-level points, including the post-hoc exploratory embedding attacker (†); hierarchical pending |
| 2 | grid J, all 9 cells: Sonnet, Memon-inspired, embedding (†, post hoc) and the analytic baseline |
| 3 | linkage F1_L vs direction accuracy q by condition and attacker (embedding †: read along F1_L, its primary comparison) |
| 4 | game O Kendall τ by condition; Sonnet vs Jaccard floors |
| 5 | identifier J: attackers (embedding † post hoc) against the analytic and schema-aware baselines; the ±0.10 rule |
| 6 | document length vs reconstruction (J and O) |
| 7 | fragment count vs reconstruction (J and O) |
| 8 | fragment size vs reconstruction (J and O) |
| 10 | resource scaling: fragments vs output tokens of the answering call; the RBNC |
| 9 | replaced by `TABLES/table_G2_completion` (one RBNC in the study; D13) |

## Scripts (`scripts/`)
`build_master.py`, `analyze.py`, `figures.py`, `write_reports.py`.
Upstream runners: `runs/final_run_steps123.py`, `runs/final_run_steps45.py`,
`runs/final_free_attackers.py`, `runs/final_o_floors.py`,
`runs/memon_sha256_repro.py`, `runs/final_embedding_attacker.py` (post-hoc exploratory, D14).

† **Post-hoc exploratory.** The embedding attacker appears in the attacker
tables and figures alongside the statistical and LLM attackers, always marked,
and never as a prespecified or confirmatory attacker. It was motivated by the
observed Memon-inspired / Sonnet gap, then fully designed and frozen before
its own evaluation, with no final-data tuning and no model selection from its
scores. This is its first complete result. F1_L is its primary comparison.

## Related records
- Uncertainty method, the schema-advantage clarification and the SHA-256 fix:
  `docs/RUN_DECISIONS.md` D13.
- The SHA-256 reproducibility report:
  `results/audit/memon_sha256_reproducibility.md`.
- The embedding adversary: its design (`docs/embedding_adversary_design.md`),
  RUN_DECISIONS D14 and addenda, the smoke test
  (`results/audit/embedding_smoke.json`) and the final run
  (`results/final_embedding/`).
