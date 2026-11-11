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
underfull boxes, 12 pages total, main body pages 1–10.** Figures
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
and clearly marked appendices do **not** count. §7 currently ends on page 10,
so there are about two pages of margin for the rewrite.

Five of the original eight figures are already out of the paper: each repeated
a table that is still in the body, and none was cited in the prose. They are
untouched in `results/paper_package/figures/` with their data frames and build
scripts. To put one back, add a `figure*` to the `RESULTS EXHIBITS` block in
`main.tex` and run `python tools/check_layout.py`.

If the body ever needs to shrink further, the next candidates are Figure 1
(linkage against ordering), whose numbers are the F1_L and q columns of Table
4, and the two longest note blocks (precedence against adjacency, granularity
gradient), which run to about 2,000 characters each.

## How the exhibits are placed

Standard LaTeX floats and nothing else. Three rules:

1. **Every body exhibit is `[t]` only.** No `p` means no page of nothing but
   exhibits: a table can only sit at the top of a page that also carries text.
2. **All nine results exhibits are declared together, a section early** — the
   `RESULTS EXHIBITS` block in §4.2 of `main.tex`. A spanning float cannot
   print on the page it is declared on, so one declared under its own heading
   starts a page late and the lag compounds to three pages. Declared up front
   they are dealt out in order, one page top at a time, in step with the text.
   Their order in that block is the order they print in.
3. **Never `\FloatBarrier`.** One stray barrier between §5.4 and §5.5 caused
   every layout problem recorded in `CHANGELOG.md` revisions 5–9.

`\dbltopnumber` 3 and `\dbltopfraction` 0.75 cap a page top so there is always
text under the exhibits. Both body figures are wide and short (504pt, panels
side by side) because they are spanning floats; do not rebuild them at column
width.

### Check it after every prose edit

```bash
python tools/check_layout.py
```

It runs four checks and exits non-zero if any fails: every exhibit within one
page of its section, every body page carrying prose, nothing past the bottom
margin, every table on the page with its notes. The layout depends on how much
text sits between exhibits, so it **will** move when Sections 4–5 are
rewritten. If an exhibit drifts, reorder or move the `\input` lines in the
`RESULTS EXHIBITS` block.

Word counts and ink are both misleading here — a table's notes are hundreds of
words of small type, so an exhibit-only page measures as a full one. That is
why the checks count body paragraphs and exhibit-to-section distance instead.

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
