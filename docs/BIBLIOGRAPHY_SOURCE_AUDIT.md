# Bibliography source audit — for author verification before drafting

**Purpose.** A claim-by-claim verification sheet, not a literature summary. Every
row states what the repo currently claims, where the claim lives, where in the
source it should be supported, and how strongly it is actually verified. Written
so the author can open each source and check it personally.

**Built:** 2026-11-09. **Auditor:** repo agent. **Status:** nothing here is
author-verified yet; see the sign-off checklist at the end.

**Scope note, read this first.** The instruction was to start from the repo's
bibliography rather than from memory. **There is no bibliography file in the
repo, and no manuscript.** `find` over the working tree returns no `.bib` and no
manuscript `.tex` — only generated figure fragments under
`results/final_analysis/FIGURES/`. The 16-entry `reference_draft.bib` and the
`main.tex` draft existed only in a session scratchpad, which has since been
cleared; both are gone. Those 16 entries were written from memory and never
verified against sources, so no verified work was lost — but it does mean this
audit is assembled from the repo's *prose* claims, which is the complete set of
external works the repo substantively relies on.

**Evidence held locally.** PDFs and extracted text for seven of the eight
priority papers are at
`C:\Users\aiden\AppData\Local\Temp\claude\C--Users-aiden-Desktop-projects-fragmentation\30d9133a-c63a-4ede-9208-c23613322fc2\scratchpad\relwork\pdfs`.
That is temp space and will not survive indefinitely. SHA-256 prefixes are
recorded per paper below so a re-download can be checked against what was read.
These are publisher PDFs and are deliberately **not** committed to the repo.

---

## Audit status summary

| Paper | Current citation role | Verification status | Novelty-critical? | Action needed |
|---|---|---|---|---|
| Shanmugasundaram & Memon 2003 | classical single-document reassembly precedent; origin of the Memon-inspired attacker's mechanism | **PRIMARY VERIFIED** | Yes — baseline justification | Get ACSAC page numbers; close packet open-item #4 |
| Ciriani et al. 2010 | motivates fragmentation for association privacy | **PRIMARY VERIFIED** | Motivation | Confirm `22:1--22:33` page form |
| De Capitani di Vimercati et al. 2014 | disjointness is necessary but not sufficient; the formal statement of our question | **PRIMARY VERIFIED** (preprint) | **Yes — strongest motivation** | Get volume/issue/pages from IEEE |
| Memon & Pal 2006 | mixed-source (k-file) reconstruction precedent | **SECONDARY ONLY** | **Yes — kills a novelty claim** | **Obtain IEEE primary before citing specifics** |
| Paixão et al. 2020 (Pattern Recognition) | mixed-source *text*-document reconstruction precedent; metric contrast | **PRIMARY VERIFIED** | **Yes — kills a novelty claim** | None blocking |
| Paixão et al. 2020 (CVPR companion) | scale/speed claim; 20-mixed-page instance | **PRIMARY HELD, DETAIL UNVERIFIED** | Supporting | Verify whether 505 shreds is one mixed instance |
| ShredBench 2026 | prevents claiming first LLM fragment reconstruction or first granularity study | **PRIMARY VERIFIED** | **Yes** | Verify which model/subset gives NED 0.33 |
| Lermen et al. 2026 | establishes modern LLM semantic linkage; precedent for closed-world design | **PRIMARY VERIFIED** | Yes — novelty + limitation | None blocking |
| Gallé & Tealdi 2015 | observation-model contrast for tiny textual units | **METADATA ONLY** | Yes — constrains the 1-word claim | **Obtain ACM primary**; one circulating number is unverified |
| Espiritu & Cash 2026 | *not currently cited* — adjacent plaintext-recovery work | **METADATA ONLY** | Possibly | Decide whether to cite |
| OrderProbe 2026 | *not currently cited* — semantic competence ≠ exact ordering | **METADATA ONLY** | No | Optional one-line cite |

**Counts.** 10 works audited (8 priority + 2 newly identified). **6 primary
verified** (2003, Ciriani, De Capitani, Paixão PR, ShredBench, Lermen) plus
Paixão CVPR primary-held-with-one-unverified-detail. **1 secondary only**
(Memon & Pal 2006). **3 metadata only** (Gallé, Espiritu & Cash, OrderProbe).

---

# Shanmugasundaram & Memon 2003 — *Automatic Reassembly of Document Fragments via Context Based Statistical Models*

**Full citation:** Kulesh Shanmugasundaram and Nasir Memon. *Automatic Reassembly
of Document Fragments via Context Based Statistical Models.* 2003. 8 pages.
Polytechnic University, Brooklyn NY. **Page numbers not in the PDF — unresolved.**

**Stable primary source:** https://www.acsac.org/2003/papers/97.pdf (served from
the ACSAC 2003 proceedings path; local sha256 `e01b513b895358b7`). Venue should
be confirmed against the ACSAC/IEEE record before the bib entry is final — the
PDF itself names no venue.

**Current verification status:** **PRIMARY VERIFIED** (full text read).

**Where our repo cites or discusses it:**
- `docs/adversaries.md` — header warning block; "What comes from
  Shanmugasundaram & Memon" and "What is ours, a substitution" lists; wording
  rules section.
- `docs/RELATED_WORK_NOTES.md` §1 (five-prompt notes, reviewer answer).
- `docs/PRIOR_ART_CODE_COMPARISON.md` §0, §3 comparison table.
- `docs/paper_section3.md` line 79–80 (with a dated 2026-09-13 correction).
- `docs/PAPER_WRITING_PACKET.md` lines ~290–294 and open-item #4 (line 1502).

**Why we cite it:** It is the origin of the mechanism our Memon-inspired
baseline borrows — judging whether one fragment follows another using a
statistical model of the text trained on the fragments themselves — and the
historical predecessor to Game O.

## Claims our paper currently makes about this source

| # | Claim we currently make | Where we make it | Source location that should support it | Verification status |
|---|---|---|---|---|
| 1 | Reassembles fragments of a **single** document | adversaries.md; RELATED_WORK §1 | §2.1 problem statement; §1 "we consider reassembling a single document" | **VERIFIED** |
| 2 | Adjacency scored by a context model built from the fragments themselves | adversaries.md "What comes from" | §2.3 "build an n-order context model … by accumulating the context models of individual fragments"; §3.1 | **VERIFIED** |
| 3 | Uses PPM with PPMC blending across orders 0..k | adversaries.md substitution list | §3.1 | **VERIFIED** |
| 4 | Reassembly is a maximum-weight Hamiltonian path, intractable, solved by heuristic | PRIOR_ART §3 | §2.1 and §2.2; §3.2 α-β tree pruning | **VERIFIED** |
| 5 | **Assumes a known first fragment**, justified by file headers | adversaries.md header; PRIOR_ART §1, §3 | §3.2 "Assuming we know the first fragment … most files have headers" | **VERIFIED** |
| 6 | Explicitly names "Collating" (grouping mixed-source fragments) and defers it | RELATED_WORK §1 prompt 4 | §1 three-step model, step 2; §4 conclusion future work | **VERIFIED** |
| 7 | Their metric is a local adjacent-pair rate with no membership term | adversaries.md; PRIOR_ART §4 | §3.3 "the number of adjacent fragments in the reassembled documents that are in fact adjacent in the original" | **VERIFIED** |
| 8 | Fragments are byte-level, 100–200 per document | RELATED_WORK §1 | §3.3 "randomly split into several pieces (100 - 200)" | **VERIFIED** |
| 9 | Unformatted plain text was among their hardest types | RELATED_WORK §1 | Table 2 (26.4–31.0%) vs logs (57.7–68.0%); Fig 4; Fig 5 compression-ratio cross-check | **VERIFIED** |
| 10 | Assumes lossless recovery (no missing fragments) | RELATED_WORK §1 | §2.1 "We assume fragments are recovered without loss of data" | **VERIFIED** |
| 11 | Analyst-in-the-loop; converges in 4–10 iterations | RELATED_WORK §1 | §3.3 Table 3 | **VERIFIED** |
| 12 | Context orders 3–5 performed best | RELATED_WORK §1 | §3.3 and Fig 6 | **VERIFIED** |
| 13 | Our Memon-inspired attacker is **not faithful**; substitutions are a fixed-order smoothed char model, TF-IDF grouping, tanh weighting, local search, no anchor | adversaries.md | n/a — claim about our code (`adversaries/memon.py`, `memon_joint.py`, `memon_linkage.py`, `harness/order_from_sim.py`) | **VERIFIED against our code** |

### Conflict found, already resolved — record it

`docs/paper_section3.md` line 80 carries a dated self-correction: the line
previously called the statistical attacker "the classical content-based
reassembly approach … after Shanmugasundaram & Memon 2003 — **the pre-LLM state
of the art**", and the correction notes that `B_stat` is only the TF-IDF grouper
and that "state of the art" was an overclaim. `docs/adversaries.md` now bans the
phrase outright. **No live conflict; the older framing is retracted in place.**
Verify the retraction survives into the manuscript.

