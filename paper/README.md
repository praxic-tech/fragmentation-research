# paper/

## `main.tex` is the manuscript

`reference_draft.tex` is the superseded earlier version, kept for comparison.
It was written by an AI assistant with access to the decision log, the frozen
results and the figure/table package, so the authors could see one possible
shape of the argument before writing their own. **None of its prose is intended
for the submitted paper.** The AI Use section says exactly this, and it is the
wording the submitted paper should carry if any of it is kept.

## Build

```bash
cd paper
pdflatex main && bibtex main && pdflatex main && pdflatex main
```

Current state: **0 errors, 0 undefined citations or references, 0 overfull or
underfull horizontal boxes, 14 pages total, main body pages 1–12.** Figures
resolve from `../results/paper_package/figures/` and tables from
`../results/paper_package/tables/`, so rebuilding the package updates the paper
with no edits here.

`pdffonts main.pdf` lists `LinLibertineT` and `LinBiolinumTB`, which confirms
the template really is Libertine/Biolinum. The figures carry their type as
outlines (showtext), so they contribute no font rows; that is expected and is
why the figure typeface matches the page.

## Page budget

PoPETs 2027 caps the main body at 12 typeset pages and desk-rejects
over-length papers without appeal. The mandatory sections (ethical
considerations, open science, AI use), the acknowledgments, the bibliography
and clearly marked appendices do **not** count. §7 currently ends about two
fifths down page 12, so there is roughly half a page of margin. If it needs to
shrink, cut in this order:

1. Figure 2 (grid) — Table 4 carries the same numbers, and dropping it is also
   what would clear the float-only page 8 (see below).
2. Figure 3 (linkage against ordering) — overlaps Tables 4 and 7.
3. The grid section (§5.2) can lose its figure and keep its table.
4. §5.3 and §5.4 can be compressed, but the interpretation boundary §5.3
   establishes should not be dropped entirely.

## Float layout

Figures 1, 2, 3 and 7 are **pinned** with `[H]` (the `float` package): they are
not floats, they are set where they are declared, with text before and after.
That is what keeps them in the prose and why Section 5 has no float-only page.
Figures 4, 5 and 6 float `[tb]` because they are too tall to pin where they are
cited — pinned, the `float` package breaks the column and leaves the rest of it
blank. Figure 8 is `[b]` so it cannot print above the References heading. Every
table is a `table*`, which cannot be set inline at all.

**A pinned figure is frozen.** If you rewrite the prose around one, rebuild and
look at the page: if the figure no longer fits in what is left of the column,
the column breaks early and you get a hole. Move the `\begin{figure}[H]` to a
different paragraph boundary, or give that one figure `[tb]`.

Do not rebuild Figure 3 at `page_width`. Every figure in the package is one
column, 239pt; as a `figure*` Figure 3 could only be set at a page top or
bottom and it was the hardest float in the document to place.

`dbltopnumber`, `dbltopfraction`, `dblfloatpagefraction`, `floatpagefraction`,
`!` placement overrides and `dblfloatfix` were each measured on this manuscript
and every one of them produces a byte-identical PDF — once a float is deferred,
LaTeX drains the queue with `\@makefcolumn`, which consults none of them.
Pinning, not tuning, is what fixed this.

What is left: a hole in the first column of page 8, where LaTeX ends the column
to give the top of column 2 to two figures, and about half of page 13. Page 13
is the appendices: Tables 9 and 10 can only sit at a page top so they go to
page 14, and Appendix B is currently one sentence and a TODO. The verbatim
prompts fill that space.

## What is deliberately missing

Fields marked `FIXME` in `refs.bib` are genuinely unresolved, not placeholders
to be filled from memory. They live in `annote`, which no ACM style prints —
they were in `note`, which ACM-Reference-Format **does** print, and the audit
trail was appearing in the typeset bibliography. Do not rename the field back.
See `docs/BIBLIOGRAPHY_SOURCE_AUDIT.md` for the claim-by-claim verification
status of every source, including which ones must not be cited for specifics.

`\TODO{...}` marks every place a number or fact is not in the frozen artifacts:
author details, repository URL, IRB language, release licence, the verbatim
prompts, and the confirmation that the synthetic-data paragraph says what the
authors want it to say.

## Claims the paper deliberately does not make

Recorded here because they are easy to reintroduce while rewriting:

- Not first to mixed-source reconstruction (2006 and 2020 precede it).
- Not first to LLM-driven reconstruction or to a granularity study (2026).
- Not a discovery that fragmented data can remain linkable (2014 proves it).
- Not a lower bound on classical statistical attackers — the tested baselines
  bound nothing about the attainable frontier.
- Not a safe fragment size, and the integer widths tested must not be
  interpolated.
- `F1_J = 0.723` is **not** "72% of the document reconstructed"; the
  corresponding adjacency score is 0.287.

Attacker names follow `docs/adversaries.md` exactly. Never "Memon" alone, never
"pre-LLM state of the art", and the dropped hierarchical attacker is never
tabulated.

## Scripts here

`fix_floats.py` sets each figure's float type from the figure's own native
width and strips `width=` overrides, so a 239pt figure is never magnified to
full text width. It is safe to re-run after the figure package is rebuilt.
