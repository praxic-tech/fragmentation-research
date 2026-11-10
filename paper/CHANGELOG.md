# `main.tex` — change log

`paper/main.tex` is the manuscript: the content of `reference_draft.tex`,
revised as instructed and moved into the PoPETs 2027 template.
`reference_draft.tex` is kept as the superseded earlier version.

Build state after revision 5: **0 errors, 0 undefined citations or
references, 0 overfull or underfull horizontal boxes, 14 pages total, main body
pages 1–12** (§7 ends about two fifths down page 12; the mandatory sections,
acknowledgments, bibliography and appendices follow and do not count).
`pdffonts` reports `LinLibertineT` and `LinBiolinumTB`.

---

## Framing edits

- **Abstract rewritten to the eight-point order** (problem → games → metric
  decomposition → headline → adjacency qualification → identifier contrast →
  granularity → scoped conclusion). The prior-art concessions that ran across
  several sentences are reduced to one closing clause: the contribution is the
  measurement rather than a new reassembly algorithm.
- **Introduction restructured to the six-paragraph flow**, with the two hidden
  structures (membership, order) named explicitly before the games are
  introduced, and Game J identified as primary.
- **Two contributions, not a list of five.** The attacker comparison is stated
  as evidence for both rather than a contribution.
- **Scope sentence kept and tightened**: closed world, complete pool, known
  N = 7, one prose corpus, one generative attacker, not a deployment-level
  partial-compromise estimate.
- **Related Work compressed, not cut.** Each predecessor now gets what it
  establishes plus the one or two differences that matter. Repeated "we do not
  claim X" sentences removed; the concession is made once, in the Introduction
  and once per predecessor where it prevents a real misreading.
- **The Ciriani → De Capitani → us chain is stated explicitly** as the
  intellectual lineage, with the note that we do not claim semantic
  relationships are inherently impossible to formalise.

## Metric and baseline clarification

- **Added a worked example** in §3.5 (Scoring): four fragments `A B C D`
  predicted as `A C B D` preserves five of six precedence relations but only
  one of three true adjacent joins. This sits *before* Results, so the reader
  meets the distinction before meeting the number.
- Stated plainly that F1_J = 0.723 is **not** 72.3% verbatim reconstruction and
  **not** 72.3% correct adjacent joins.
- **Split the reference points into two named things** in a restructured §3.6:
  - *analytic one-bucket reference*, b_J = 0.149 — a trivial-strategy
    benchmark, explicitly **not chance, not a floor, and not a legal answer**
    under the exactly-seven-group contract;
  - *legal random attacker* — size-blind random seven-group partition,
    F1_J = 0.077, with the oracle-size variant at 0.088 reported separately and
    labelled attacker-favourable.
  - Recorded that 0.149 is roughly twice 0.077, so advantages normalised
    against b_J **understate** the margin. A_J is retained because that is how
    the study was prespecified.
- **`q` is defined once as the frozen micro average ΣC/ΣK** and stated to be
  conditional on the attacker's own correctly linked pairs, hence not the same
  quantity as Game O ordering accuracy. The macro mean (0.8206) appears
  nowhere.

## Results reordering

- **The interpretation now sits immediately after the headline number**, in the
  same subsection, as a bulleted side-by-side: one-shot (F1_J 0.723, F1_L
  0.882, q 0.792, adjacency F1 0.287, longest run 4.53) against legal
  size-blind random (F1_J 0.077, adjacency F1 0.004, longest run 1.13), plus
  the no-intact-pair counts. The intended reading is stated in one sentence.
- **The five-point granularity series is now the primary granularity result**
  (§5.6), with the binary sentence-versus-token edge case moved to
  Appendix G. The appendix keeps the full edge-case result, its paired
  statistics and the scorer explanation; the main text says the series extends
  it.
- **The resources plot moved to Appendix D.** The main text keeps the
  completion protocol, the non-completion rule, 651/652, and that
  non-completions are never scored zero.