### Numerical discrepancy to resolve

`docs/PAPER_WRITING_PACKET.md` line ~293 says word-bigram Jaccard is "exactly 0
for **86.7%** of within-document pairs". `adversaries/memon_linkage.py`'s
docstring says the Jaccard matrix is "~**83%** exact zeros". These may be
different quantities (within-document pairs vs all pairs) or one may be stale.
**Both numbers are load-bearing** for the "the lexical baselines are at chance
because the signal is sparse" caveat. Resolve before either appears in print.

## What the paper actually does

**Input / observation channel:** the complete set of byte-level fragments of one
file, recovered losslessly. Statistical model trained on those fragments only;
no external corpus.

**Given information / anchors:** the identity of the first fragment (file
headers). No source-count problem — there is one source by construction.

**Unknowns it must infer:** the permutation of the fragments.

**Output:** the top-β near-optimal orderings, presented to a human analyst.

**Metric:** fraction of adjacent pairs in the reassembly that are truly
adjacent. Not a permutation score; no membership term.

**Main result (directly verified, Table 2, single pass, top-β ∈ {5,10,15,20}):**
log files 57.7 / 58.0 / 58.7 / 68.0 %; executables 30.0 / 30.7 / 33.4 / 33.4 %;
binary files 23.4 / 24.6 / 28.4 / 28.4 %; unformatted text 26.4 / 28.3 / 29.0 /
31.0 %. Table 3 iterations to convergence: logs 4, source 6, executables 9,
binary 10, unformatted 10.

## Comparison to our paper

| Dimension | Prior paper | Our paper | Material difference? |
|---|---|---|---|
| Data type | byte-level disk blocks, mixed file types | plaintext linguistic units | **Yes** |
| Source count | one document | 7, known | **Yes** |
| Membership known? | n/a (single source) | hidden | **Yes** |
| Ordering known? | hidden | hidden | No |
| Structural anchors | known first fragment (header) | none | **Yes** |
| Observation channel | byte continuity across the cut, via PPM | language only | **Yes** |
| Output | top-β orderings for an analyst | one partition with order, autonomous | **Yes** |
| Metric | adjacent-pair rate | F1 over precedence pairs, factored into linkage × conditional ordering | **Yes** |
| Privacy/security question | forensic recovery capability | privacy leakage under fragmentation | **Yes** |

**What this paper takes away from our novelty:** Statistical text-fragment
reassembly is established, and so is the *idea* of scoring adjacency with a
compression-style model. We cannot claim fragment reassembly, adjacency
scoring, or the graph formulation. It also removes any claim that our
statistical baseline represents "the classical approach" — ours is a
substitution on three axes and lacks an input the original requires.

**What remains different / unresolved:** membership is unknown in Game J and is
the step this paper names and defers; there is no anchor; the units are
linguistic rather than byte-level; and the metric separates linkage from
ordering, which theirs cannot.

**Claims we may safely make:** "Classical work demonstrated statistical
reassembly of a single document's fragments, and identified the grouping of
mixed-source fragments as a distinct prior stage that it did not address."
"Our Memon-inspired attacker takes the context-model idea from this work; it is
one tested statistical baseline, not a faithful implementation."

**Claims we must not make:** "the pre-LLM state of the art". "Prior work left
mixed-source reconstruction unsolved" (2006 closed it). "Our baseline is a
lower bound on classical performance." Any table placing their percentages
beside F1_J / F1_L / q.

## My manual verification checklist

- [ ] Confirm the venue and page numbers from the ACSAC/IEEE record (the PDF names neither).
- [ ] Confirm §1 step 2 "Collating" and the §4 future-work sentence read as we quote them.
- [ ] Confirm §3.2 states the first fragment is assumed known, and the header justification.
- [ ] Confirm §3.3's accuracy definition is adjacent-pair, not permutation-level.
- [ ] Confirm Table 2's four rows against our transcription above.
- [ ] Confirm the paper assumes lossless recovery (§2.1).
- [ ] Note for yourself: eq. (2) as printed says "maximizing" a sum of −log C, while Fig. 1 sums raw probabilities. Decide to cite the Hamiltonian-path reduction only, and not the transformation.

---

# Ciriani et al. 2010 — *Combining Fragmentation and Encryption to Protect Privacy in Data Storage*

**Full citation:** Valentina Ciriani, Sabrina De Capitani di Vimercati, Sara
Foresti, Sushil Jajodia, Stefano Paraboschi, Pierangela Samarati. ACM
Transactions on Information and System Security **13**(3), Article 22, July
2010. 33 pages → cite as `22:1--22:33` (confirm the house form).

**Stable primary source:** https://csis.gmu.edu/jajodia/2010-acm-tissec.pdf
(author-hosted; local sha256 `3d5fdc6444261b16`). Note the HTTPS certificate was
rejected by one fetch path; `curl -L` retrieved it.

**Current verification status:** **PRIMARY VERIFIED** (full text read).

**Where our repo cites or discusses it:** `docs/RELATED_WORK_NOTES.md` §2 (five
occurrences); referenced in the motivation chain in `docs/PRIOR_ART_CODE_COMPARISON.md` §7.
**Not currently cited anywhere in the results or methods docs.**

**Why we cite it:** It establishes that fragmentation is a privacy mechanism
aimed at protecting *associations*, which is what makes our question a privacy
question rather than a capability question.

## Claims our paper currently makes about this source

| # | Claim we currently make | Where we make it | Source location that should support it | Verification status |
|---|---|---|---|---|
| 1 | A confidentiality constraint is a subset of attributes whose **joint** visibility must be prevented | RELATED_WORK §2 | Definition 2.1 | **VERIFIED** |
| 2 | A singleton constraint means the attribute's own values are sensitive, and can only be solved by encryption | RELATED_WORK §2 | Def 2.1 discussion; §3 "singleton constraints can be solved only by encryption" | **VERIFIED** |
| 3 | "Well-defined" means no constraint is a subset of another | RELATED_WORK §2 | Definition 2.2 | **VERIFIED** |
| 4 | Fragmentation is attribute-level; each physical fragment carries all other attributes encrypted, with a salt | RELATED_WORK §2 | Definitions 3.1 and 3.2 | **VERIFIED** |
| 5 | Correctness has two conditions: no fragment is a superset of a constraint, and fragments are **pairwise disjoint in cleartext attributes** | RELATED_WORK §2; PRIOR_ART §7 | Definition 3.3, conditions (1) and (2) | **VERIFIED** |
| 6 | Minimal fragmentation is NP-hard | RELATED_WORK §2 | Theorem 4.3 (via hypergraph colouring) | **VERIFIED** |
| 7 | Their guarantee is **syntactic and by construction**, addressing joins on shared plaintext attributes, and does not model content-based relinking | RELATED_WORK §2; PRIOR_ART §7 | **Our interpretation** of Def 3.3; the paper makes no claim about content inference either way | **OUR INTERPRETATION — defensible but label it** |
| 8 | Their experimental contribution is mainly efficient near-optimal fragmentation, not adversarial evaluation | RELATED_WORK §2 | §5 heuristic; §8 query execution | **VERIFIED** |

**Flagged:** claim 7 is the load-bearing one for our motivation and it is an
*interpretation*, not a quotation. The paper's silence on content inference is
not the same as a statement that content inference is out of scope. Phrase it as
what the correctness condition *addresses*, never as what the authors *claim*.

## What the paper actually does

**Input / observation channel:** an honest-but-curious server holding physical
fragments: some attributes in cleartext, plus `salt` and `enc` (the remaining
attributes encrypted, XOR-ed with the salt; CBC with the salt as IV).

**Given information / anchors:** the attacker has no key. Salts are not secret.

**Unknowns it must infer:** nothing is "inferred" — this is a design paper, not
an attack paper. The guarantee is that constraints cannot be violated by
recombining fragments, because no plaintext attribute appears in two fragments.

**Output:** a correct, minimal (vector-minimal, heuristically found)
fragmentation of a relation.

**Metric:** correctness against the constraint set; then plaintext visibility
maximised; then query-execution cost.

**Main result:** constraints are enforceable by combining fragmentation with
attribute-level encryption; minimal fragmentation is NP-hard (Thm 4.3).

## Comparison to our paper

| Dimension | Prior paper | Our paper | Material difference? |
|---|---|---|---|
| Data type | relational attributes | natural-language text | **Yes** |
| Source count | one relation, m fragments | 7 documents per pool | **Yes** |
| Membership known? | n/a — fragments are schema objects | hidden | **Yes** |
| Ordering known? | n/a — no ordering notion | hidden | **Yes** |
| Structural anchors | schema, salts, constraint set | none | **Yes** |
| Observation channel | cleartext attribute values + ciphertext | plaintext fragment text | Partly |
| Output | a fragmentation design | an attacker's reconstruction | **Yes** |
| Metric | constraint correctness | measured attacker success | **Yes** |
| Privacy/security question | can we design fragments that prevent association disclosure? | can an attacker re-establish associations from content? | **Yes — complementary, not competing** |

