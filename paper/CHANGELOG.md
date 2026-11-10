# `main.tex` — change log

`paper/main.tex` is the manuscript: the content of `reference_draft.tex`,
revised as instructed and moved into the PoPETs 2027 template.
`reference_draft.tex` is kept as the superseded earlier version.

Build state: **0 errors, 0 undefined citations or references, 2 overfull boxes
(3.5pt and 1.4pt), 17 pages total, main body pages 1–12.** `pdffonts` reports
`LinLibertineT` and `LinBiolinumTB`.

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