- Game O promoted from a sub-point of the decomposition section to its own
  subsection (§5.4), using headline-only figures.

## Figure and table changes

- **The template's figure filenames do not exist** and were replaced with the
  validated package names. The template referenced `fig5_identifiers`,
  `fig6_single_token_edge`, `fig4_gameO_vs_gameJ`, `fig8_resource_scaling` and
  a commented-out `fig7_landscape`; the actual files are `fig4_identifiers`,
  `fig5_single_token`, `figA_gameO_vs_gameJ`, `figB_resource_scaling`. No
  landscape figure exists and none was invented.
- **Table 9 (adjacency and the legal random baseline) added to the headline
  subsection**, immediately after Table 2, so the adjacency numbers appear with
  the headline rather than later.
- **Table 8 (granularity series) placed with §5.6** as the primary granularity
  table.
- **Figure 6 panel (a) keeps raw V_J against the changing random-shuffle
  reference** rather than being converted to a flat zero line, as instructed;
  the caption states that the reference is not constant (0.423 → 0.141) and
  A_VJ is printed at each point. Join recall is quoted in the caption so it
  stays visible for the two-regime reading.
- **Figure 1's caption now names both references**, so the dashed b_J line
  cannot be read as chance.
- **Notation table converted to `table*`** — it overflowed a single column by
  39.7pt.
- `\bibliography{sample-base}` → `\bibliography{refs}`.

## Wording softened for causal and novelty precision

- "Disjointness did not remove the dependency" → "Disjointness did not remove
  enough content signal to prevent substantial reconstruction in the prose
  setting we tested."
- "The channel is the content itself" → "The results are consistent with
  fragment content providing a strong reconstruction channel", with an explicit
  statement that no experiment isolated *which* properties of content carry the
  signal, so entity continuity and chronology are not claimed as measured
  mechanisms.
- Identifiers: "Format leaks here; content does not" → "In this synthetic arm
  the schema structure remains directly exploitable while the tested
  content-based attackers do not recover record association." The paragraph
  noting that data type, schema, fragment form and signal structure all changed
  together is retained.
- "classical methods fail" and equivalents removed throughout; the text says
  *tested* statistical, lexical and embedding attackers, and states in §4.4
  that the Memon-inspired attacker is not a faithful reproduction and that the
  Jaccard orderers run on a sparse similarity signal.
- Gallé & Tealdi: "our fragments share nothing" → "our fragments form a
  disjoint partition and do not expose that guaranteed window-to-window
  overlap; individual words and entities can of course still recur across
  fragments, and at fine granularity they frequently do."
- Threat model no longer says the attacker sees "plaintext and nothing else";
  §3.3 lists what is given and what is denied as two explicit lists.
- Novelty language left at the narrow framing. No "first" claim of any kind.
- Granularity: no universal threshold. The wording is "in this controlled
  exploratory arm the transition occurs below roughly four words", immediately
  followed by the scope sentence.

## Numerical corrections

| Quantity | Was | Now | Why |
|---|---|---|---|
| Identifier `q` | 0.6266 | **0.631** | 0.6266 is the macro mean; the frozen convention is micro ΣC/ΣK = 0.6306 |
| Game O headline τ | 0.8239 | **0.7690** | the old value pooled headline with grid |
| Game O pair correctness | 0.9119 | **0.8845** | same pooling error |
| Game O contiguity | pooled | **exact 0.3249, run 0.2373, longest run 6.31** | headline-only |
| Legal random Game J | absent | **0.077 size-blind, 0.088 oracle-size** | new rows |
| Headline adjacency | absent | **0.287, longest run 4.53** | new |
| Development contact | "untouched" | **21 documents in 18 of 46 headline pools** | provenance correction |

Verified against the frozen artifacts while writing: grid F1_J range
0.498–0.801 and smallest A_J 0.422; Game O τ 0.724–0.943 across cells; 652
one-shot units with 651 complete and the one non-completion at 322 fragments;
identifier A_schema 90% CI [−0.162, −0.129]; and that "every headline document
recovered at least one correct adjacent pair" is **exactly** zero in all 46
pools, not a rounded mean.

