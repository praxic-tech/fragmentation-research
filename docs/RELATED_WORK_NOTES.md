# Related work — verified notes for the novelty defense

**What this is.** A reference pass over the five papers in the reading plan,
written against the actual sources (downloaded and text-extracted, not from
memory), so the authors can write their own related-work section and answer
reviewer questions without re-reading. Same status as
`scratchpad/paper/reference_draft.tex`: AI-produced reference material, to be
rewritten in the authors' own words. The AI-use statement covers it.

**Verification date:** 2026-10-30. Sources were fetched and read, except
Gallé & Tealdi — see §0 and §5 for that one gap.

> **REVISED 2026-10-30, same day, after review.** The first version of these
> notes overstated our novelty by reviewing only the five papers in the reading
> plan. **Mixed-source fragment reconstruction is not new**: Memon & Pal (2006)
> reassemble k files at once from mixed fragments, and Paixão et al. (2020)
> reconstruct several mixed shredded text documents at once. Both are now in
> §0. Four further corrections (a withdrawn "lower bound" claim, a wrong "no
> counts" distinction, an over-strong known-first-fragment defense, and a sign
> error) are marked **[CORRECTED]** where they occur. The code-level comparison
> against the two predecessors is in `docs/PRIOR_ART_CODE_COMPARISON.md`, which
> supersedes the novelty paragraph in §6 of the original version.

**Naming discipline carries over** (`docs/adversaries.md`): the attacker is
always "Memon-inspired", never "Memon" alone, and never "pre-LLM state of the
art". When citing the 2003 paper as a work, use "Shanmugasundaram & Memon".

---

## 0. Citation ledger (verified against source)

`docs/adversaries.md` says "verify the reference against the source". Done.

| # | reference | status |
|---|---|---|
| 1 | Kulesh Shanmugasundaram and Nasir Memon. *Automatic Reassembly of Document Fragments via Context Based Statistical Models.* 2003. 8 pages. | Title, authors, affiliation (Polytechnic University) and year read off the PDF. Served from `acsac.org/2003/papers/97.pdf`, i.e. ACSAC 2003. **Page numbers are not in the PDF — get them from the ACSAC/IEEE record before the bib entry is final.** |
| 2 | Valentina Ciriani, Sabrina De Capitani di Vimercati, Sara Foresti, Sushil Jajodia, Stefano Paraboschi, Pierangela Samarati. *Combining Fragmentation and Encryption to Protect Privacy in Data Storage.* ACM TISSEC 13(3), Article 22, July 2010. | Verified in full from the PDF, including the running footer. Article 22, 33 pages → cite as `22:1--22:33`. |
| 3 | Zichun Guo, Yuling Shi, Wenhao Zeng, Chao Hu, Haotian Lin, Terry Yue Zhuo, Jiawei Chen, Xiaodong Gu, Wenping Ma. *ShredBench: Evaluating the Semantic Reasoning Capabilities of Multimodal LLMs in Document Reconstruction.* Findings of ACL 2026, pages 22603–22615. | Verified from the ACL Anthology landing page and the paper PDF. Nine authors — do not truncate silently. |
| 4 | Simon Lermen, Daniel Paleka, Joshua Swanson, Michael Aerni, Nicholas Carlini, Florian Tramèr. *Large-scale online deanonymization with LLMs.* USENIX Security '26, pages 1947–1966. | Verified from the USENIX page and the paper PDF. Note the title is "deanonymization", not "semantic linkage" as the reading plan labelled it. |
| 5 | Matthias Gallé and Matias Tealdi. *Reconstructing Textual Documents from n-grams.* KDD '15, pages 329–338. DOI 10.1145/2783258.2783361. | Metadata verified via the NAVER LABS Europe publication page and the ACM DOI. **The CiteSeerX link in the reading plan is dead (HTTP 404)** — do not keep it. Full text not obtained; see §5. |

**Added on review — the two mixed-source predecessors the reading plan omitted:**

| # | reference | status |
|---|---|---|
| 6 | Nasir Memon and Anandabrata Pal. *Automated reassembly of file fragmented images using greedy algorithms.* IEEE Transactions on Image Processing 15(2):385–393, February 2006. | **SECONDARY ONLY — not read.** IEEE-paywalled. The Parallel Unique Path (PUP) algorithm reassembles **k files simultaneously** from mixed fragments, growing one path per file from the k file headers and removing assigned fragments from other files' candidate sets; later cast as a k-vertex-disjoint path problem. **Read in full before citing.** |
| 7 | Thiago M. Paixão, Rodrigo F. Berriel, Maria C. S. Boeres, Alessandro L. Koerich, Claudine Badue, Alberto F. De Souza, Thiago Oliveira-Santos. *Self-supervised Deep Reconstruction of Mixed Strip-shredded Text Documents.* Pattern Recognition, 2020. DOI 10.1016/j.patcog.2020.107535 (arXiv:2007.00779). Companion: *Fast(er) Reconstruction of Shredded Text Documents via Self-Supervised Deep Asymmetric Metric Learning*, CVPR 2020, DOI 10.1109/CVPR42600.2020.01435 (arXiv:2003.10063). | **PRIMARY — both PDFs read.** "The reconstruction of several mixed shredded documents at once." Images of shreds, not text; one global permutation solved exactly as an ATSP with Concorde; k swept 1…100; >90% accuracy on 100 mixed documents (2,292 shreds). |