**What this paper takes away from our novelty:** the idea that fragmentation
protects sensitive associations is theirs. We cannot present
association-oriented fragmentation privacy as our framing.

**What remains different / unresolved:** everything about the attack. This is
our motivation, not our competitor.

**Claims we may safely make:** "Fragmentation has been proposed to protect
sensitive associations by ensuring that attributes whose joint visibility is
constrained never appear together in the clear, with correctness requiring that
no two fragments share a cleartext attribute."

**Claims we must not make:** "Our result validates / refutes their guarantees."
"Fragmentation for association privacy is our idea." Any suggestion that their
formal guarantee was shown to fail — different system, different threat model.

## My manual verification checklist

- [ ] Confirm Definition 3.3's two conditions read as we state them.
- [ ] Confirm Theorem 4.3 is NP-hardness of *minimal* fragmentation specifically.
- [ ] Confirm the singleton-constraint-requires-encryption claim.
- [ ] Decide whether our "syntactic, by construction, does not model content relinking" phrasing overstates their position — it is our reading, not their text.
- [ ] Confirm the `22:1--22:33` page form against the published article.

---

# De Capitani di Vimercati et al. 2014 — *Fragmentation in Presence of Data Dependencies*

**Full citation:** Sabrina De Capitani di Vimercati, Sara Foresti, Sushil
Jajodia, Giovanni Livraga, Stefano Paraboschi, Pierangela Samarati. IEEE
Transactions on Dependable and Secure Computing. **DOI 10.1109/TDSC.2013.2295798.**
Copyright line reads © 2013 IEEE; commonly cited as 2014.
**Volume, issue and pages are NOT on the author preprint — must come from IEEE.**

**Stable primary source:** https://spdp.di.unimi.it/papers/tdsc2014.pdf
(author-hosted preprint; local sha256 `6529154488a5230b`).

**Current verification status:** **PRIMARY VERIFIED** (preprint; abstract and
definitions read directly). Bibliographic completeness is the only gap.

**Where our repo cites or discusses it:** `docs/RELATED_WORK_NOTES.md` §0 ledger
row 7 only — **one mention, added 2026-10-30.** It is not yet in
`PRIOR_ART_CODE_COMPARISON.md`, the packet, or any methods doc. Given the role
we now want it to play, that is an under-citation to fix during drafting.

**Why we cite it:** It states formally, twelve years before our experiment, that
fragment disjointness is insufficient for unlinkability when dependencies permit
recombination. It converts our contribution from "we noticed something" into
"we supply the empirical instance of a stated open problem."

## Claims our paper currently makes about this source

| # | Claim we currently make | Where we make it | Source location that should support it | Verification status |
|---|---|---|---|---|
| 1 | Disjointness is "only a necessary, but not sufficient, condition" for preventing recombination | RELATED_WORK §0 row 7 | **Abstract**, verbatim | **VERIFIED — direct quotation** |
| 2 | The insufficiency arises because dependencies among data enable "some form of linkability" | RELATED_WORK §0 row 7 | Abstract; §1 | **VERIFIED** |
| 3 | Their dependencies are **declared, attribute-level** relations | RELATED_WORK §1 note; §6 test answer | Definition of data dependencies (§2); Fig. 3 example; `d1={Birth,ZIP}→…`, `d2={Birth,ZIP}→Name` | **VERIFIED** |
| 4 | The problem is formulated and solved as a Constraint Satisfaction Problem | RELATED_WORK §0 row 7 | §1 contributions; Index Terms list "CSP" | **VERIFIED** |
| 5 | Ours is an *implicit* dependency expressed in unconstrained natural language and inferred by the attacker | RELATED_WORK §6; PRIOR_ART §7 | **Our novelty inference** — the source says nothing about natural language | **OUR NOVELTY INFERENCE — label it** |
| 6 | *(not yet claimed, should be)* this paper adds **visibility constraints** (Def 2.2), which Ciriani 2010 does not have | — | Definition 2.2 | **VERIFIED — available, uncited** |

**Caution on claim 5.** Do not write that semantic dependencies "cannot be
enumerated in advance" as an absolute. Some could in principle be formalised.
The defensible wording is about where the dependency *lives* and who supplies
it: theirs are supplied to the protection design; ours are latent in content and
inferred by the attacker.

## What the paper actually does

**Input / observation channel:** a relation fragmented under confidentiality and
visibility constraints, where known data dependencies hold among attributes.

**Given information / anchors:** the constraint set and the dependency set are
declared inputs to the design.

**Unknowns it must infer:** none — it computes fragmentations that remain
correct in the presence of the declared dependencies.

**Output:** fragmentations satisfying confidentiality, visibility and
unlinkability given the dependencies.

**Metric:** correctness under the extended model; then efficiency/scalability of
the CSP solution.

**Main result:** the prior unlinkability condition (pairwise-disjoint cleartext
attributes) is necessary but not sufficient; dependencies can re-enable
linkability; the paper models and solves for this.

## Comparison to our paper

| Dimension | Prior paper | Our paper | Material difference? |
|---|---|---|---|
| Data type | relational attributes | natural-language text | **Yes** |
| Source count | one relation | 7 documents | **Yes** |
| Membership known? | n/a | hidden | **Yes** |
| Ordering known? | n/a | hidden | **Yes** |
| Structural anchors | declared constraints and dependencies | none | **Yes** |
| Observation channel | cleartext attributes across fragments | plaintext fragment text | Partly |
| Output | a safe fragmentation | an attacker's reconstruction | **Yes** |
| Metric | correctness under dependencies | measured attacker success | **Yes** |
| Privacy/security question | how to fragment safely when dependencies exist | whether language itself is such a dependency, and how much leaks | **Complementary** |

**What this paper takes away from our novelty:** the *observation* that
disjoint fragments can remain linkable is not ours, and we must not present it
as a discovery. It is a published theoretical result.

**What remains different / unresolved:** their dependency is declared, discrete
and supplied to the designer; ours is latent in prose and must be inferred by
an attacker. They prove a design condition; we measure an attack. Nothing in
their model quantifies how much an adversary recovers.

**Claims we may safely make:** "Prior work establishes that requiring fragments
to share no attributes is necessary but not sufficient for unlinkability, since
dependencies among the data may permit recombination. That result is formulated
for declared, attribute-level dependencies supplied to the protection design. We
ask whether implicit dependencies carried by unconstrained natural-language
content constitute a comparable channel, and we measure how much an attacker
recovers through it."

**Claims we must not make:** "We show for the first time that fragmented data
can remain linkable." "Semantic dependencies cannot be formalised." Any claim
that we extend or generalise their theorem — we do not prove anything.

## My manual verification checklist

- [ ] Get volume, issue and page numbers from IEEE Xplore (not on the preprint).
- [ ] Confirm the abstract's "necessary, but not sufficient" sentence verbatim.
- [ ] Confirm the dependency definition is over declared attribute relations, with Fig. 3 as the example.
- [ ] Confirm Definition 2.2 introduces visibility constraints (absent from Ciriani 2010) — decide whether to cite that distinction.
- [ ] Confirm nothing in the paper addresses unstructured text, so our extension is genuinely an extension.
- [ ] Decide whether the authors' own later work already covers content inference, which would weaken our gap.

---

# Memon & Pal 2006 — *Automated Reassembly of File Fragmented Images Using Greedy Algorithms*

**Full citation:** Nasir Memon and Anandabrata Pal. IEEE Transactions on Image
Processing **15**(2):385–393, February 2006.

**Stable primary source:** IEEE Xplore (paywalled). **Two offered links both
failed:** a CiteSeerX document URL returned HTTP 404 (4,689-byte HTML error
page, local sha256 `d1d9b6f6025f94ca`), and a second CiteSeerX link offered in
review also 404'd. CiteSeerX document URLs are not a working route here.

**Current verification status:** **SECONDARY ONLY. THE PRIMARY HAS NOT BEEN
READ.** Everything below comes from: Pal & Memon, *The evolution of file
carving* (IEEE Signal Processing Magazine, 2009); a JOWUA multimedia-carving
survey; related USPTO patent texts; and a review summary.

**Where our repo cites or discusses it:** `docs/PRIOR_ART_CODE_COMPARISON.md` §0
(marked SECONDARY ONLY), §1 comparison table, §3, §7; `docs/RELATED_WORK_NOTES.md`
§0 ledger row 6, §1, §6, §7.

**Why we cite it:** It is the paper that removes any claim to being first at
joint membership-and-ordering reconstruction. We cite it to concede.

## Claims our paper currently makes about this source