## Deliberately not changed, and why

- **`anonymous` removed from the class options, as instructed.** The author
  block is now visible. A comment at the top of the file says to restore it
  before any anonymous submission; `review` is kept.
- **`popets.sty` is not on this machine**, so the `\usepackage{popets}` line is
  wrapped in `\IfFileExists` with local stubs for the three mandatory
  environments. The line itself is untouched and the guard is inert inside the
  real template. Build there before submitting.
- **The analytic one-bucket reference was not replaced**, per instruction — A_J
  was defined against it. Both roles are now explicit instead.
- **No threat-model schematic was added.** The instruction made it optional and
  conditional on space; the main body is already at the 12-page boundary, and
  the instruction said not to sacrifice text for it.
- **The single-token result and its scorer explanation were not removed**, only
  relocated to Appendix G with the full paired statistics.
- **`fig7_landscape` was not created.** It is commented out in the template, no
  such figure exists in the validated package, and the instruction forbids
  inventing results.
- **The 83% vs 86.7% Jaccard-sparsity conflict is unresolved**, so the text
  quotes neither number and says "a large majority of within-document pairs".
  That conflict still needs settling in the source documents.
- **`\TODO{}` markers left in place** for author details, the artifact URL, the
  provider's data-use terms, IRB language, the release licence, and
  confirmation that the synthetic-data paragraph says what the authors want.
  These are facts not present in the frozen artifacts and were not invented.
- **`reference_draft.tex` retained** rather than deleted, so the earlier
  version remains diffable.
- **Section numbering follows the template**, which differs slightly from the
  earlier draft. That was the instruction's intent (move into the template),
  and no argument was reordered beyond the Results changes listed above.

---

# Revision 2 — float sizing, author order, and a header bug

## Figure sizing (the visible problem)

**Six figures were being magnified 2.1x.** Eight of the nine package figures
are natively **239pt wide — exactly one acmart column**; only
`fig3_linkage_vs_ordering` is 504pt (genuine full width). They had been wrapped
in `figure*` with `width=\textwidth`, scaling a 239pt figure to ~504pt and
blowing the designed 7–8pt type up to roughly 16pt.

Fixed by `paper/fix_floats.py`, which reads each figure's own page width with
`pdfinfo` and sets the float type from it, then drops the `width=` override so
every figure renders at its designed size:

| figure | native width | float |
|---|---|---|
| fig3_linkage_vs_ordering | 504pt | `figure*` |
| all eight others | 239pt | `figure` |

Consequences: **17 pages → 13**, and the main body moved from pages 1–12 to
**pages 1–9**, giving roughly three pages of slack against the 12-page cap
instead of sitting on the boundary. Figure type now matches the body text.

## A bug that corrupted every running head

`\acmConference` takes three mandatory arguments, `[short]{name}{date}{venue}`.
The template called it with one, so it silently swallowed the following
`\settopmatter{...}` group and typeset the literal string
`printacmref=false,printccs=false,printfolios=true` into the running head of
every page. `\settopmatter` now comes first and `\acmConference` is given its
arguments. The running head reads `Shards of Meaning` / `PoPETs` as intended.

This was inherited from the supplied template, not introduced here, and will
recur in any build where `popets.sty` is absent.

## Author order

**Aiden J. Tejada is now first author**, followed by Michael Anyaegbunam and
Mohammed Arafat Nadaf. `\shortauthors` updated to `Tejada et al.`

## Checked and deliberately left alone

- **Bold figure and table captions are acmart's own default** for this format
  (`\captionsetup[figure]{labelfont={bf,small}, textfont={bf,small}}` in
  `acmart.cls`), not something introduced here. Unchanged.
- The two sub-4pt overfull boxes (3.5pt, 1.4pt) remain; both are below the
  threshold worth rewording around.

Build after revision 2: **0 errors, 0 undefined citations or references, 2
overfull boxes, 13 pages, main body pages 1–9.**