Two housekeeping notes:

- The reading-plan URLs carry `utm_source=chatgpt.com` tracking parameters.
  Strip them before anything goes near the bibliography.
- The plan dates Gallé & Tealdi 2015 and labels ShredBench and Lermen 2026.
  All three are right.

---

## 1. Shanmugasundaram & Memon (2003) — classical fragment reassembly

**1. What problem are they solving?**
Digital-forensic reassembly: given the fragments of a file recovered from a
disk, swap file or slack space, with no file-table or page-table metadata,
compute the permutation that concatenates them back into the original. They
frame it as the digital equivalent of classical physical-evidence reassembly.
Their worked motivation includes an adversary who deliberately splits a
document and scatters the pieces across a peer-to-peer store.

**2. What does their attacker know or receive?**
- The complete set of fragments of **one** document, lossless: they state the
  assumption that concatenation in the proper order yields the original intact.
- No ordering metadata.
- **The identity of the first fragment is assumed known**, justified by file
  headers. Their tree-pruning search is rooted at it.
- No external corpus. The statistical model is built *from the fragments
  themselves* — each fragment is run through PPM and the per-fragment
  statistics are merged into one model of the document.

**3. What is the closest overlap with our study?**
The core mechanism: score whether fragment B follows fragment A by how well a
statistical model of the text predicts the characters across the candidate
boundary, then search for a high-scoring path through all fragments. That is
exactly the idea our Memon-inspired attacker borrows, and the honest extent of
the borrowing.

Mechanically: a sliding window of size n sits at the end of A and slides d
characters into B; at each position PPM (PPMC blending, orders 0..k) estimates
the next character; the product of those probabilities is the candidate
adjacency probability C(i,j). **[CORRECTED]** Maximising the product over
permutations is equivalent to **minimising** the sum of −log C (equivalently,
maximising the sum of log C) — the first version of this note said "maximising
a sum of −log C", which is backwards. The paper's own equation (2) as printed
reads "maximizing" over a −log term, and its Figure 1 instead sums raw
probabilities along the path, so **cite their Hamiltonian-path reduction, not
the transformation, and do not reproduce the sign.** Our implementation is
correct: `adversaries/memon.py:score_pair` returns a log probability and
`memon_order_guess` maximises the sum of them. Either way the search problem is
a **maximum-weight Hamiltonian path** in the complete graph of fragments. That
is intractable, so
they use α-β tree pruning (from game-tree search) rooted at the known first
fragment, keeping β best paths per level and returning the top-β near-optimal
orderings.

**4. What is the most important difference?**
**They explicitly scope out the mixed-source problem.** Their three-step
process model is Preprocessing → Collating → Reassembling, where Collating is
"group the fragments that belong to each document" and they say in §1:

> "Although, in this paper, we consider reassembling a single document, in
> reality evidence is usually a collection of mixed fragments of several
> documents of different types."

They then state that they focus on the final step, reassembling one document
from preprocessed fragments of that document, and the conclusion lists the
grouping step as future work: they plan to investigate collating fragments
from mixed fragments of several documents using text-classification methods.

**[CORRECTED — this was over-read in the first version.]** The quotation is
genuine and worth citing, but it establishes only what *that paper* did and did
not do. It does **not** establish that the problem stayed open: the same group
closed it three years later with PUP (Memon & Pal 2006, ledger row 6), which
reassembles k files at once by growing one path per file, and Paixão et al.
(2020, row 7) did it for mixed shredded text documents. So this is **historical
context about the 2003 paper**, not a novelty argument for us. Do not write
anything implying the mixed-source problem was unsolved after 2003.

Four further differences, all of which matter for the baseline defense:

- **Granularity and units.** Their fragments are byte-level disk blocks; each
  document was randomly split into 100–200 pieces of mixed file types (logs,
  C/C++/Java/Lisp source, executables, Office/PDF binaries, plain text,
  encrypted/compressed data). Ours are linguistic units — sentences, clauses,
  or fixed-width word runs — cut at known boundaries.
