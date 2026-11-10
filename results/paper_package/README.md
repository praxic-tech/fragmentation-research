# Figure and table package

Drop-in figures and tables for the paper. **Copies only** — this directory is
assembled by `build_package.py` from the generator outputs and is never edited
by hand, so it cannot disagree with them.

## Rebuild

```bash
Rscript results/paper_figures_r/make_all.R      # figures, then validation
python  results/paper_tables/make_tables.py     # tables
python  results/paper_package/build_package.py  # this package
```

`make_all.R` ends in `validate_figures.R`, which checks every figure's CSV
against the frozen source artifacts independently of the plotting code and
stops on any failure. No number in either directory is typed by hand.

## Using these in the paper

The paper is `acmart` with `\documentclass[sigconf]{acmart}`. Figures are sized
for a single column (3.33in = acmart sigconf's 241.14749pt) and set in Linux
Biolinum, the template's own sans, at 8pt axis titles and 7pt ticks.

```latex
\begin{figure}[t]
  \includegraphics{fig6_granularity_gradient.pdf}
  \caption{...}\label{fig:gradient}
\end{figure}
```

Tables are `table*` environments that span both columns and carry their own
caption, label and notes; `\input{}` them directly. Each shrinks to
`\textwidth` only if it is wider than the page, and is never enlarged.

**Text in the figure PDFs is outlines, not selectable text.** `pdffonts` lists
no fonts at all, which satisfies any embedding requirement trivially, but the
text cannot be selected, searched or read by a screen reader. This is a Windows
limitation, not a choice: see the Fonts section of
`results/paper_figures_r/README.md`. Rebuilding on Linux or macOS produces real
embedded text with no other change.

## Figures

| # | File | Placement | Width | Status | Shows |
|---|---|---|---|---|---|
| 1 | `fig1_headline_attackers.pdf` | Main | 1 col | Prespecified; embedding row post hoc | The generative attacker reconstructs far more than the tested statistical and similarity attackers |
| 2 | `fig2_grid_reconstruction.pdf` | Main | 1 col | Prespecified | Reconstruction across nine strategy x granularity cells |
| 3 | `fig3_linkage_vs_ordering.pdf` | Main | 1 col | Prespecified | The joint score split into linkage and conditional ordering |
| 4 | `fig4_identifiers.pdf` | Main | 1 col | Prespecified; D11 baselines | Structured identifiers behave qualitatively differently from prose |
| 5 | `fig5_single_token.pdf` | Main | 1 col | POST-HOC EXPLORATORY (D16) | Single-token cuts drive null-adjusted joint reconstruction to about its random-shuffle reference |
| 6 | `fig6_granularity_gradient.pdf` | Main | 1 col | POST-HOC EXPLORATORY (D16, D18) | Five cuts of identical text: observed against the random-shuffle reference, and what it means in words |
| A | `figA_gameO_vs_gameJ.pdf` | Appendix | 1 col | Prespecified | Ordering with membership given is much easier than joint recovery |
| B | `figB_resource_scaling.pdf` | Appendix | 1 col | Prespecified; single-token points post hoc | Output grows with fragment count, but fragment count does not determine completion |
| C | `figC_token_raw_vs_null.pdf` | Appendix | 1 col | POST-HOC EXPLORATORY (D16) | What A_VJ near zero means in raw terms |

Each figure ships `.pdf` (vector, for the paper), `.png` (600 dpi), `.svg`,
and `.csv` holding exactly the data frame it was drawn from.

## Tables

| # | File | Status | Shows |
|---|---|---|---|
| 1 | `table1_design.tex` | Prespecified | The design: corpora, cells, pools, units |
| 2 | `table2_headline_attackers.tex` | Prespecified; embedding row post hoc | Headline attacker comparison with 95% CIs |
| 3 | `table3_grid.tex` | Prespecified | The nine-cell grid |
| 4 | `table4_gameO.tex` | Prespecified | Game O: ordering with membership given |
| 5 | `table5_identifiers.tex` | Prespecified; D11 baselines | The structured-identifier arm |
| 6 | `table6_single_token.tex` | POST-HOC EXPLORATORY (D16) | Sentence against single-token cuts on identical excerpts, paired |
| 7 | `table7_resources.tex` | Prespecified | Resources, completion and cost |
| 8 | `table8_gradient.tex` | POST-HOC EXPLORATORY (D16, D18) | The five-point granularity gradient, with its random-shuffle reference per arm |
| 9 | `table9_adjacency.tex` | Post hoc, free reanalysis | Precedence against adjacency, and a random attacker that is a legal answer |

Each table ships `.tex` (booktabs, ready to `\input`) and `.md` (the same
content for review).

## Reading the post-hoc material

Figures 5 and 6 and Tables 6 and 8 are **post-hoc exploratory** (D16, D18) and
are labelled as such in their own captions and notes. They were designed after
results were seen; the claim restrictions in `docs/RUN_DECISIONS.md` carry over.
Table 9 is a free reanalysis of predictions already on disk.

## Two things to check before submitting

- The granularity material rests on `A_VJ`, the visible-text metric D16 froze
  as primary. Its random-shuffle reference is **not constant across arms** (it
  falls from 0.423 at the sentence cut to 0.141 at one word), so raw `V_J` is
  not comparable between arms and the normalised column is the one to read.
- PoPETs 2027 caps the main body at 12 typeset pages and desk-rejects
  over-length papers without appeal. Nine figures and nine tables will not all
  fit; the appendix figures (A, B, C) and the wider tables are the first to cut.
  Evaluations on purely synthetic data also require a well-marked paragraph
  arguing the results extrapolate, which the identifier arm needs.

`manifest.json` carries the same table plus a SHA-256 prefix for every file.
