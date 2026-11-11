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

## How the exhibits are placed

**The body contains almost no floats.** The wide tables are set in place with
`cuted`'s `strip`, and the figures are centred material. A `table*` can only go
to a page top or bottom; with nine of them the float queue never emptied and
columns were left part-full — one at 33% of its height. Deleting every table
from the body was what proved it: all fourteen columns then filled to 99%.

Four exceptions stay real floats, set in `make_tables.py`'s `FLOAT_TABLES`, not
in the generated files: `table4_gameO` and `table5_identifiers`, which sit next
to each other and overrun the page as strips, and the two appendix tables. Do
not move that choice into the generated `.tex` files — a package rebuild has
already silently undone it once.

**Measure prose, not ink.** `tools/page_prose.py` reports how many body
paragraphs landed on each page; a page with none is an exhibit wall. Ink and
word counts both miss this, because a table's notes are hundreds of words of
6pt type and make an exhibit-only page measure as a full one. Every body page
currently carries running text, and the thinnest carries two paragraphs.

**Every table carries its own notes.** They were set outside the strip for a
while, so they would flow and fill columns, but a `cuted` strip lets its
contents split across a page and Table 2 ended up one page away from its
notes. `tools/page_attached.py` checks for that.

**The cost is page 8**, which carries three tables and no prose. Fifteen
arrangements were measured against four things at once — pages, content past
the margin, detached notes, pages without prose — and none has all four; see
`CHANGELOG.md` for the table. What would resolve it is not a setting: two note
blocks run to about 2,000 characters each, roughly a fifth of a page apiece,
and shortening those two is what makes their tables small enough to share a
page with text.

**Measure ink too, but second.** `tools/page_ink.py` reports how far down
each column the last ink sits; `tools/page_overflow.py` reports content past
the bottom margin. A table's notes are hundreds of words and tell you nothing
about how full a column is. Current state: every body column at 93–99% except
page 8's second at 63%.

**Do not tune the float parameters.** `dbltopnumber`, `dbltopfraction`,
`dblfloatpagefraction`, `floatpagefraction`, `topnumber`, `bottomnumber`,
`textfraction`, `!` overrides, `dblfloatfix`, the `review` option and
`\raggedbottom` were each measured on this manuscript and none of them changes
the result. Once a float is deferred LaTeX drains the queue with
`\@makefcolumn`, which consults none of them.

**Known imperfection:** the granularity figure's caption sits at the top of the
column after its panels. Centred material can break between a graphic and its
caption. `\nopagebreak[4]`, a minipage wrapper and three other declaration
points were each measured and all cost more elsewhere than they save.

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