- **Their metric is not comparable to ours.** Accuracy is "the number of
  adjacent fragments in the reassembled document that are in fact adjacent in
  the original": a local adjacent-pair rate. It is not a permutation score and
  has no membership component, so **no number in that paper can be put beside
  F1_J, F1_L or q.** Do not tabulate one.
- **Plain text was among their hardest cases.** Single-pass top-β accuracy
  (Table 2): log files 57.7–68.0%, executables 30.0–33.4%, binary files
  23.4–28.4%, unformatted text 26.4–31.0%. They attribute the gap to
  structure, cross-checking it against compression ratio, and note chat
  transcripts are hard because the words are unpredictable. Context orders 3–5
  worked best; larger contexts did not help.
- **The human in the loop is part of the design.** The deliverable is the top
  β orderings for an analyst, who confirms correct subsequences, merges them
  into unit fragments and re-runs; Table 3 reports convergence in 4 (logs) to
  10 (unformatted, binary) iterations. Our games score a single autonomous
  answer with no analyst and no iteration.

**5. What claim in our paper does this change or constrain?**

- Our framing improves. "Prior work studied ordering fragments of a single
  document" is true but weak; "the original formulation names source grouping
  as a separate step and leaves it to future work" is specific, checkable and
  much harder to argue with.
- **Add a third substitution to the Memon-inspired description.**
  `docs/adversaries.md` currently lists the substitutions as: fixed-order
  smoothed character model instead of PPM; TF-IDF grouping added; tanh
  weighting; local ordering search instead of Hamiltonian-path/tree-pruning;
  masking controls. Missing: **their search requires a known first fragment,
  and Game J provides none.** That is not a design preference, it is a missing
  input, and it belongs in the one-sentence substitution note.
- **[CORRECTED — the "lower bound" claim is withdrawn.]** The first version
  said a smoothed fixed-order bigram model is weaker than PPMC escape-blended
  multi-order prediction, so our numbers are a *lower bound* on a classical
  statistical attacker. That does not follow: a model that is stronger in one
  setting is not necessarily stronger on this corpus, and we never ran PPMC
  here. The safe claim, and the only one to put in the paper: **this is one
  tested statistical baseline — neither a faithful implementation of the 2003
  method nor an estimate of the strongest attainable classical performance.**
  This sentence was *not* added to `docs/adversaries.md`.

### Reviewer question: "Why didn't you implement the original method faithfully?"

**[CORRECTED — softened. The first version called this "airtight"; it is not.]**
Because the method's required inputs are absent in Game J, so it cannot be run
as specified. That makes faithful replication infeasible — it does **not** make
a comparable classical attacker impossible, and we should not claim it does. An
adaptation could enumerate candidate starting fragments at k× cost, or
re-anchor the search some other way. We chose a different adaptation; a
reviewer may reasonably ask why not that one. The three absent inputs:

1. It reassembles the fragments **of one document**; Game J hands the attacker
   a pool mixed across seven documents, and the grouping step the original
   needs beforehand is the step the original defers to future work.
2. Its search is **rooted at a known first fragment** (file headers). Our
   fragments are masked prose with no header, no identifying structure, and no
   privileged starting point.
3. Its PPM model is built from the fragments of the single document being
   reassembled. Built over a seven-document pool it models a mixture, which is
   precisely the confound the Collating step was supposed to remove.

So we take the mechanism — statistical adjacency scoring over the fragments'
own text, plus a search for a high-scoring path — implement it with a
smoothed character-bigram boundary likelihood and a deterministic local
ordering search, label it **Memon-inspired**, name the substitutions, and cite
the original for the context-model idea only. We do not claim it represents
that method's attainable performance, and we report it as a statistical
attacker sitting at the floor on this corpus, not as a competitive one.

One further note. **PUP also starts from the file headers** — it grows one path
per file from k known starting fragments. **[CORRECTED]** An earlier version
then concluded that lacking an anchor is the single dimension on which Game J
is harder than *both* reconstruction predecessors. That is wrong: Paixão needs
no anchor either, because the ATSP is solved globally. Two separate axes:

- **supplied anchor** (the attacker is told which fragment starts a document):
  PUP yes; Paixão no; Game J no.
- **boundary-continuity evidence** (a physical or byte signal that two pieces
  abut): PUP yes (pixel/DCT/median-edge); Paixão yes, and it is the CNN's whole
  input; **Game J no.**

The distinction to press is therefore **continuity, not anchoring**: no
predecessor's adjacency signal exists in Game J because there is no physical,
visual or byte-level cut to inspect. On known source count, exact partition and
known cut boundaries we are as attacker-favourable as they are, or more so.
Full table in `docs/PRIOR_ART_CODE_COMPARISON.md` §1.