| # | Claim we currently make | Where we make it | Source location that should support it | Verification status |
|---|---|---|---|---|
| 1 | Reassembles **k files simultaneously** from a mixed fragment pool | PRIOR_ART §0, §7; RELATED_WORK §0 row 6 | unlocated — secondary description | **SECONDARY ONLY** |
| 2 | The algorithm is Parallel Unique Path (PUP), a parallel variant of Dijkstra, growing one path per file | PRIOR_ART §0 | unlocated | **SECONDARY ONLY** |
| 3 | Fragments already assigned to one file are removed from other files' candidate sets | PRIOR_ART §0 | unlocated | **SECONDARY ONLY** |
| 4 | **Starts from identified file headers**, which supply the number of files and each file's starting fragment | PRIOR_ART §0, §1; RELATED_WORK §1 | unlocated | **SECONDARY ONLY** |
| 5 | Headers also supply resolution / image size / expected fragment count | RELATED_WORK §0 row 6 (via review) | unlocated | **SECONDARY ONLY — weakest claim in this audit** |
| 6 | Compatibility comes from pixel matching, DCT and median-edge detection | PRIOR_ART §0, §3 | unlocated | **SECONDARY ONLY** |
| 7 | Complexity O(n² log n) | PRIOR_ART §0 | attributed to Pal & Memon 2009 and Poisel | **SECONDARY ONLY** |
| 8 | Later cast as a k-vertex-disjoint path problem | PRIOR_ART §0 | attributed to "Pal et al. subsequently" — possibly a *different* paper | **SECONDARY ONLY, AND POSSIBLY MISATTRIBUTED** |
| 9 | Assumes all blocks present, no holes | PRIOR_ART §0 | unlocated | **SECONDARY ONLY** |
| 10 | Mixed-source reconstruction is therefore not novel | PRIOR_ART §7; RELATED_WORK §6 | depends on claim 1 only | **Our novelty inference, resting on a secondary claim** |

**This is the most important gap in the audit.** Claim 10 — a concession that
materially shapes the paper's contribution — rests on claim 1, which has not
been verified against the primary. The concession is very likely correct, and I
recommend making it regardless. But claims 2–9 must not appear in the manuscript
until someone reads IEEE TIP 15(2):385–393, and claim 8 may belong to a
different paper entirely.

## What the paper actually does

**Cannot be stated from primary evidence.** Per secondary sources only: input is
byte/image fragments of multiple image files; headers are identified first and
anchor the reconstruction; compatibility is pixel/DCT/median-edge across the
candidate boundary; output is k disjoint reconstruction paths; greedy parallel
path growth. **No metric, dataset or headline number is recorded here, because
none has been verified.**

## Comparison to our paper

| Dimension | Prior paper (secondary) | Our paper | Material difference? |
|---|---|---|---|
| Data type | image/byte file fragments | plaintext linguistic units | **Yes** |
| Source count | k, from headers | 7, stated in the prompt | Both known — **no** |
| Membership known? | hidden, but anchored by headers | hidden, unanchored | **Yes** |
| Ordering known? | hidden | hidden | No |
| Structural anchors | file headers → count, start, size | none | **Yes** |
| Observation channel | pixel/DCT/edge continuity | language only | **Yes** |
| Output | k disjoint paths | partition with order | Similar in shape |
| Metric | unverified | F1 over precedence pairs, factored | unknown |
| Privacy/security question | forensic recovery | privacy leakage | **Yes** |

**What this paper takes away from our novelty:** the claim "first joint
membership-and-ordering reconstruction" is **dead**. Concede it in the
related-work paragraph that introduces Game J, before a reviewer raises it.

**What remains different / unresolved:** the observation channel and the
absence of any anchor. Their attacker is handed, by file format, the two things
ours must infer or do without.

**Claims we may safely make:** "Mixed-source fragment reassembly has prior art
in fragmented image and file reconstruction." That is all, until the primary is
read.

**Claims we must not make:** any specific statement about PUP's mechanism,
header contents, complexity, or assumptions; "we are the first to reconstruct
from multiple mixed sources"; any numerical comparison.

## My manual verification checklist

- [ ] Obtain IEEE TIP 15(2):385–393 through institutional access.
- [ ] Confirm the paper reconstructs **multiple files at once** rather than one file at a time.
- [ ] Confirm headers are required, and record exactly what they supply (count? starting fragment? dimensions? expected fragment count?).
- [ ] Confirm the compatibility signal is pixel/DCT/MED across the candidate boundary.
- [ ] Confirm whether "PUP" and the k-vertex-disjoint-path formulation are in *this* paper or a later one — our note may misattribute.
- [ ] Record the actual metric and headline numbers, with the table/figure.
- [ ] Decide whether the concession needs the specifics at all; "mixed-source reassembly has prior art" may be sufficient.

---

# Paixão et al. 2020 — *Self-supervised Deep Reconstruction of Mixed Strip-shredded Text Documents*

**Full citation:** Thiago M. Paixão, Rodrigo F. Berriel, Maria C. S. Boeres,
Alessandro L. Koerich, Claudine Badue, Alberto F. De Souza, Thiago
Oliveira-Santos. *Pattern Recognition*, 2020. **DOI 10.1016/j.patcog.2020.107535.**
Preprint arXiv:2007.00779.

**Stable primary source:** https://arxiv.org/pdf/2007.00779 (local sha256
`dc19387f6b781ca7`).

**Current verification status:** **PRIMARY VERIFIED** (abstract, method,
metric definition, dataset and experiment protocol read).

**Where our repo cites or discusses it:** `docs/PRIOR_ART_CODE_COMPARISON.md` —
sixteen occurrences across §0, §1, §2, §3, §4, §4B, §7, §8;
`docs/RELATED_WORK_NOTES.md` — eleven, across §0 row 7, §1, §6, §7.

**Why we cite it:** the closest structural predecessor — it reconstructs several
mixed *text* documents at once — and the source of our sharpest metric contrast.

## Claims our paper currently makes about this source

| # | Claim we currently make | Where we make it | Source location that should support it | Verification status |
|---|---|---|---|---|
| 1 | It reconstructs "several mixed shredded documents at once" | PRIOR_ART §0; RELATED_WORK §0 row 7 | **Abstract**, verbatim | **VERIFIED — direct quotation** |
| 2 | Input is **images** of paper shreds, not text | PRIOR_ART §0, §1 | §4.2 datasets (shreds scanned at 300 dpi, one JPEG per shred); §3.1 | **VERIFIED** |
| 3 | Compatibility is a two-class (valid/invalid) problem learned from pixel content around the cut | PRIOR_ART §0, §3 | Abstract; §3.1; Fig. 3 (16 rightmost pixels joined); Fig. 4 (sliding window, stride 16) | **VERIFIED** |
| 4 | Training is self-supervised on simulated-shredded documents | PRIOR_ART §0 | Abstract; §3.1; §4.1 | **VERIFIED** |
| 5 | Output is **one global permutation**, not a predicted grouping | PRIOR_ART §0, §2, §4 | §3.2.2 "solution … represents the intended shreds' permutation"; §4.3 accuracy definition over positions | **VERIFIED** |
| 6 | Solved as Minimum-cost Hamiltonian Path → ATSP (dummy vertex) → TSP, exactly, with Concorde | PRIOR_ART §0, §3 | §3.2.2 (Concorde + QSOpt3) | **VERIFIED** |
| 7 | Accuracy is `(1/(N−1)) Σ 1[match]` over immediate adjacency | PRIOR_ART §0, §4, §4B | **Equation (2)**, §4.3 | **VERIFIED** |
| 8 | A match includes the **inter-document seam** (last shred of d1 with first of d2) | PRIOR_ART §0, §4; RELATED_WORK §6 | §4.3 preceding eq. (2); "shreds from different documents, and the order these documents appear is not relevant" | **VERIFIED — direct quotation** |
| 9 | Membership is implicit in contiguous runs, never output or scored | PRIOR_ART §0, §2 | **Our interpretation** of eq. (2) + the single-permutation output | **OUR INTERPRETATION — well supported but not stated by them** |
| 10 | They sweep the number of mixed documents: k=1..5 in the ablation, plus 10, 15, 20 … up to N_docs (60, 20, 100) | PRIOR_ART §0, §7; RELATED_WORK §0 row 7 | §4.4 incremental evaluation protocol | **VERIFIED** |
| 11 | Reports accuracy >90% on 100 mixed documents / 2,292 shreds | PRIOR_ART §0; RELATED_WORK §0 row 7 | Abstract ("superior to 90%"); §1 (100 documents, 2,292 shreds); §5 Fig. 6 ("above 90% for the three datasets") | **VERIFIED** |
| 12 | Adding documents does not degrade accuracy | PRIOR_ART §0, §7 | §5 discussion of the incremental experiment | **VERIFIED** |
| 13 | Their >90% is **not numerically comparable** to our F1_J | PRIOR_ART §0, §4; RELATED_WORK §0 row 7 | **Our novelty inference**, from claims 2, 5, 7, 8 | **OUR INFERENCE — sound, label it** |

