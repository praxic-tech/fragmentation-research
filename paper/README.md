# paper/

## `reference_draft.tex` is a reference model, not the manuscript

It was written by an AI assistant with access to the decision log, the frozen
results and the figure/table package, so the authors can see one possible shape
of the argument before writing their own. **None of its prose is intended for
the submitted paper.** Read it, disagree with it, then write your own. The AI
Use section of the draft says exactly this, and it is the wording the submitted
paper should carry if any of it is kept.

## Build

```bash
cd paper
pdflatex reference_draft && bibtex reference_draft && pdflatex reference_draft && pdflatex reference_draft
```

Current state: **0 errors, 0 undefined citations or references, 0 overfull
boxes, 11 pages.** Figures resolve from `../results/paper_package/figures/` and
tables from `../results/paper_package/tables/`, so rebuilding the package
updates the draft with no edits here.

`pdffonts reference_draft.pdf` lists `LinBiolinum` and `LinLibertine`, which
confirms the template really is Libertine/Biolinum and that the figure typeface
matches the page.

## Page budget

PoPETs 2027 caps the main body at 12 typeset pages and desk-rejects over-length
papers without appeal. The mandatory sections (ethical considerations, open
science, AI use), the acknowledgments, the bibliography and clearly marked
appendices do **not** count. At 11 pages total this draft is inside that, but it
is also not cut for argument quality — it was written to be complete rather than
short, as instructed. If it needs to shrink, cut in this order:

1. Appendix figure C and Table 1 (design) — the least load-bearing.
2. Figure A and Figure B — both support claims the text already makes.
3. The grid section (\S5.2) can lose its figure and keep its table.
4. \S5.8 (precedence against adjacency) can compress to a paragraph, but the
   interpretation boundary it establishes should not be dropped entirely.

## What is deliberately missing

Fields marked `FIXME` in `refs.bib` are genuinely unresolved, not placeholders
to be filled from memory. See `docs/BIBLIOGRAPHY_SOURCE_AUDIT.md` for the
claim-by-claim verification status of every source, including which ones must
not be cited for specifics.

`\TODO{...}` in the draft marks every place a number or fact is not in the
frozen artifacts: author details, repository URL, IRB language, release licence,
and the confirmation that the synthetic-data paragraph says what the authors
want it to say.

## Claims the draft deliberately does not make

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