---

## 2. Ciriani et al. (2010) — fragmentation for privacy

**1. What problem are they solving?**
Outsourcing a relation to an honest-but-curious server while protecting
sensitive *associations* between attributes, and doing it without encrypting
everything — because encrypted data makes query processing expensive. The
design goal is to keep as much as possible in plaintext.

**2. What does their attacker know or receive?**
The physical fragments stored at the server: for each fragment, a subset of
attributes in the clear, plus `salt` (the primary key) and `enc`, the
encryption of all remaining attributes of the tuple XOR-ed with the salt
(CBC with the salt as IV, or a semantically secure cipher). The attacker does
not have the key. The salts need not be secret.

**3. Key definitions, in their numbering**
- **Def 2.1, confidentiality constraint:** a subset `c` of the attributes `A`,
  whose *joint* visibility must be prevented. A singleton constraint means the
  attribute's values are sensitive on their own (so it must be encrypted). A
  non-singleton constraint means the association must not be disclosed —
  `{DoB, ZIP, Illness}` can be sensitive as a triple while `{DoB, ZIP}` and
  `Illness` are each releasable. Constraints may also encode inference
  channels, not just explicit secrets.
- **Def 2.2, well-defined:** no constraint is a subset of another (a subset
  constraint makes the superset redundant).
- **Def 3.1/3.2, fragmentation and physical fragment:** fragmentation is
  attribute-level; every physical fragment carries *all* original attributes,
  in the clear or inside `enc`, so any query can be answered from a single
  fragment.
- **Def 3.3, correctness — two conditions.** (1) No fragment is a superset of
  any constraint. (2) **Fragments are pairwise disjoint in their cleartext
  attributes**, so no plaintext attribute can be used to join two fragments
  back together.
- **§4:** maximising plaintext visibility subject to correctness is the
  *minimal fragmentation* problem, which is **NP-hard** (Thm 4.3, by
  correspondence with hypergraph colouring); §5 defines vector-minimality and
  gives a heuristic.

**4. Why encryption at all?** Singleton constraints are unsatisfiable by
fragmentation alone — you cannot split a single attribute away from itself —
so they must be encrypted. And `enc` is what lets one fragment answer any
query. Salting defeats frequency analysis on the ciphertext.

**5. What is the most important difference, and what it constrains in our paper?**
Condition (2) of Def 3.3 is the whole story. **Their unlinkability guarantee is
syntactic and is about one specific channel: a shared plaintext attribute used
as a join key.** It is established by construction, not measured, and it says
nothing about an adversary who relinks fragments by reasoning over their
*content*. There is no language in their model for "these two cleartext values
read like they came from the same tuple".

That is the gap our experiment probes, and it is also the reason our result
cannot be presented as an evaluation of their scheme:

- Their unit is an attribute of a relation; ours is a run of natural-language
  text from a document.
- Their fragments are disjoint *by construction* in the clear; our Game J pool
  is a disjoint partition too, but the attacker receives **all** fragments of
  all seven documents at once and is asked to regroup them. Nothing in their
  threat model grants an adversary that view and then asks this question.
- They give a formal guarantee under a stated constraint language; we report
  measured attacker success under a plaintext-fragment threat model of our own.

### Reviewer question: "Does your synthetic identifier result validate Ciriani's privacy guarantees?"

No, and the paper must say so explicitly. Different system, different data
model, different threat model, different kind of claim. Ciriani et al. prove
that a correct fragmentation prevents constraint violation by *attribute-level
linking*; we measure whether a particular family of attackers can regroup and
order *plaintext text fragments* by content. A negative result of ours would
not establish their guarantee, and a positive result would not refute it — it
would be evidence about a channel their correctness condition does not model.
Our synthetic identifier corpus is a structured-data stress test for *our*
games, not an instantiation of their scheme.

Worth one sentence of related work: the same group's later work on
fragmentation without encryption and on loose associations is where the
content/inference channel starts to be discussed in the database literature.
Cite it if a reviewer is likely to know it, but verify those references
separately — they were not part of this pass.

---

## 3. ShredBench (Findings of ACL 2026) — LLM document reconstruction

The strongest prior-art challenge of the five, and the cleanest to separate.

**1. What problem are they solving?**
Whether multimodal LLMs can restore the *content* of a shredded document, as a
probe of semantic reasoning under structural disruption. Their motivation is
that MLLMs are benchmarked on pristine document images.

**2. What does the model receive?**
**Images.** Their own task formulation: a set `I = {f1 … fN}` of unordered,
scattered **image fragments derived from a single source document D**,
possibly rotated and subjected to lighting distortion, rendered with paper
texture via a 3D synthesis stage. Documents are rendered from Markdown at
1600px width with CSS styling, in bordered and borderless layouts.