## What the paper actually does

**Input / observation channel:** scanned images of mechanically produced paper
shreds, 300 dpi, one JPEG per shred; the model sees the pixel content either
side of a candidate join.

**Given information / anchors:** the number of mixed documents k defines the
instance. No supplied starting shred — the ATSP is solved globally with a
zero-weight dummy vertex. Physical cut edges are available as evidence.

**Unknowns it must infer:** the global arrangement of all shreds; document
boundaries fall out of it implicitly.

**Output:** one permutation of all shreds in the instance.

**Metric:** eq. (2), the fraction of adjacent positions in the solution that are
true adjacencies, where a true adjacency is intra-document consecutive **or** a
seam between two completed documents.

**Main result (verified):** accuracy above 90% across three datasets including a
new 100-document, 2,292-shred collection; accuracy does not degrade as k grows.

## Comparison to our paper

| Dimension | Prior paper | Our paper | Material difference? |
|---|---|---|---|
| Data type | shred images of paper | plaintext | **Yes** |
| Source count | k, swept 1→100 | 7, fixed | **Yes — and not in our favour** |
| Membership known? | hidden, implicit in output | hidden, explicitly predicted | **Yes** |
| Ordering known? | hidden | hidden | No |
| Structural anchors | physical cut edges; no start anchor | none | **Yes** |
| Observation channel | pixel content across the cut | language only | **Yes — the core difference** |
| Output | one global permutation | partition with order per group | **Yes** |
| Metric | immediate-adjacency rate, seams free | precedence F1 factored into linkage × ordering; cross-document pairs wrong | **Yes** |
| Privacy/security question | forensic/document-recovery capability | privacy leakage under fragmentation | **Yes** |

**What this paper takes away from our novelty:** mixed-source reconstruction of
*text documents* is established, at far greater scale than ours, by a learned
model. We cannot claim mixed-document reconstruction, learned reconstruction,
or scaling in the number of mixed sources. It also makes "why don't you vary N?"
a foreseeable reviewer question, since they do.

**What remains different / unresolved:** the observation channel (pixel
continuity across a physical cut versus language alone); the output
representation (global permutation versus predicted partition); and the metric
(seam-free adjacency versus a factored precedence score). Those three are
independent and each is material.

**Claims we may safely make:** "Mixed-document reconstruction has been
demonstrated for strip-shredded text documents at scale, using a learned model
of the pixel content either side of a physical cut, with the solution expressed
as a single global permutation and scored by immediate adjacency in which the
seam between two completed documents counts as correct."

**Claims we must not make:** "we are first to mixed-source text
reconstruction"; "our F1_J of 0.723 is lower/higher than their 90%"; "no prior
work varies the number of mixed sources."

## My manual verification checklist

- [ ] Confirm the abstract phrase "several mixed shredded documents at once."
- [ ] Confirm §4.3 / eq. (2) and specifically that the inter-document seam counts as a match.
- [ ] Confirm the single-permutation output — that no grouping is predicted or scored.
- [ ] Confirm the k-sweep values and that accuracy does not degrade with k.
- [ ] Confirm the >90% figure's experiment and dataset (Fig. 6 and §5).
- [ ] Confirm the compatibility input is pixel content around the cut (Figs. 3–4).
- [ ] Check whether any experiment reports a grouping/membership accuracy separately — if one does, our "no separate membership metric" claim needs softening.

---

# Paixão et al. 2020 (CVPR companion) — *Fast(er) Reconstruction of Shredded Text Documents via Self-Supervised Deep Asymmetric Metric Learning*

**Full citation:** Paixão, Berriel, Boeres, Koerich, Badue, De Souza,
Oliveira-Santos. CVPR 2020. **DOI 10.1109/CVPR42600.2020.01435.** Preprint
arXiv:2003.10063.

**Stable primary source:** https://arxiv.org/pdf/2003.10063 and
https://openaccess.thecvf.com/content_CVPR_2020/papers/Paixao_Faster_Reconstruction_of_Shredded_Text_Documents_via_Self-Supervised_Deep_Asymmetric_CVPR_2020_paper.pdf
(local sha256 `186f38f9b4100482`).

**Current verification status:** **PRIMARY HELD; ONE DETAIL UNVERIFIED.**

**Where our repo cites or discusses it:** `docs/PRIOR_ART_CODE_COMPARISON.md` §0,
§8 open items; `docs/RELATED_WORK_NOTES.md` §0 row 7.

**Why we cite it:** the scale/speed companion result, and the "20 mixed pages"
instance.

| # | Claim we currently make | Where | Source location | Status |
|---|---|---|---|---|
| 1 | ~22× speed-up on a 505-shred instance | PRIOR_ART §0 | abstract | **NOT RE-VERIFIED from the PDF** |
| 2 | The instance is "20 mixed shredded pages from different documents" | PRIOR_ART §0; RELATED_WORK §0 row 7 | abstract | **NOT RE-VERIFIED** |
| 3 | Whether that is ONE mixed instance or 20 separate single-page instances | PRIOR_ART §8 open item | unresolved | **OPEN QUESTION, already flagged** |

The Pattern Recognition paper's k-sweep makes our concession hold regardless of
how claim 3 resolves, so this is not blocking — but do not state claim 2 as a
single mixed instance until checked.

## My manual verification checklist

- [ ] Confirm the 505-shred / 20-page figure and the 22× speed-up from the abstract.
- [ ] Settle whether the 505 shreds form one mixed instance or twenty single-page instances.
- [ ] Decide whether this paper needs citing at all, given the PR paper covers the concession.

---

# ShredBench 2026 — *Evaluating the Semantic Reasoning Capabilities of Multimodal LLMs in Document Reconstruction*

**Full citation:** Zichun Guo, Yuling Shi, Wenhao Zeng, Chao Hu, Haotian Lin,
Terry Yue Zhuo, Jiawei Chen, Xiaodong Gu, Wenping Ma. *Findings of the
Association for Computational Linguistics: ACL 2026*, pages 22603–22615. San
Diego, California. **Nine authors — do not truncate silently.**

**Stable primary source:** https://aclanthology.org/2026.findings-acl.1135/ and
the PDF at https://aclanthology.org/2026.findings-acl.1135.pdf (local sha256
`2f8ed13a8f197448`).

**Current verification status:** **PRIMARY VERIFIED** (task formulation,
shredding design, metric definitions read).

**Where our repo cites or discusses it:** `docs/RELATED_WORK_NOTES.md` §0 row 3,
§3 (seven occurrences); `docs/PRIOR_ART_CODE_COMPARISON.md` §7.

**Why we cite it:** It prevents us from claiming first LLM fragment
reconstruction or first granularity study, and it supplies a convergent
granularity result in a different modality.

## Claims our paper currently makes about this source

| # | Claim we currently make | Where we make it | Source location that should support it | Verification status |
|---|---|---|---|---|
| 1 | Fragments are **image** crops, not plaintext | RELATED_WORK §3; PRIOR_ART §7 | §3.4 Task Formulation; §3.2–3.3 pipeline | **VERIFIED** |
| 2 | Fragments come from **a single source document D** | RELATED_WORK §3; PRIOR_ART §7 | §3.4, verbatim: "scattered image fragments derived from a single source document" | **VERIFIED — direct quotation** |
| 3 | Granularity is varied as 8 / 12 / 16 pieces | RELATED_WORK §3 | §3.2; Table 1 | **VERIFIED** |
| 4 | Cuts are Voronoi (irregular), chosen to defeat trivial straight-edge matching | RELATED_WORK §3 | §3.2 Voronoi Cutting Algorithm; Table 1 contrast with grid-crop benchmarks | **VERIFIED** |
| 5 | The task is set-to-sequence; output is the restored text, not spatial coordinates | RELATED_WORK §3 | §3.4, explicit | **VERIFIED** |
| 6 | Metrics are NED, TEDS, BLEU, ROUGE-L | RELATED_WORK §3 | §4.2 Evaluation Metrics | **VERIFIED** |
| 7 | NED is normalised Levenshtein and **lower is better** | RELATED_WORK §3 | §4.2, "A lower NED implies higher similarity" | **VERIFIED** |
| 8 | State-of-the-art models average NED 0.73 | RELATED_WORK §3 | §3.3 data-validation discussion | **VERIFIED — but see caution** |
| 9 | Best model reaches NED 0.33 in a breakdown | RELATED_WORK §3 | §5 results text | **NOT PRECISELY LOCATED — which model and which subset is unconfirmed** |
| 10 | Performance degrades as the number of pieces rises | RELATED_WORK §3 | abstract; §5 | **VERIFIED in direction** |
| 11 | There is **no membership component and no grouping metric** | RELATED_WORK §3; PRIOR_ART §7 | §3.4 single-source formulation; §4.2 metric list; no occurrence of mixed-source language in the paper | **VERIFIED (by construction and by absence)** |
| 12 | Domains are bilingual news (800–2,500 chars), code, scientific tables | RELATED_WORK §3 | §3.1 | **VERIFIED** |