---

# Revision 3 — post-hoc results out of the appendix, and the A–H skeleton cut

Two problems, both introduced here rather than inherited.

## The post-hoc result was stranded behind the references

Revision 1 moved the binary single-token experiment to an appendix, following
the instruction to "consider moving the old binary single-token figure to the
appendix... **only make this change if it improves layout**." It did not
improve layout: it put a real result behind the bibliography and left page 13
two-thirds blank.

**The result is now reported in the main body**, as a short closing paragraph
of §5.6 ("The binary arm this series extends"), with its full numbers: A_VJ
0.588 → 0.016, paired difference 0.572 [0.539, 0.607], 20/20 pools, sign test
p = 1.9e-06, raw V_J 0.762 vs null 0.423 and 0.155 vs 0.141, and A_VL 0.777 →
0.159. Only the supporting figure and per-pool table remain in an appendix,
which is where supporting material belongs.

Appendix placement after the references was **not** the bug: acmart puts
appendices there, and the supplied template says so explicitly.

## Eight appendices, five of which said nothing

The template's appendix outline comments were converted into real numbered
sections in revision 1. The result was A–H, where five contained a single
descriptive sentence and two displayed as bare headings because their floats
had drifted to the next page. That reads as scaffolding, not a paper.

**Removed** (they described material that does not exist yet):

- Full Grid Results and Paired Comparisons
- Visible-Text Scorer, Nulls and Per-Pool Data
- Audits and Controls
- Development History and Screening

Those are still worth writing. The plan is preserved here so it is not lost:
strategy and granularity paired tables and per-cell fragment mechanics; the
scorer definition, its tests and the predicted-structure robustness null; the
Jaccard identifier-order leak correction with before/after, the masking
side-channel control and corpus fidelity checks; and the screening history,
the development-contact inventory for the 21 documents in 18 headline pools,
and the decomposed attacker that was designed but never run.

**Kept, now four appendices:** A Prompts (still a marked TODO, and required
for the open-science claim), B Game O Details, C Completion/Resources and
Cost, D Single-Token figures and per-pool data.

**Appendix D given real content** rather than one sentence and two floats: the
per-arm null means (V_J 0.423 vs 0.141; V_L 0.503 vs 0.317) and why that makes
the normalized value the one to quote; the two non-generative attackers, which
were not designed for single-token input (Memon-inspired 0.043 → −0.067,
17/20; embedding 0.104 → −0.090, 20/20); the three pools where raw and
normalized scores disagree in sign for Memon-inspired; and q_V 0.860 vs 0.376
with a pointer to why it does not decompose the score.

**`figC_token_raw_vs_null` dropped from the paper.** It duplicates panel (c)
of Figure 8, and the values it shows are now stated in the main text. It
remains in the figure package if a reviewer asks.

Build after revision 3: **0 errors, 0 undefined citations or references,
1 overfull box (3.5pt), 13 pages, main body pages 1–9.**


---

# Revision 4 — Game O and the post-hoc arm back beside their text

Recorded in commit `a0dccef`; the detail is in that commit message. In short:
revision 3 moved the post-hoc *prose* into the body and left its figure and
table in an appendix, and Game O had the same split. Both were brought back to
their own sections, the two emptied appendices were deleted, and the main body
grew from pages 1–9 to pages 1–12.

---

# Revision 5 — the PDF read page by page

Every page of the built PDF was rendered and read. These are what that found.
Nothing here changes a number, a claim or a sentence of argument.

## Three section headings with nothing under them

§3.2 Notation, Appendix A and Appendix C each consisted of a heading and a
float. The float deferred to the following page, so the heading printed alone
over the next heading. Each now opens with a sentence that says what its
exhibit contains and refers to it by number, which is what makes the heading a
section rather than a label.

## Figure 2's caption described a different figure