The pipeline is Data Collection → Shredding Simulation → 3D Synthesis.
Sources: bilingual (English/Chinese) news filtered to 800–2,500 characters,
programming code (C++, Java, Python) and scientific tables.

**3. How is granularity varied?**
**Voronoi cutting into 8, 12 or 16 pieces** (k-d tree over seed points),
chosen deliberately over grid crops so that models cannot exploit trivial
straight-edge matching — their Table 1 contrasts this with grid-crop
benchmarks (2×2 to 5×5). So three granularity levels, all coarse, and the
difficulty lever is **visual irregularity**.

**4. What metrics?**
NED (normalized Levenshtein distance, **lower is better**), TEDS for tables,
BLEU and ROUGE-L — all text-similarity measures between the restored string
and the ground-truth text. State-of-the-art models average **NED 0.73**, which
the authors read as a model reasoning failure rather than a data defect, with
the strongest model (Gemini 3 Pro) reaching NED 0.33 in the best breakdown.
Degradation with piece count is the headline finding.

Critically: the task is **set-to-sequence**, output is the text string, and
they state it explicitly — unlike geometric jigsaw work, they do **not**
require predicting each piece's spatial coordinates. So:

- **No membership component.** All pieces come from one document. The phrase
  "mixed-source", "cross-document" or "multiple documents" appears nowhere in
  the paper.
- **No permutation metric.** Edit distance on the recovered text does not
  decompose into a grouping term and an ordering term. There is no analogue of
  `F1_J = F1_L × q`, and no analogue of q at all.

**5. What claim does this change or constrain?**
It constrains the novelty claim hard, and it should be cited prominently
rather than buried:

- We must **not** claim novelty for "LLMs reconstructing fragmented documents"
  or for "varying fragmentation granularity". Both are established, in a 2026
  paper, with a public benchmark.
- What is left, and is genuine: plaintext rather than rendered images;
  fragments mixed across seven source documents so that **membership is itself
  unknown**; a metric that separates the linkage component from the ordering
  component; a granularity range that goes two orders finer (28 down to ~532
  fragments per pool, against 8–16 pieces); and a privacy threat model with a
  closed-form trivial-strategy reference on every Game J unit rather than a
  capability benchmark. **[CORRECTED]** Not "calibrated baselines and
  permutation nulls" — the nulls exist only in the single-token edge-case
  experiment, and the analytic reference is not chance for a valid N-group
  answer (`docs/PRIOR_ART_CODE_COMPARISON.md` §4A).
- It also *supports* us where the mechanisms differ: their difficulty lever is
  visual discontinuity across irregular cut edges, ours is the removal of
  semantic context. Their result that performance falls with piece count is a
  useful independent echo of our granularity finding in a different modality —
  cite it as convergent evidence, not as competition.

### Reviewer question: "Haven't ShredBench's authors already studied LLM reconstruction and fragment granularity?"

Yes — and we say so in the related-work section, in those words. Our novelty
is neither of those alone. It is the joint membership-and-order evaluation on
mixed-source plaintext, the decomposition of the score into linkage and
ordering, and the attacker comparison under a privacy threat model with
calibrated baselines.

---

## 4. Lermen et al. (USENIX Security '26) — LLM deanonymization

Note the real title is *Large-scale online deanonymization with LLMs*. The
reading plan's "semantic linkage" is a description, not the title.

**1. What problem are they solving?**
Re-identifying people behind pseudonymous accounts and conversations using LLM
agents, in two regimes: an open-world agentic setting where the agent searches
the live web, and a **closed-world** setting where the match must be found in a
fixed candidate database.

**2. What makes it closed-world, and what does the attacker know?**
Two explicit difficulty parameters:

- **A fixed candidate pool.** For the Hacker News → LinkedIn experiment, about
  **89,000** active HN users, with 5,000 query profiles.
- **The a priori probability λ that a query has a match.** In the main
  experiments the true match is guaranteed to be in the candidate set — λ = 1,
  the prior of a match existing is 100%.

They are candid that both make the attack easier, and **§6.4 varies both**
(Figure 7: recall at 90% precision against pool size, with log-linear
extrapolation to larger pools; and against λ). That is the methodological
move we should pay attention to.

**3. How do embeddings and LLM reasoning combine?**
Three modular stages, each runnable with or without an LLM so the
contributions can be ablated:

1. **Extract** — an LLM summarises each profile into identity-relevant
   features (posting history, interests, location cues).
2. **Search** — semantic embeddings of those summaries retrieve a top-k
   shortlist (15 highest-scoring candidates per query in the reported runs).
