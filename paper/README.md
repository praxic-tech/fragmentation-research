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

1. Figure 2 (grid) — Table 4 carries the same numbers, and dropping it would
   also clear one of the two float-only pages (see below).
2. Figure 3 (linkage against ordering) — overlaps Tables 4 and 7.
3. The grid section (§5.2) can lose its figure and keep its table.
4. §5.3 and §5.4 can be compressed, but the interpretation boundary §5.3
   establishes should not be dropped entirely.

## Float layout

Every float is declared at the top of the subsection that discusses it, which
is what keeps it on or next to that subsection's page. Do not move the
declarations back to the end of a subsection: LaTeX cannot place a float before
the point it is declared, and that was what pushed four pages' worth of figures
two to three pages past their text.

Pages 7 and 8 carry floats only. That is a float-to-prose ratio, not a setting:
§§5.2–5.4 declare five large exhibits against about 1.2 pages of prose, because
§5.3 is four lines and §5.4 is twelve. `dbltopnumber`, `dbltopfraction`,
`dblfloatpagefraction`, `floatpagefraction` and `dblfloatfix` were each measured
on this manuscript and every one of them produces a byte-identical PDF — once a
float is deferred, LaTeX drains the queue with `\@makefcolumn`, which consults
none of them. Writing those two subsections out, or taking cut 1 above, is what
clears it.

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