**Caution on claim 8.** The 0.73 figure appears in the context of the authors'
*data-validation* argument — that samples are solvable and the failure is the
models', not the data. Confirm it is a headline model-performance number before
quoting it as one.

## What the paper actually does

**Input / observation channel:** rendered document images, Voronoi-shredded into
8, 12 or 16 irregular pieces, 3D-synthesised with paper texture, possibly
rotated and lighting-distorted.

**Given information / anchors:** all pieces come from one document; the model
sees the visual cut edges.

**Unknowns it must infer:** the reading order, implicitly, plus OCR of the text.

**Output:** a text string intended to match the ground-truth document text.

**Metric:** NED (lower better), TEDS for tables, BLEU, ROUGE-L — all
text-similarity measures on the restored string.

**Main result (verified in direction):** strong on intact documents, degrading
with fragmentation; state-of-the-art average NED 0.73 in the authors' framing.

## Comparison to our paper

| Dimension | Prior paper | Our paper | Material difference? |
|---|---|---|---|
| Data type | document images | plaintext | **Yes** |
| Source count | 1 | 7 | **Yes** |
| Membership known? | n/a — single source | hidden | **Yes** |
| Ordering known? | hidden | hidden | No |
| Structural anchors | visual cut edges | none | **Yes** |
| Observation channel | pixels + OCR + semantics | language only | **Yes** |
| Output | restored text string | partition with order | **Yes** |
| Metric | edit distance on text | precedence F1, factored | **Yes** |
| Privacy/security question | model capability benchmark | privacy leakage | **Yes** |
| Granularity range | 8–16 pieces | 28 → 532 fragments per pool | **Yes, two orders finer** |

**What this paper takes away from our novelty:** "first LLM reconstruction of
fragmented documents" and "first study of fragmentation granularity" are both
**dead**, in a 2026 paper with a public benchmark. Concede both in the opening
sentence of the LLM related-work paragraph.

**What remains different / unresolved:** plaintext rather than rendered images;
mixed sources with unknown membership; a metric that factors; a granularity
range two orders finer; and a privacy threat model with calibrated references
rather than a capability benchmark.

**Claims we may safely make:** "Multimodal models have been benchmarked on
reconstructing a single shredded document from image fragments, with
performance degrading as the number of pieces increases."

**Claims we must not make:** "we are first to use an LLM for fragment
reconstruction"; "we are first to vary fragmentation granularity"; any direct
comparison of our F1_J to their NED.

## My manual verification checklist

- [ ] Confirm §3.4's "single source document" phrasing.
- [ ] Confirm the 8 / 12 / 16 piece counts and the Voronoi rationale.
- [ ] Confirm NED's direction (lower is better) in §4.2.
- [ ] Locate the 0.73 figure and decide whether it is a headline performance number or a validation-argument number.
- [ ] Locate the 0.33 figure, and record which model and subset.
- [ ] Confirm no experiment mixes fragments from multiple documents.

---

# Lermen et al. 2026 — *Large-scale online deanonymization with LLMs*