3. **Reason** — a two-stage verification: a fast model selects the most likely
   candidate from the shortlist or abstains, and a stronger reasoning model is
   spent only on a single promising match. A confidence score is thresholded
   to trace precision–recall.

**4. Metrics and results.** Recall@Precision, where recall is over *matchable*
users. The ablation is the striking part: on HN → LinkedIn, recall at 99%
precision goes from **4.4% (Search only) to 45.1% (with Reason)**, against
about **0.1%** for an adapted classical baseline (a Narayanan-style 332-attribute
binary feature vector). The abstract's headline is up to **55% recall at 90%
precision** where the best non-LLM method is near zero. The open-web agentic
study reaches 25–67% recall at 70–90% precision (226 of 338 targets, 67%, at
90% precision). Full pipeline cost at most **$0.23 per target**.

*Caveat on these numbers:* they were read out of a two-column PDF whose
columns interleave in extraction. The shape is solid; verify any exact
figure against the paper before it appears in our text.

**5. Is any task about ordering or grouping fragments?** No. Every task is
matching a profile to an identity, or matching two split profiles of one user
to each other. There is no within-source ordering and no document
reconstruction.

**What it changes or constrains in our paper:**

- **It is the precedent for our attacker architecture, and we should say so.**
  Their Search-then-Reason structure — embedding retrieval, then LLM
  verification — is the same decomposition our embedding attacker and one-shot
  Sonnet attacker occupy separately. Their ablation showing embeddings alone
  far below embeddings-plus-reasoning is **[CORRECTED]** *consistent with* the
  gap we observe between the embedding attacker and the LLM attacker — not
  support for it and not an explanation of it. Different pipelines, different
  task, no shared control. The two findings agree in direction, which earns one
  sentence; it is not a controlled replication and must not read as one.
- **It legitimises the closed world and sets the standard we fall short of.**
  Our known-N = 7 closed world with a guaranteed partition is the same kind of
  attacker-favourable simplification as their fixed pool with λ = 1 — so the
  design is defensible and has precedent. But they *vary* both parameters and
  extrapolate; **we vary neither.** We should state that plainly as a
  limitation and name pool size (N) and the guarantee that every fragment
  belongs to exactly one in-pool document as the two parameters a future
  version would sweep. This connects directly to the deferred J-floors /
  embedding-attacker work.
- It also supplies the cost framing: their "$0.23 per target" is the kind of
  number that makes a capability result into a privacy result. Our own
  per-pool costs are recorded in the ledger and could serve the same purpose.

### Reviewer question: "Is your seven-document known-N setup artificially favourable to the attacker?"

Yes. Concede it directly, in one short paragraph, and do not hedge. The
attacker is told the number of source documents, every fragment is guaranteed
to belong to exactly one of them, the partition is exact, and the pool is
small. This is a restricted, attacker-favourable closed world chosen so that
membership and ordering can be scored exactly against a known key — not a
model of any deployment. Results are upper bounds on nothing and lower bounds
on nothing with respect to a real system; they characterise this game. Prior
deanonymization work makes the same simplification deliberately (fixed
candidate pool, guaranteed match) and then measures sensitivity to it; we do
not, and that is a limitation we name rather than defend.

---

## 5. Gallé & Tealdi (2015) — reconstruction from n-grams

**Caveat: this section rests on the published abstract and the authors'
publication page, not the full text.** The reading plan's CiteSeerX link is
dead (404) and the ACM version was not retrieved. Everything below is
consistent across both sources, but **the full paper should be read before
these notes are relied on for a specific claim**, and before any sentence of
our related-work section cites a detail rather than the result.

**1. What problem are they solving?**
Given only the **n-grams of a corpus and their counts, for a fixed n**, how
much of the original text can be rebuilt? Their target is the set of longest
contiguous substrings that *must* appear in the originals — i.e. what the
n-gram release necessarily leaks. The motivation is privacy of released n-gram
statistics, so the framing is close to ours.