The caption promised panels (a) and (b), a full-length headline row, the
Memon-inspired attacker and the post-hoc embedding attacker. The figure has one
panel, nine grid rows and one attacker plus a baseline tick — confirmed against
`fig2_grid_reconstruction.csv`, the data frame the figure ships. Rewritten from
that file. Also in §5.6, "Panel~(b)" named no figure at all; it is now
Figure~\ref{fig:gradient}(b).

## The bibliography was printing its own audit trail

Every entry's `note` field carried its verification status from
`docs/BIBLIOGRAPHY_SOURCE_AUDIT.md`, and ACM-Reference-Format **prints**
`note`. The typeset bibliography was publishing "SECONDARY ONLY — THE PRIMARY
HAS NOT BEEN READ", "FIXME: volume, number and pages are not on the preprint"
and "DO NOT cite the PUP mechanism" to the reader. Moved to `annote`, which no
ACM style emits. The audit trail is unchanged in `refs.bib`; it is now out of
the PDF.

## Table notes were ASCII where the body was maths

The notes and row labels are shared with the Markdown output, so they were
written `F1_J`, `b_J`, `A_VJ`, `q_V`, `A_schema`. In LaTeX they printed with
literal underscores against a body that sets the same symbols as maths.
`make_tables.py` now applies `tex_math()` after `tex_escape()` to captions,
cells and notes, and the table headers set F1 upright (`\mathrm{F1}_{J}`) to
match `\FJ` in the body. `prompt_J` is a request-spec name, not a metric, so it
is set in `\textsf`, not maths.

## \appendix was issued about a hundred lines early

It sat in front of the acknowledgments, so the mandatory sections and the
bibliography were formally inside the appendix. It worked only because those
sections are starred. Moved to where the appendices actually start.

## Four body pages carried no text

Pages 7, 8, 10 and 11 of the previous build were float pages, two of them
roughly half blank, while figures sat two to three pages from the text that
cited them. Two causes, both fixed:

- **Every float was declared at the end of its subsection.** LaTeX cannot place
  a float before the point it is declared, so the top of the page the
  subsection starts on was never a candidate. Each float group is now declared
  immediately after its subsection's `\label`.
- **Placement was `[t]` only**, so a figure that missed a column top had nowhere
  to go but the deferred queue. One-column figures are now `[htb]` and the
  spanning floats `[tb]`, and acmart's float separations are tightened, which
  is worth most of a text line per float at this density.

Two float pages remain, 7 and 8. **They are not a setting.** dbltopnumber,
dbltopfraction, dblfloatpagefraction and floatpagefraction were each measured
by building the paper once per value, and every one produces a byte-identical
PDF, as does removing `dblfloatfix`: once a float is deferred, LaTeX drains the
queue with `\@makefcolumn`, which consults none of them. The cause is the ratio
— §§5.2–5.4 declare five large exhibits against about 1.2 pages of prose,
because §5.3 is four lines and §5.4 is twelve. Either writing those two
subsections out or dropping one of the two overlapping exhibits would clear it;
`paper/README.md` already ranks Figure 2 first in the cut order, since Table 4
carries the same numbers. That is an authors' decision, not a layout one.

## Smaller things

- The running head read "PoPETs, ," because `\acmConference` was given empty
  date and venue arguments. They now carry `YYYY` and `Issue X`, matching the
  `\acmYear` and `\acmNumber` placeholders already in the preamble. The real
  template overwrites all of them.
- The one remaining 3.5pt overfull line came from "Memon-inspired": TeX will
  not hyphenate either half of a word that already contains a hyphen. 1em of
  `\emergencystretch` absorbs it without loosening anything that already fits.
  The build now reports no overfull or underfull horizontal boxes in the body.
- The appendix figure is pinned `[b]`. With a top placement it floated to the
  top of the page the bibliography starts on and printed above the References
  heading.
- `paper/patch_floats.py` deleted. It was a one-off that has already been
  applied, and re-running it would load `placeins` with `[section]`, which
  acmart refuses to compile.

Build after revision 5: **0 errors, 0 undefined citations or references, 0
overfull or underfull horizontal boxes, 14 pages, main body pages 1–12.**