**Full citation:** Simon Lermen, Daniel Paleka, Joshua Swanson, Michael Aerni,
Nicholas Carlini, Florian Tramèr. *35th USENIX Security Symposium (USENIX
Security '26)*, pages 1947–1966. **Note the title is "deanonymization", not
"semantic linkage".**

**Stable primary source:** https://www.usenix.org/conference/usenixsecurity26/presentation/lermen
and the PDF at https://www.usenix.org/system/files/usenixsecurity26-lermen.pdf
(local sha256 `6808f2f834d2ca8e`).

**Current verification status:** **PRIMARY VERIFIED** (pipeline, dataset,
difficulty parameters, ablation numbers read).

**Where our repo cites or discusses it:** `docs/RELATED_WORK_NOTES.md` §0 row 4,
§4; `docs/PRIOR_ART_CODE_COMPARISON.md` §7, §8.

**Why we cite it:** establishes modern LLM semantic linkage, and provides the
precedent for a closed-world evaluation that varies its own difficulty
parameters — which is also the source of a limitation we must concede.

## Claims our paper currently makes about this source

| # | Claim we currently make | Where we make it | Source location that should support it | Verification status |
|---|---|---|---|---|
| 1 | Three-stage pipeline: Extract → Search (dense embeddings) → Reason | RELATED_WORK §4 | §1 bullet list; §3 stage descriptions | **VERIFIED** |
| 2 | Candidate pool is ~89,000 active Hacker News users | RELATED_WORK §4 | §4.1 dataset | **VERIFIED** |
| 3 | In the main experiments the true match is guaranteed present — "the prior of a match existing is 100%" | RELATED_WORK §4; PRIOR_ART §7 | §3, verbatim | **VERIFIED — direct quotation** |
| 4 | §6.4 varies candidate-pool size and the match prior λ | RELATED_WORK §4; PRIOR_ART §7 | §6.4; Fig. 7 | **VERIFIED** |
| 5 | Reason lifts recall at 99% precision from 4.4% (Search only) to 45.1% | RELATED_WORK §4 | §1 and §5 ablation | **VERIFIED** |
| 6 | Best non-LLM comparison is ~0.1% at the same threshold | RELATED_WORK §4 | §1 | **VERIFIED** |
| 7 | Up to 55% recall at 90% precision | RELATED_WORK §4 | abstract / §1 | **VERIFIED** |
| 8 | The classical baseline is a Narayanan-style binary vector over 332 attributes | RELATED_WORK §4 | §4.x baseline description | **VERIFIED** |
| 9 | Full pipeline costs at most $0.23 per target | RELATED_WORK §4 | §3 cost note | **VERIFIED** |
| 10 | No task involves ordering or grouping document fragments | RELATED_WORK §4; PRIOR_ART §7 | absence across the paper | **VERIFIED by absence** |
| 11 | Their embedding-vs-reasoning ablation is **consistent with**, not evidence for, our embedding-vs-Sonnet gap | RELATED_WORK §4 (corrected) | **Our interpretation** — different pipelines, no shared control | **OUR INTERPRETATION, correctly hedged** |

## What the paper actually does

**Input / observation channel:** pseudonymous profile text; in the closed-world
setting, a fixed candidate database.

**Given information / anchors:** a fixed candidate pool; in the main
experiments, the guarantee that the true match is in it.

**Unknowns it must infer:** which candidate corresponds to the query profile.

**Output:** a single predicted match, or an abstention.

**Metric:** Recall@Precision over matchable users, with a confidence threshold
traced into precision–recall curves.

**Main result (verified):** 4.4% → 45.1% recall at 99% precision when the Reason
stage is added, against ~0.1% for the adapted classical baseline; up to 55%
recall at 90% precision; agentic open-web setting 25–67% recall at 70–90%
precision.

## Comparison to our paper

| Dimension | Prior paper | Our paper | Material difference? |
|---|---|---|---|
| Data type | profile text | document fragments | **Yes** |
| Source count | ~89,000 candidates | 7 documents | **Yes** |
| Membership known? | match guaranteed in pool | partition guaranteed, labels hidden | Similar favourability |
| Ordering known? | n/a — no ordering task | hidden | **Yes** |
| Structural anchors | fixed candidate pool | known N | Similar |
| Observation channel | profile semantics | fragment semantics | **No — closest match of any paper** |
| Output | identity match | partition with order | **Yes** |
| Metric | Recall@Precision | precedence F1, factored | **Yes** |
| Privacy/security question | deanonymization cost | fragmentation leakage | Related |

**What this paper takes away from our novelty:** LLM-assisted semantic linkage
is established, with much stronger headline numbers than ours in its own
setting. We cannot claim to have discovered that language models enable semantic
linkage, nor that semantic attackers change privacy threat models.

**What remains different / unresolved:** there is no fragment ordering and no
grouping task anywhere in the paper. Reconstruction — recovering *within-source
order* and *which pieces go together* — is not what they do.

**Claims we may safely make:** "LLM-assisted semantic linkage has been
demonstrated at scale against pseudonymous profiles, substantially outperforming
classical feature-based matching, in a closed-world setting whose difficulty
parameters the authors vary explicitly." And, as a limitation: "Closed-world
evaluation with a fixed candidate set is established practice; unlike that work,
we do not vary our pool size or the match guarantee."

**Claims we must not make:** "we discovered semantic linkage"; "their ablation
explains our embedding-versus-LLM gap"; "no prior work studies closed-world
favourability."

## My manual verification checklist

- [ ] Confirm the exact title (it is "deanonymization", not "semantic linkage").
- [ ] Confirm the "prior of a match existing is 100%" sentence and its section.
- [ ] Confirm §6.4 sweeps both pool size and λ, and look at Fig. 7.
- [ ] Confirm the 4.4% → 45.1% ablation and which precision threshold it is at.
- [ ] Confirm the ~89,000 pool size and the 5,000 query profiles.
- [ ] Confirm nothing in the paper orders or groups fragments.
- [ ] Check our numbers were not crossed between the closed-world and agentic settings — they were read from a two-column extraction.

---

# Gallé & Tealdi 2015 — *Reconstructing Textual Documents from n-grams*

**Full citation:** Matthias Gallé and Matias Tealdi. *Proceedings of the 21st ACM
SIGKDD International Conference on Knowledge Discovery and Data Mining (KDD '15)*,
pages 329–338. **DOI 10.1145/2783258.2783361.**

**Stable primary source:** https://dl.acm.org/doi/10.1145/2783258.2783361
(paywalled). Author/lab landing page with abstract:
https://europe.naverlabs.com/research/publications/reconstructing-textual-documents-from-n-grams/
**The CiteSeerX link in the original reading list is dead** — HTTP 404,
4,689-byte HTML error page (local sha256 `e092697a24148775`). Remove it.

**Current verification status:** **METADATA ONLY — the full text has not been
read.** Everything below comes from the publisher metadata and the authors' own
publication-page abstract.

**Where our repo cites or discusses it:** `docs/RELATED_WORK_NOTES.md` §0 row 5,
§5 (six occurrences). Not in PRIOR_ART_CODE_COMPARISON.

**Why we cite it:** It provides the observation-model contrast for very small
textual units, and it constrains our single-token claim.

## Claims our paper currently makes about this source

| # | Claim we currently make | Where we make it | Source location | Verification status |
|---|---|---|---|---|
| 1 | The attacker receives n-grams with counts for a fixed n | RELATED_WORK §5 | abstract | **METADATA ONLY** |
| 2 | The goal is the longest substrings that must appear in the originals | RELATED_WORK §5 | abstract | **METADATA ONLY** |
| 3 | Modelled as a de Bruijn graph, n-grams as edges, Eulerian cycles as reconstructions | RELATED_WORK §5 | abstract | **METADATA ONLY** |
| 4 | Two reduction rules preserve all reconstructions and yield an irreducible equivalent graph | RELATED_WORK §5 | abstract | **METADATA ONLY** |
| 5 | Evaluated on Project Gutenberg | RELATED_WORK §5 | abstract | **METADATA ONLY** |
| 6 | Removing low-frequency n-grams barely hinders reconstruction; adding fictitious n-grams does, at small perplexity cost | RELATED_WORK §5 | abstract | **METADATA ONLY** |
| 7 | Recovered chunks averaging ~55 words, maximal averaging ~658, from all 5-grams | RELATED_WORK §5 | **NOT IN THE ABSTRACT** — came from a web-search summary that attributed it to a *related* Tealdi & Gallé method, possibly the SeqBio 2013 workshop paper | **UNVERIFIED — DO NOT USE** |
| 8 | Order-n n-grams overlap by n−1 tokens, so adjacency is encoded in the data | RELATED_WORK §5; §6 | **Our interpretation** — true by definition of n-grams, not a claim of theirs | **OUR INTERPRETATION (sound by definition)** |
| 9 | Our fragments are disjoint, so no overlap evidence exists | RELATED_WORK §5 | claim about our own design | **VERIFIED against our code** |

**Claim 7 must be removed or verified.** It is the only quantitative figure we
carry for this paper and it is not from the paper's own abstract.

## What the paper actually does

**Stated only at abstract level.** Input: the complete n-gram inventory with
counts for a fixed n. Unknowns: the original text. Output: the maximal
substrings forced by the inventory. Metric: number and size of recovered
substrings. Defence result: fictitious n-grams.

## Comparison to our paper

| Dimension | Prior paper | Our paper | Material difference? |
|---|---|---|---|
| Data type | n-gram inventory with counts | disjoint text fragments | **Yes** |
| Source count | a corpus, not enumerated sources | 7 documents | **Yes** |
| Membership known? | no membership problem | hidden | **Yes** |
| Ordering known? | hidden | hidden | No |
| Structural anchors | **n−1 token overlap between windows** | none | **Yes — the core difference** |
| Observation channel | overlapping windows + multiplicities | disjoint fragments (multiplicities still visible) | **Yes** |
| Output | maximal substrings | partition with order | **Yes** |
| Metric | recovered substring length | precedence F1, factored | **Yes** |
| Privacy/security question | leakage from released n-gram statistics | leakage from fragmented plaintext | Related |

**What this paper takes away from our novelty:** reconstruction of text from
very small units is established, and so is the framing of it as a privacy
leak from a release format. The one-word arm is not novel as "reconstruction
from tiny units."

**What remains different / unresolved:** the overlap. Order-n n-grams share
n−1 tokens with their neighbours, which hands the attacker adjacency directly;
our fragments share nothing. Membership is also absent from their problem.

**Claims we may safely make:** "Reconstruction from small textual units has
been studied for overlapping n-gram releases, where consecutive windows share
n−1 tokens and therefore expose adjacency relationships directly. Our fragments
are disjoint and expose no such relationships."

**Claims we must not make:** "reconstruction from word-level units is new";
"our fragments are uncounted" (repeated surface forms are visible and our
primary scorer counts multiplicities); "a disjoint partition carries strictly
less information than an n-gram inventory" (an information-ordering claim we
have not proved); and the ~55-word figure, until verified.

## My manual verification checklist

- [ ] Obtain the ACM paper (KDD '15, 329–338) and replace the dead CiteSeerX link.
- [ ] Confirm the de Bruijn / Eulerian formulation and the two reduction rules.
- [ ] Confirm whether counts (multiplicities) are assumed, and whether "perfect n-gram information" is their assumption.
- [ ] Find the actual reported recovered-substring statistics and replace or delete our ~55-word figure.
- [ ] Confirm the defence result (fictitious n-grams) and its cost measure.
- [ ] Check whether they discuss disjoint (non-overlapping) releases at all — if they do, our contrast needs rewording.

---

# NEWLY IDENTIFIED / NOT CURRENTLY CITED — Espiritu & Cash 2026, *Plaintext Recovery Against Post-Filtering Access Control*

**Full citation:** Zachary Espiritu (MongoDB Research) and David Cash
(University of Chicago). *USENIX Security '26*, pages 3753–3772. Full version
arXiv:2608.11730, submitted 12 August 2026.

**Stable primary source:** https://arxiv.org/abs/2608.11730 and
https://www.usenix.org/conference/usenixsecurity26/presentation/espiritu

**Current verification status:** **METADATA ONLY** (arXiv abstract page read;
full text not read).

**Where our repo cites or discusses it:** `docs/RELATED_WORK_NOTES.md` §8 only,
as "two things the reading list missed". **Not cited in any claim.**

**Why we would cite it:** same venue and year; it amplifies an access-control
side channel into plaintext recovery and, in the Elasticsearch/OpenSearch case,
recovers indexed terms and in places n-grams approximating corpus text. A
reviewer who knows it will expect us to.

| # | Claim | Source location | Status |
|---|---|---|---|
| 1 | Rich query predicates turn existence leakage into reconstruction | abstract | **METADATA ONLY** |
| 2 | PostgreSQL row-level security attacked via a timing side channel | abstract | **METADATA ONLY** |
| 3 | Elasticsearch/OpenSearch scoring and prefix-expansion channels recover indexed terms and sometimes n-grams approximating text | abstract | **METADATA ONLY** |

**What it takes away from our novelty:** it prevents any sweeping "first
plaintext-recovery privacy attack" claim. Their leakage channel is active
querying of access-control and index side channels; ours assumes possession of
plaintext fragments. Different threat models.

**Action:** decide whether to cite. If cited, read the primary first.

## My manual verification checklist

- [ ] Read the primary before citing anything specific.
- [ ] Confirm the threat model is active querying, not possession of fragments.
- [ ] Confirm what "n-grams approximating corpus text" means operationally.
- [ ] Decide whether it belongs in related work or can be omitted.

---

# NEWLY IDENTIFIED / NOT CURRENTLY CITED — OrderProbe 2026, *How Order-Sensitive Are LLMs? OrderProbe for Deterministic Structural Reconstruction*

**Full citation:** Zhaolu Kang and 21 co-authors (22 total). *Findings of the
Association for Computational Linguistics: EMNLP 2026*, pages 16651–16681.
Budapest, Hungary.

**Stable primary source:** https://aclanthology.org/2026.findings-emnlp.788/

**Current verification status:** **METADATA ONLY** (landing page read).

**Where our repo cites or discusses it:** nowhere. Raised in review only.

**Why we might cite it:** semantic competence does not imply exact structural
reconstruction — thematically adjacent to our precedence-versus-adjacency gap.

| # | Claim | Source location | Status |
|---|---|---|---|
| 1 | Task is restoring canonical order of scrambled fixed four-character CJK expressions | landing page abstract | **METADATA ONLY** |
| 2 | Frontier models recover fewer than 35% zero-shot | landing page abstract | **METADATA ONLY** |
| 3 | A consistent gap between meaning-oriented generation and exact structural reconstruction | landing page abstract | **METADATA ONLY** |

**Assessment:** weaker support than it appears. The task restores a *memorised
convention* (idiom word order) scored by exact match, not a reconstruction of
novel text. **Our own Game O data is far better evidence** for the
precedence-versus-exact gap: at `pairs_correct` 0.8–0.9 (n=87), mean
exact-position fraction is 0.227 and mean longest-run fraction 0.208. Cite
OrderProbe as a one-line observation at most; do not let it carry the argument.

## My manual verification checklist

- [ ] Confirm the task is fixed four-character CJK expressions, exact-match scored.
- [ ] Confirm the sub-35% figure and which models.
- [ ] Decide whether a one-line citation earns its space.

---

# Tooling and method citations that will need bibliography entries

Not prior art, but they will need entries and none exists yet. Sourced from the
code, not from memory.

| Dependency | Used by | Verification needed |
|---|---|---|
| spaCy (sentence segmentation) | `datagen/pull_prose_v4.split_sentences`, 25 references across the corpus build | Pin the version actually used; cite properly |
| `sentence-transformers/all-mpnet-base-v2`, revision `e8c3b32edf5434bc2275fc9bab85f82640a19130` | `adversaries/embedding_joint.py` (D14) | Revision is pinned in the results rows — cite model card and revision |
| Bit-parallel LCS: Crochemore et al. 2001; Hyyrö 2004 | `harness/visible_metrics.lcs_len` | Get full citations; currently author-year only in a docstring |
| `scipy.optimize.linear_sum_assignment` (Hungarian) | `harness/visible_metrics.score_sequences` | Cite SciPy |
| claude-sonnet-5 via the Batches API | every paid run | Record exact model id and the $1/$5 per-M batch rate basis |

---

# Novelty implications after source audit

### Definitely not novel

Established by sources verified above:

- **Mixed-source fragment reconstruction**, including joint membership and
  ordering. Memon & Pal 2006 (secondary) for k files; **Paixão et al. 2020
  (primary verified)** for mixed text documents at up to 100 documents.
- **Statistical text-fragment reassembly** and adjacency scoring with a
  compression-style model — Shanmugasundaram & Memon 2003.
- **LLM reconstruction of fragmented documents**, and **varying fragmentation
  granularity** — ShredBench 2026.
- **LLM-assisted semantic linkage**, and the claim that semantic attackers
  change privacy threat models — Lermen et al. 2026.
- **Fragmentation as protection for sensitive associations** — Ciriani et al. 2010.
- **That disjoint fragments can remain linkable when dependencies permit
  recombination** — De Capitani di Vimercati et al. 2014. This is the one most
  at risk of being accidentally claimed; it is a published theoretical result.
- **Reconstruction from very small textual units**, and framing it as leakage
  from a release format — Gallé & Tealdi 2015 (metadata only).
- **Scaling in the number of mixed sources** — Paixão sweeps k; we do not.

### Probably novel / distinct based on verified literature

Each survives the source-by-source comparison:

1. **The observation model.** Every verified reconstruction predecessor's
   adjacency signal is physical, visual, byte-level or overlap-based: pixel/DCT/
   edge continuity (Memon & Pal, Paixão), byte continuity via PPM (2003),
   n−1-token overlap (Gallé). None exists in Game J, where the fragment text is
   the only evidence. This is the strongest surviving distinction and it is
   verified against five sources.
2. **The measurement.** No verified predecessor separates "did I associate these
   fragments with the right source?" from "conditional on that, did I recover
   their order?". Paixão's eq. (2) is a single immediate-adjacency rate that
   additionally **gives the inter-document seam for free**; 2003's is a local
   adjacent-pair rate with no membership term. Our `F1_J = F1_L · q` factors
   exactly because both share a denominator.
3. **The two-game design.** Game O isolates ordering leakage under known
   membership; Game J adds hidden membership. No verified source runs that
   contrast.
4. **The conditionality result.** That reconstructability tracks the surviving
   linkage signal — strong for clinical prose, absent for structured
   identifiers where only a schema-aware attacker beats the reference, reduced
   by disruptive cuts — is not a claim any verified source makes.

### Still uncertain

- **Memon & Pal 2006 specifics.** Claims 2–9 in that section are secondary only.
  The concession stands; the details must not be used.
- **Whether the CVPR companion's 505-shred instance is a single mixed instance.**
- **The Gallé ~55-word figure** is unverified and should be deleted unless the
  primary supports it.
- **Whether ShredBench's NED 0.73 is a headline performance number** or part of
  a data-validation argument.
- **Whether De Capitani's group has later work covering content inference**,
  which would narrow our gap.
- **The 83% vs 86.7% Jaccard-sparsity discrepancy** between
  `memon_linkage.py` and the packet.

### Current strongest novelty framing

**Repo-agent synthesis — for the author to independently accept or reject.**
Write your own version before reading this.

> Fragmentation removes explicit associations, but disjointness does not
> necessarily remove the dependencies that allow those associations to be
> reconstructed. That insufficiency has been established for declared,
> attribute-level dependencies supplied to a protection design. We ask whether
> the implicit dependencies carried by unconstrained natural-language content
> constitute a comparable channel for a modern semantic attacker, in a setting
> where none of the physical, visual, byte-level or overlap evidence used by
> prior reconstruction work is available. We evaluate it with two games — one
> isolating ordering leakage under known membership, one measuring joint
> source-association and ordering leakage when membership is withheld — and
> report a joint score that factors exactly into a linkage component and a
> conditional ordering component. Reconstructability varies sharply with the
> signal the fragments retain.

Two contributions, not more: **(1)** the threat model and measurement framework;
**(2)** the empirical characterisation of when leakage occurs. The attacker
comparison is evidence for both, not a third contribution.

### Current repo claims that need correction

| # | Claim | Where | Problem | Proposed correction |
|---|---|---|---|---|
| 1 | Gallé recovered ~55-word chunks (max ~658) from all 5-grams | `RELATED_WORK_NOTES.md` §5 | Not in the abstract; came from a search summary attributing it to a different method | Delete, or verify against the KDD primary |
| 2 | Memon & Pal PUP specifics — headers give count/start/resolution/fragment count; O(n² log n); k-vertex-disjoint formulation | `PRIOR_ART_CODE_COMPARISON.md` §0; `RELATED_WORK_NOTES.md` §0 row 6 | All secondary; claim 8 may be misattributed to this paper | Keep the high-level concession; move specifics behind a "not primary-verified" marker until the IEEE paper is read |
| 3 | ShredBench's best model reaches NED 0.33 | `RELATED_WORK_NOTES.md` §3 | Model and subset not located | Locate or drop |
| 4 | Jaccard is 0 for 86.7% of within-document pairs | `PAPER_WRITING_PACKET.md` ~line 293 | Conflicts with `memon_linkage.py`'s "~83% exact zeros" | Determine which quantity each measures; make one authoritative |
| 5 | Ciriani's guarantee "does not model content-based relinking" | `RELATED_WORK_NOTES.md` §2 | Our interpretation presented close to source fact | Rephrase as what the correctness condition *addresses*, not what the authors claim |
| 6 | De Capitani's dependencies "cannot be enumerated in advance" | drafted phrasing in `RELATED_WORK_NOTES.md` §0 row 7 discussion | Stronger than provable | Use "declared and supplied to the protection design" versus "implicit in content and inferred by the attacker" |
| 7 | CVPR 505 shreds = "20 mixed shredded pages" as one instance | `PRIOR_ART_CODE_COMPARISON.md` §0 | Unverified | Mark open, or drop the companion citation |
| 8 | No `.bib` and no manuscript exist in the repo | — | The audit instruction assumed one | Create `paper/refs.bib` in the repo, under version control, before drafting |

### Author sign-off

- [ ] I personally read the novelty-critical papers.
- [ ] I verified the claims marked PRIMARY VERIFIED.
- [ ] I agree with the "takes away from novelty" statements.
- [ ] I agree with the "remaining distinction" statements.
- [ ] I wrote my own novelty framing before comparing it to the agent framing.
- [ ] Final Related Work language reflects my own review, not just AI synthesis.

---

**Related repo documents:** `docs/RELATED_WORK_NOTES.md` (five-prompt notes per
paper, with corrections marked), `docs/PRIOR_ART_CODE_COMPARISON.md`
(code-level comparison of our implementation against the two mixed-source
predecessors), `docs/adversaries.md` (binding attacker names and the
Shanmugasundaram & Memon wording rules), `docs/PAPER_WRITING_PACKET.md`
(methodology and results reference).