**2. What does the attacker receive?**
The complete n-gram inventory with counts ("perfect n-gram information", in
the companion workshop paper's phrasing), and n itself. Not the document
boundaries, not the ordering.

**3. Method, and the closest overlap with our study.**
A **de Bruijn graph** in which n-grams are edges, so every Eulerian cycle is a
plausible reconstruction. They give two reduction rules that shrink the graph
while preserving all possible reconstructions and lengthening edge labels, and
prove that iterating them yields an irreducible equivalent graph. Evaluated on
Project Gutenberg by the number and size of recovered substrings; a related
method of theirs recovered chunks averaging ~55 words (maximal averaging ~658)
from the set of all 5-grams. On defense: dropping low-frequency n-grams barely
helps, while **adding fictitious n-grams** makes reconstruction much harder at
small cost in language-model perplexity.

The overlap is the headline: reconstruction from very small textual units is
established, and it works well.

**4. What is the most important difference?**
**Order-n n-grams overlap by n−1 tokens.** Adjacency is handed to the attacker
*inside the data* — that is exactly why the de Bruijn/Eulerian formulation
applies at all, and why recovery is so effective. Our fragments are a
**disjoint partition**: their union is the text and no two share any token, so
there is no overlap evidence whatsoever, and adjacency has to be inferred from
language and meaning.

**[CORRECTED — the first version said "they have multiplicity counts, we do
not". That is wrong twice over.]** Our attacker sees every repeated fragment
string in the pool, so the input *does* carry multiplicity information — and
our own primary scorer is built on it: `harness/visible_metrics.py:128` computes
V_L as a **multiset intersection**, `np.minimum(count_vector, true_counts)`,
crediting a predicted group for having the right *number of copies* of each
token. The real distinction is narrower and stronger: **overlapping n-grams
reveal exact shared-token relationships between neighbouring windows; disjoint
fragments do not.** That is what makes the de Bruijn construction work, and it
is what we lack. The remaining difference is membership — they reconstruct a
corpus without deciding which document a piece came from; we require it first.

So "small units are reconstructable" and "our one-word fragments are
reconstructable" are claims about different information, not the same claim at
two scales.

**5. What claim does this change or constrain?**
It constrains the single-token result more than anything else in the list:

- Drop any suggestion that reconstruction from word-level units is new. It is
  not. **[CORRECTED]** The first version said a "disjoint, **uncounted**,
  mixed-source partition carries **strictly less structural information** than
  an overlapping n-gram inventory." Both italicised parts are wrong and are
  removed: our fragments *are* counted — repeated strings are visible to the
  attacker and scored as multiplicities by `visible_metrics` — and a
  strictly-less-information claim is an ordering over two different observation
  models that we have not proved and do not need. The defensible statement is
  specific, not comparative: **overlapping n-grams (n > 1) expose shared-token
  relationships between neighbouring windows; our disjoint fragments do not.**
  The two observation models reveal *different* information.
- It reframes what the right variable is. Their work implies fragment *size*
  is not the quantity that governs reconstructability — **overlap and
  duplication structure** is. We already measured the analogue: 44.4% of
  one-word fragments share their surface text with another fragment, falling to
  5.4% at two words and under 1% at three and four. That table is the right
  place to engage Gallé & Tealdi, and it is also the reason the visible-text
  scorer was frozen as primary.
- Their defense result (fictitious n-grams work, pruning rare ones does not)
  is the closest thing in the five papers to a mitigation finding. If our
  discussion gestures at mitigations, it should cite them rather than
  improvise.

### Reviewer question: "Does your one-word result establish a minimum safe fragment size?"

No, and the paper should foreclose the reading. It is post-hoc exploratory
evidence for the tested excerpts, the tested attackers and this closed-world
game. Two granularities cannot locate a threshold, which is what the
prospective 4/3/2-word arms (D18) are for — and even five points on the same
20 pools would give a dose–response curve on one corpus with one model, not a
safe minimum. The duplicate-text measurement above is the reason to be
sceptical of "fragment size" as the governing variable in the first place.

---

## 6. The test: why does this paper still deserve publication?

**[CORRECTED — the first version of this answer claimed the joint
membership-and-ordering problem was unestablished. That was wrong, and it was
wrong in the most dangerous possible place. Replaced.]**

The answer to have ready, without notes:

Every ingredient is established, **including the joint problem.** Classical
forensic reassembly solved k-file reconstruction from mixed fragments in 2006
(PUP: one path grown per file from the k file headers, fragments removed from
other files' candidate sets). Paixão et al. reconstructed several mixed
strip-shredded text documents at once in 2020, sweeping the number of mixed
documents from 1 to 100 and reporting over 90% accuracy. ShredBench
reconstructs image fragments of a single document with an LLM. The
deanonymization work matches identities and never orders or groups fragments.
The fragmentation-for-privacy literature guarantees unlinkability against joins
on shared plaintext attributes and does not model content-based relinking.

So we are not first to mixed-source reconstruction, and we should say so in the
related-work section rather than wait to be told. What is ours is narrower:
**the fragments are plaintext.** Both reconstruction predecessors rely on a
signal that does not exist here — pixel, DCT and edge continuity across a
physical or byte-level cut, which in Paixão's case *is* the model's entire
input. Game J supplies none of it, so language is the only available evidence.
(PUP additionally starts from k known file headers; Paixão does not need an
anchor, so anchoring is a difference from PUP alone, not from both.) On top of
that we report a score that factors exactly into a linkage component and a
conditional ordering component — which neither predecessor's single
adjacent-pair accuracy can express, and which measures a different thing from
it: ours counts **all** within-document precedence pairs, theirs counts only
**immediate adjacency**. And we measure how reconstruction varies across
attacker families, fragmentation strategies, granularities and data types on
frozen pools, against a closed-form trivial-strategy reference that neither
predecessor reports at all.

The contribution is that measurement and its decomposition in the plaintext,
no-continuity setting — not the invention of mixed-source reconstruction, and
not any single ingredient. Three things to concede in the same breath: both
predecessors vary the number of mixed sources and we hold N = 7 fixed; our
statistical baseline is not a competitive reproduction of prior reassembly
methods; and the analytic reference is a trivial-strategy benchmark, not chance
for a valid 7-group answer (`docs/PRIOR_ART_CODE_COMPARISON.md` §4A).

See `docs/PRIOR_ART_CODE_COMPARISON.md` for the code-level version of this
argument, with file paths and function names.

---

## 7. What to change in our own files

Concrete, in rough priority order:

0. **Related work must name the mixed-source predecessors** — Memon & Pal
   (2006) and Paixão et al. (2020), in the paragraph that introduces Game J,
   not buried later. This is the correction that matters most; everything else
   here is tuning. **And read the 2006 paper in full first** — our knowledge of
   PUP is secondary.
0b. **Limitations: the fixed-N gap now has three independent precedents
   against it** — Lermen's §6.4 sweeps candidate-pool size and match prior,
   Paixão sweeps k from 1 to 100 and finds accuracy does not degrade, and PUP is
   defined for arbitrary k. Our N = 7 is fixed and unswept. Name it as a gap.
0c. **State the F1_J interpretation boundary wherever F1_J is first reported.**
   `ordered_pairs` scores **all** within-document precedence pairs, not
   immediate adjacency, so F1_J = 0.723 does not mean 72% of the text was
   recovered or 68% of adjacent fragments rejoined. Our own Game O data puts
   numbers on the gap: a pairwise precedence rate of 0.8–0.9 goes with ~23% of
   fragments exactly placed and a longest intact run of ~21%
   (`docs/PRIOR_ART_CODE_COMPARISON.md` §4B). Two free fixes belong with it —
   a random-valid-partition baseline for prose Game J, and
   `reconstruction_detail` computed for Game J, which currently is not.
1. **`docs/adversaries.md`** — add the known-first-fragment point to the
   Memon-inspired substitution list, and add that their accuracy metric is
   adjacent-pair correctness, so no number from that paper is comparable to
   F1_J / F1_L / q. One line each.
2. **Related-work section** — lead the LLM paragraph with ShredBench and
   concede both ideas (LLM reconstruction, granularity variation) in the first
   sentence. Conceding early is what makes the rest of the paragraph credible.
3. **Limitations** — one paragraph on the closed world: known N = 7,
   guaranteed exact partition, small pool, neither parameter varied; name pool
   size and the match-guarantee as the two sweeps a future version owes, and
   cite the deanonymization work as the precedent for doing so.
4. **Memon-inspired framing** — **[CORRECTED]** say only that it is one tested
   statistical baseline, neither a faithful implementation nor an estimate of
   the strongest attainable classical performance. The earlier "lower bound on
   a classical statistical attacker" wording is withdrawn and must not be
   added to `docs/adversaries.md`.
5. **Single-token discussion** — engage Gallé & Tealdi where the duplicate-text
   table already is, and make the overlap-versus-disjoint distinction
   explicitly. Keep "locates no threshold".
6. **Bibliography** — replace the dead CiteSeerX link with the ACM DOI, strip
   the tracking parameters from all five URLs, get the ACSAC page numbers, and
   keep all nine ShredBench authors.

## 8. Two things the reading list missed

- **Zachary Espiritu and David Cash. *Plaintext Recovery Against
  Post-Filtering Access Control.* USENIX Security '26, pages 3753–3772;
  arXiv:2608.11730.** Turns existence leakage under rich query predicates into
  reconstruction, and in the Elasticsearch/OpenSearch case recovers indexed
  terms and in places **n-grams that approximate corpus text**. Same venue and
  year as the deanonymization paper, and it is text reconstruction from a
  partial-visibility channel. A reviewer who knows it will expect us to. Worth
  reading before submission; metadata verified from the arXiv abstract page,
  full text not read.
- The **fragmentation-without-encryption and loose-associations** line from the
  same group as Ciriani et al. — that is where the content-inference channel
  surfaces in the database literature. Not verified in this pass; check the
  references before citing.
