# Prior art vs. our implementation — a code-level comparison

**Why this exists.** The related-work notes compared *papers*. This compares
**our code** against the two closest mixed-source predecessors, because the
novelty claim has to survive a reviewer who asks "what does your attacker
actually do that theirs doesn't". Every claim about our side cites a file and a
function.

**Date:** 2026-10-30. **Verdict up front:** mixed-source fragment
reconstruction is **not ours**. It was solved for byte/image fragments in 2006
and for shredded text pages in 2020. What survives is narrower and should be
stated narrowly — see §7.

---

## 0. The two predecessors, and how well I verified them

| work | what it is | verification |
|---|---|---|
| **Memon & Pal (2006)**, *Automated reassembly of file fragmented images using greedy algorithms*, IEEE TIP 15(2):385–393 | The **Parallel Unique Path (PUP)** algorithm: reassembles **k files at once** from a pool of mixed fragments. | **SECONDARY ONLY.** IEEE-paywalled; I did not read it. Everything below comes from secondary descriptions (Pal & Memon, *The evolution of file carving*, 2009; a JOWUA carving survey; the related USPTO patents). **Read it before citing any specific claim.** |
| **Paixão et al. (2020)**, *Self-supervised Deep Reconstruction of Mixed Strip-shredded Text Documents*, Pattern Recognition, DOI 10.1016/j.patcog.2020.107535 (arXiv:2007.00779); and the companion CVPR 2020 paper (arXiv:2003.10063, DOI 10.1109/CVPR42600.2020.01435) | Reconstructs **several mixed shredded text documents at once**. | **PRIMARY.** Both PDFs downloaded and text-extracted; quotations and equation (2) below are read off the paper. |

### Memon & Pal (2006) — PUP, as far as secondary sources establish it

- Fragments are nodes; a directed edge weight is the likelihood that fragment
  *j* follows *i*. The weight comes from image-specific signals: pixel
  matching, DCT, median edge detection.
- PUP is a variant of Dijkstra single-source shortest path run **in parallel,
  one path per file**. A fragment assigned to one file is removed from every
  other file's candidate set — that is the "Unique" in the name.
- **It starts from the file headers.** The k starting fragments are known.
- Complexity O(n² log n). Later refined by Pal et al. as a **k-vertex-disjoint
  path problem**, and extended with Sequential Hypothesis Testing (SHT-PUP).
- Assumes all blocks present, no holes.

**So the joint problem has a 2006 solution.** PUP simultaneously decides
membership (which of k paths a fragment joins) and order (its position in that
path). Structurally that is Game J. The 2003 paper deferred Collating; the same
group closed it three years later. **Our notes must not imply otherwise.**

### Paixão et al. (2020) — mixed strip-shredded text documents

From the abstract: the work extends their single-page method to "the
reconstruction of several mixed shredded documents at once."

- **Input is images of paper shreds**, scanned at 300 dpi, one JPEG per shred.
  Not text. Compatibility is a two-class (valid/invalid) CNN over the
  side-by-side pixel content of a shred pair, trained self-supervised on
  simulated shredding.
- **Output is one global permutation.** They solve a Minimum-cost Hamiltonian
  Path, converted to an Asymmetric TSP by adding a zero-weight dummy vertex,
  reduced to symmetric TSP, and solved **exactly** with Concorde.
- **Membership is implicit, not predicted.** Documents appear as contiguous
  runs inside the single permutation. There is no grouping step and no
  predicted partition.
- **The metric, their equation (2):**
  `accuracy = (1/(N−1)) · Σᵢ 1[R⁻¹(i) matches R⁻¹(i+1)]`
  where a *match* is either an intra-document consecutive pair `(sᵢ⁽ᵈ⁾, sᵢ₊₁⁽ᵈ⁾)`
  **or an inter-document seam** `(s_last⁽ᵈ¹⁾, s₁⁽ᵈ²⁾)` with d1 ≠ d2 — because,
  in their words, "the order these documents appear is not relevant". So the
  document boundary is free.
- **They sweep the number of mixed documents.** k = 1…5 in the ablation, plus
  k = 10, 15, 20, … up to N_docs (60, 20, or 100), with instances built by
  adding one document at a time. Headline: accuracy >90% on 100 mixed
  shredded documents (2,292 shreds), and adding documents "does not degrade
  accuracy".
- The CVPR companion reports ~22× speed-up on a 505-shred instance drawn from
  **20 mixed shredded pages from different documents**.

---

## 1. What the attacker receives, and what is hidden

**Ours — `adversaries/joint_game.py`.**

`prompt_J(items, n_records)` is the entire input. Verbatim structure: "Below
are {len(items)} shuffled fragments taken from {n_records} different records
and mixed together. You are given no information about which fragment came
from which record." It then requires grouping into exactly `n_records` groups,
ordering within each, "Use every item exactly once", and a JSON array of
`n_records` arrays.

What that means precisely:

| | ours | Memon & Pal 2006 | Paixão 2020 |
|---|---|---|---|
| fragment content | plaintext string, nothing else | image/byte fragment | shred image, 300 dpi |
| **number of sources** | **given** (`n_records` in the prompt) | **given** (k = number of headers found) | **given** (k, the instance size) |
| **supplied anchor** — the attacker is *told* which fragment starts a document | **none** | **k known headers** | **none** (ATSP dummy vertex) |
| **boundary-continuity evidence** — a physical/byte signal for "these two pieces abut" | **none** | pixel / DCT / median-edge across the byte cut | **pixel content across the physical cut** (the CNN's whole input) |
| cut boundaries | known, exact | unknown (cluster boundaries) | physical shred edges |
| partition guaranteed exact | **yes** ("every item exactly once") | yes (no holes assumed) | yes |
| adjacency evidence available | language only | pixel/DCT/MED continuity | pixel continuity across the cut |

`present(fragments, seed)` is what hides the rest: `mask_fragment_ids` replaces
real ids with aliases, then the display order is shuffled. Both draws come from
`_unit_seed(fragments, seed, purpose)`, a SHA-256 over the unit's fragment ids
**and texts** plus the run seed and a purpose string. The docstring records why:
a shared `seed=42` had made the permutation depend only on fragment *count*, so
equal-size cells got byte-identical scrambles and on pool 1 every Game O
prompt's shown order was anti-correlated with truth (τ −0.006 to −0.333).
`shown_order` is stored so positional leakage can be re-checked after the fact.

**The honest reading of this table — [CORRECTED 2026-10-30].** An earlier
version of this document collapsed the first two rows into one "anchor" row and
then concluded that lacking an anchor is the one dimension on which Game J is
harder than *both* predecessors. **That contradicted this very table and is
withdrawn.** The two things are different:

- a **supplied anchor** tells the attacker which fragment starts a document;
- **boundary-continuity evidence** lets the attacker judge which fragments abut.

Scored properly:

- **PUP has both.** Headers give the anchor, pixel/DCT/MED give continuity.
- **Paixão has only the second**, and has it in abundance — the physical cut
  edge *is* the CNN's input. No anchor is needed because the ATSP is solved
  globally.
- **Game J has neither**, and that is the asymmetry to press: we lack an anchor
  that only PUP has, and we lack boundary-continuity evidence that **both** have.

So the correct one-line claim is about continuity, not anchoring: **no
predecessor's adjacency signal exists in Game J, because there is no physical,
visual or byte-level cut to inspect — only language.** On the other three rows
(known source count, exact partition, known cut boundaries) we are at least as
attacker-favourable as both. Do not write "no anchor is the one dimension where
Game J is harder than both predecessors".

## 2. How membership and ordering are represented in the output

**Ours.** A partition **with an order inside each group** — a list of lists of
fragment ids. `harness/joint_metrics.py:1-10` states this is the single scoring
surface and that no attacker-specific branch may enter it, "an attacker-specific
branch in scoring is how two attackers stop being comparable."

- `ordered_pairs(groups)` (`joint_metrics.py:78`) → every `(earlier, later)`
  pair implied by the ordered groups.
- `unordered_pairs(groups)` (`:88`) → the same pairs with direction discarded.

**Paixão.** A bijection `R : S → {1…N}`, one global sequence. No partition
object exists, so there is nothing to compare to `unordered_pairs`.

**Memon & Pal.** k disjoint paths — structurally the closest thing in prior art
to our list-of-lists, and the reason this comparison had to be done.

**This is a real difference in what is measured, not just representation.** A
predicted partition can be scored for grouping *independently* of order; a
global permutation cannot.

## 3. How our statistical baseline scores adjacency and searches for an order

Three files. `adversaries/memon.py` for the boundary signal,
`adversaries/memon_linkage.py` for grouping, `harness/order_from_sim.py` for the
search; `adversaries/memon_joint.py` wires them together.

**Adjacency.** `memon.py:score_pair(text_a, text_b, model, vocab, n, d)` at
line 105. A window of size `n` sits at the end of A and slides `d` steps into B;
at step *i* the context is `(text_a + text_b[:i])[-n:]` and the score accumulates
`log p_char(model, context, text_b[i], vocab)`. `p_char` (`:96`) is add-0.5
smoothed. Frozen at `N = 2`, `D = N = 2` (`:38-39`); the docstring explains that
`d ≤ n` keeps at least one character of A in every context, so the score stays
boundary-sensitive rather than scoring B's interior.

**On the sign.** `score_pair` returns a **log** probability and
`memon_order_guess` (`:132`) **maximises the sum** of those log probabilities.
Maximising Σ log P is equivalent to maximising ∏ P, equivalently to *minimising*
Σ −log P. The code is right. (The error was in `RELATED_WORK_NOTES.md`, now
fixed — see §6.)

**Grouping.** `memon_linkage.py:build_tfidf` (`:62`) builds L2-normalised
TF-IDF vectors by hand (`(1+log tf) · log((N+1)/(df+1))`), cosine = dot product.
`_agglomerative` (`:85`) forms the full distance matrix `1 − sim`, adds
`rng.random(...) * 1e-6` jitter (`:94`) to break exact ties, symmetrises, and
runs scipy average linkage. The jitter is not cosmetic: the module docstring
records that on the identifier corpus an all-zero similarity matrix made every
merge height tie, and `fcluster` then collapsed to **one** cluster, which scores
the trivial F1 "and looks like signal where there is none."

`memon_joint.py:group_known_n` (`:90`) is the known-N variant: it cuts with
`cut_tree(Z, n_clusters=[n_groups])` (`:123`) to get **exactly** N, because
`fcluster(criterion="maxclust")` returns *at most* N; both are computed and
`cut_tree_disagreed` (`:139`) is recorded.

**Direction and search.** `memon_joint._weight(s_ab, s_ba)` (`:147`) maps the
two directional scores to an antisymmetric bounded weight,
`W = 2·sigmoid(s_ab − s_ba) − 1 = tanh((s_ab − s_ba)/2)`, no free parameter.
`order_from_sim.objective(order, edges)` (`:100`) sums `+w` when the order
agrees with an edge and `−w` when it does not. `_local_search` (`:149`) is hill
climbing on that exact objective — adjacent swaps, then insertions, ≤64 passes.
`order_cluster` (`:239`) runs **three deterministic starts** per connected
component and keeps the best; the third start's seed is a SHA-256 over the
sorted component ids (`:293`) so it is stable across processes (D13).

**Side by side:**

| | ours | Shanmugasundaram & Memon 2003 | Memon & Pal 2006 | Paixão 2020 |
|---|---|---|---|---|
| adjacency signal | add-0.5 smoothed char-bigram boundary log-prob | PPM/PPMC, orders 0..k, escape-blended | pixel match / DCT / MED | self-supervised CNN on the shred pair |
| directionality | antisymmetric `tanh((s_ab−s_ba)/2)` | directional C(i,j) | directional edge | directional (ATSP) |
| grouping | TF-IDF + average linkage, cut to exactly N | **none** (single document) | emergent from k parallel paths | **none** (implicit in the permutation) |
| search | hill climbing, 3 seeded starts | max-weight Hamiltonian path via α-β tree pruning from a known first fragment | greedy parallel Dijkstra, unique paths | exact ATSP via Concorde |
| optimality | local | near-optimal, top-β returned | greedy | **exact** |

## 4. How our scores are computed

All in `harness/joint_metrics.py`.

- `score_joint` (`:99`) — precision `tp/|guessed|`, recall `tp/|truth|`, F1 the
  harmonic mean, over **ordered** pairs.
- `decompose` (`:161`) — the one that matters. With `denom = |g_un| + |t_un|`:
  `f1_joint = 2C/denom`, `f1_linkage = 2K/denom`, where `C` = pairs
  co-clustered **and** correctly directed and `K` = pairs co-clustered, direction
  ignored. Then `q = C/K`. Hence **F1_J = F1_L · q** exactly, by construction,
  not as an empirical approximation — the two F1s share a denominator.
- `q` is **`None` when `K == 0`**, never 0 (`:191`, and the docstring at
  `:172-175`): coercing it would turn "ordering could not be evaluated because
  linkage failed completely" into "ordering was completely wrong". Aggregation
  is micro, `ΣC/ΣK`, via `micro_q` (`:208`), which also returns the undefined
  count.
- `analytic_baseline` (`:121`) — closed form for one bucket: `T = Σ C(m_d,2)`,
  `P = C(M,2)`, `E[F1_L] = 2T/(P+T)`, `E[F1_J] = T/(P+T)`, so joint is exactly
  half of linkage because a random direction is right half the time. The
  docstring (`:48-52`) insists this is a **baseline, not a floor** — all
  singletons score 0, which is lower.
- `advantage` (`:146`) — `A = (F1 − b)/(1 − b)`, and the docstring warns it
  **must** be computed per pool then averaged, since `b` moves with each pool's
  size distribution.
- `reconstruction_detail` (`:240`) — `longest_run`, `exact_positions`,
  `mean_shift`, plus τ. The docstring carries the measurement that motivates it:
  a document at τ +0.430 had **zero** of 27 fragments correctly placed, mean
  displacement 5, longest intact run 5; another at τ +0.886 had 13 of 21 exact.

**Comparison of what the metrics can express:**

| | ours | Paixão 2020 | S&M 2003 |
|---|---|---|---|
| separates grouping from ordering | **yes**, `F1_L` and `q` | no | n/a |
| credits the document seam | no — a cross-document pair is simply wrong | **yes**, counted as a match | n/a |
| calibrated against a trivial strategy | yes, `analytic_baseline` + `advantage` | no | no |
| permutation null | `visible_metrics.oracle_size_null` — **single-token edge-case experiment only**, not the headline results (§4A) | no | no |
| contiguous-text readability | `longest_run` — **Game O only**, not computed for Game J (§4B) | no (adjacent-pair rate only) | no (adjacent-pair rate only) |
| what a "pair" is | **full precedence** (every earlier/later pair in a group) | immediate adjacency | immediate adjacency |

**`F1_L` and `q` have no counterpart in either predecessor's metric.** That is
the sharpest defensible methodological difference, and it is a difference in
*measurement*, which is a weaker kind of novelty than a new problem — say it
that way.

## 4A. Which benchmark applies to which experiment — [ADDED on review]

An earlier version of §7 said the study reports "calibrated analytic baselines
and permutation nulls" as though every experiment carried both. **It does not.**
Read off `results/final_analysis/MASTER_RESULTS.csv` (2,648 rows, 75 columns)
and from which modules import which scorer:

| experiment | unit count | primary metric | trivial-strategy reference | chance for a **valid N-group** answer | permutation null |
|---|---|---|---|---|---|
| **Game J, prose** (headline + grid) | 262 units × 4 attackers | `F1_J`, `F1_L`, `q` (id-level) | `analytic_baseline` → `b_J`, `A_J` | **NONE** | **none** |
| **Game J, identifier** | 20 units × 6 attackers | same | `b_J`, `A_J` | **Random** (random partition into known N, D11) | none; Schema-order 0.20 with the frozen ±0.10 CI rule |
| **Game O, prose** | 370 units × 4 attackers | τ, `pairs_correct` | — | **Random** permutation | none |
| **Single-token edge case (D16)** | 20 pools × conditions | `V_J`, `V_L` (visible) | — | — | **`oracle_size_null`** (primary), `predicted_structure_null` (robustness) |

Two consequences, both of which must be stated rather than smoothed over:

**(a) `analytic_baseline` is not the chance level of a valid Game J answer.**
It is the closed-form expected score of putting **every fragment in one group**
— and one group is not a legal answer to a prompt that demands exactly
`n_records` arrays. `joint_metrics.py:48-52` is already careful about this
("BASELINE, NOT FLOOR"; all singletons score 0, which is lower), but "baseline"
in the paper must be read as *trivial-strategy reference*, never as chance.
Measured on the 46 headline pools: `b_J` = **0.1493**, and the Analytic
one-bucket attacker scores `F1_J` = 0.1493 with `A_J` = 0.0000 by construction.
(`b_J` = 0.1303 on the grid; **never pool the two** — see §4B.)

**For prose Game J there is no random-valid-partition baseline at all.** The
attacker column contains only Analytic one-bucket, Embedding, Memon-inspired
and One-shot Sonnet; **Random appears for identifier J and for Game O, never
for prose J.** That is a genuine hole in the calibration story, it is free to
fill (a seeded random partition into exactly 7 groups with random intra-group
order, scored by the same `decompose`), and a reviewer comparing
`F1_L` = 0.8817 against a one-bucket reference will ask for it.

**(b) The permutation nulls belong to one experiment.** `visible_metrics` is
imported only by `analysis/single_token_edge_analysis.py`,
`runs/final_run_single_token_edge.py`, `runs/bench_visible_null.py` and its own
test; `MASTER_RESULTS.csv` has no `V_J`/`V_L` columns. The nulls are namespaced
`single-token-edge-v1` for exactly this reason. **Do not write "permutation
nulls" in a sentence that covers the headline results.**

## 4B. What F1_J does and does not mean — [ADDED on review]

`ordered_pairs` (`joint_metrics.py:78`) emits **every** `(earlier, later)` pair
within a group — the full precedence relation, not immediate adjacency.
Paixão's equation (2) counts **only immediate adjacency**. These are different
measurements, and the gap between them is large.

Our own Game O data measures it. Under perfect membership `F1_J = (1+τ)/2`,
which is exactly the `pairs_correct` column, so Game O is directly
interpretable on the F1_J scale. One-shot Sonnet, banded across **all 370 prose
Game O units** (`headline` + `primary` together — pooled *deliberately* here,
because this is a diagnostic of the metric's behaviour across its range, not a
reported result; any number quoted in the paper must come from one designation):

| `pairs_correct` band | n | mean `exact_fraction` | mean `run_fraction` |
|---|---|---|---|
| 0.5 – 0.7 | 13 | 0.070 | 0.182 |
| 0.7 – 0.8 | 25 | 0.095 | 0.152 |
| 0.8 – 0.9 | 87 | **0.227** | **0.208** |
| ≥ 0.9 | 245 | 0.593 | 0.475 |

So a pairwise precedence rate of 0.8–0.9 corresponds to only ~23% of fragments
in their true position and a longest intact run of ~21% of the document.

**Authoritative Game O headline figures** (the `semantic__sentence (full
length)` cell, 100 documents per attacker): One-shot Sonnet τ **0.7690**,
`pairs_correct` **0.8845**, `exact_fraction` 0.3249, `run_fraction` 0.2373,
`longest_run` 6.31; Jaccard-Greedy τ −0.0054 / longest run 1.85; Jaccard-MST
τ 0.0121 / 1.75; Random τ 0.0000 exactly. **[CORRECTED]** An earlier version
quoted τ 0.8239 / `pairs_correct` 0.9119 / `longest_run` 11.58 — the pooled
370-unit means, same designation-pooling error as above.

Note the headline/grid relationship **inverts between games**: Game J headline
F1_J 0.7225 is *above* the grid's 0.6763, while Game O headline τ 0.7690 is
*below* the grid's 0.8442 (the headline Game O cell is full-length reports, so
more fragments per document and harder ordering). Pooling does not merely blur
these — it can reverse the sign of a comparison.

**The interpretation rule for the paper:**

> F1_J = 0.723 does **not** mean 72% of the text was reconstructed, nor that 72%
> of adjacent fragments were correctly rejoined. It is the F1 over correctly
> recovered, directed, within-document fragment *pairs*. Contiguous readable
> text is a separate, and much smaller, quantity.

**Authoritative headline Game J figures** — the 46-pool `headline` designation,
from `results/final_analysis/TABLES/table_B_headline_J.csv`:

| attacker | F1_J | F1_L | q_micro | A_J |
|---|---|---|---|---|
| One-shot Sonnet | **0.7225** | **0.8817** | **0.7918** | 0.6731 |
| Embedding (post-hoc exploratory) | 0.1816 | 0.3635 | 0.4996 | 0.0386 |
| Memon-inspired | 0.1685 | 0.3390 | 0.4934 | 0.0229 |
| Analytic one-bucket | 0.1493 | 0.2987 | — (K = 0) | 0.0000 |

`b_J` = 0.1493 throughout. Report `q` as **q_micro = ΣC/ΣK** (the frozen
definition in `joint_metrics.micro_q`), rounded to **0.792**.

**[CORRECTED]** An earlier version of this section reported F1_J 0.6844,
F1_L 0.8136, q 0.8392, A_J 0.6358, Embedding 0.1418, Memon-inspired 0.1385,
b_J 0.1336. Those were means **pooled across the `headline` and `primary`
designations** (262 units), which is not a quantity the paper reports. Two
distinct mistakes: pooling designations, and reporting `q_mean` where the frozen
convention is `q_micro`.

**A gap this exposes, which I did not expect.** The critique assumed
`longest_run` and `exact_positions` would backstop this interpretation. **They
are not computed for Game J.** In `MASTER_RESULTS.csv`, `tau`,
`pairs_correct`, `exact_fraction`, `mean_abs_disp`, `longest_run` and
`run_fraction` are populated for **0 of 1,168 Game J rows**, and for Game O at
1,480/1,480 (`longest_run`/`run_fraction` 1,110/1,480 — the 370 missing are
exactly the Random rows; cause not established, flagged in §8). `exact_order`
is populated nowhere.

That is explicable — `reconstruction_detail` (`:240`) requires
`sorted(guess) == sorted(truth)`, i.e. one document's fragment list, which is a
Game O object — but it means **the readability claim currently has no
measurement in the game the paper leads with.** Fixing it is free and local:
run `reconstruction_detail` per predicted group against its matched true
document. Until that exists, the paper should not make contiguous-text claims
about Game J, and §7's "contiguous-text readability: yes" row applies to Game O
only.

### Scope of the F1_J = F1_L × q identity

Exact and structural **for the id-level metrics**: `decompose` (`:161`) computes
`f1_joint = 2C/denom` and `f1_linkage = 2K/denom` with the *same*
`denom = |g_un| + |t_un|`, so the ratio `q = C/K` factors them exactly.

**Naming discipline — this is where I went wrong, and the pipeline did not.**
`table_B_headline_J.csv` correctly reports **two** labelled columns: `q_mean`
(the mean of per-pool q over pools where it is defined) = 0.8206, and
`q_micro` (ΣC/ΣK) = 0.7918 [0.7723, 0.8188]. Both are legitimate and the table's
own footnote distinguishes them. The frozen reporting convention, and the packet,
use **`q_micro`**. So 0.8206 must never appear labelled plain `q` — but it must
**not** be deleted from the generated artifacts either, where it is correctly
named `q_mean`. Stripping it would corrupt the frozen analysis. This was a
labelling error in prose, not a computation error in the pipeline.

**It does not transfer to the visible-text metrics.** There, `q_V := V_J/V_L` is
a definition, and the module docstring calls it "a diagnostic only". More
importantly, `score_sequences` runs `linear_sum_assignment` **twice** — `(r,c)`
on the multiset-overlap matrix for V_L and `(r2,c2)` on the LCS matrix for V_J
(`visible_metrics.py:132-133`) — so the two values may come from **different**
predicted-group→document pairings. `V_J = V_L × q_V` is therefore a tautology
about two separately optimised quantities, not a decomposition of one pairing.
Never present `q_V` as the visible-metric analogue of `q`.

## 5. Duplicate fragment strings in the scorer

You asked for this specifically, and it is the most load-bearing thing in the
file. **`harness/visible_metrics.py`.**

The module docstring states the problem: the ordinary Game J scorer tracks
hidden fragment ids, and "at single-token granularity many fragments share
visible text ('the', 'the', …), and swapping the hidden ids of two identical
visible tokens is invisible to any attacker yet penalised by an id-level
scorer."

Two distinct duplicate problems, handled in two different places:

**(a) Duplicate *ids* in the attacker's answer** — `PoolScorer._clean` (`:104`).
Unknown ids are dropped; an id repeated anywhere counts **once**, at its first
occurrence; fragments the attacker placed nowhere become singleton groups,
matching the Game J scorer's reading of a dropped fragment.

**(b) Duplicate *visible text* across distinct fragments** — the metric design
itself. `score_sequences` (`:119`):
- **V_L** is a **multiset intersection**:
  `lm[i] = np.minimum(c[None,:], self.true_counts).sum(1)` (`:128`), where `c`
  is the predicted group's token count vector. So a predicted group is credited
  for having the right *number of copies* of each token, capped at the true
  count. **Multiplicity is scored, not discarded.**
- **V_J** replaces multiset overlap with **token-level LCS**, computed
  bit-parallel in `lcs_len` (`:58`, Crochemore/Hyyrö), with `lcs_dp` (`:75`) as
  the reference implementation for tests.
- Both are maximised over **one-to-one predicted-group → true-document
  assignments** by `linear_sum_assignment(..., maximize=True)` (`:132-133`), run
  separately for the two matrices. The docstring notes the reported values are
  the optimal *values*, so tie-breaking between equally good assignments cannot
  change them.
- `V_J ≤ V_L` always, and `single_token_edge_analysis.py:171` asserts it at
  runtime (`assert v["V_J"] <= v["V_L"] + 1e-12`).

Nulls, since `b_J` does not apply to visible metrics: `oracle_size_null`
(`:169`) permutes all fragment labels into the **true** per-document counts
(primary); `predicted_structure_null` (`:174`) permutes into the attacker's own
predicted sizes (robustness). Both seeded by `null_rng` (`:151`), SHA-256 over
`single-token-edge-v1|pool|condition|kind`.

**Why this matters for the one-word experiment, concretely.** 44.4% of one-word
fragments share surface text with another fragment, against 5.4% at two words
and under 1% at three and four. At that duplication rate an id-level score is
measuring something an attacker cannot even see, which is why D16 froze the
visible scorer as primary. It is also why the id-level and visible numbers will
nearly agree at 3 and 4 words — worth saying when the D18 arms are reported, so
nobody reads the convergence as a bug.

**And it corrects your point 3 further than you put it.** Our fragments do not
merely "contain multiplicity information" in the input — **our primary scorer is
built on multiset counts.** The old "no counts" line in the notes contradicted
our own code, not just the threat model.

## 6. The five corrections, applied

All now fixed in `docs/RELATED_WORK_NOTES.md`:

1. **Novelty of the joint problem — overstated, retracted.** §0 and the §6 test
   answer now name Memon & Pal (2006) and Paixão et al. (2020) as mixed-source
   predecessors, and the 2003 Collating quotation is demoted to historical
   context about that paper only.
2. **"Lower bound on a classical statistical attacker" — withdrawn.** A simpler
   model is not a weaker one on a given corpus. Replaced with: one tested
   statistical baseline, neither a faithful implementation nor an estimate of
   the strongest attainable classical performance. **Not** added to
   `adversaries.md`.
3. **"No counts" — wrong, replaced.** See §5.
4. **Known-first-fragment — softened.** The input is genuinely absent, so the
   method cannot run as specified; but enumerating candidate starts (at k× cost)
   or re-anchoring is a legitimate adaptation. It makes faithful replication
   harder, not a comparable classical attacker impossible. The word "airtight"
   is gone. *This is now more interesting, not less:* PUP also starts from
   headers, so "no anchor" is the one input dimension on which Game J is
   genuinely harder than both predecessors.
5. **Product/log sign — fixed.** Maximising ∏ C is equivalent to **minimising**
   Σ −log C. Our code was already correct (§3); only the prose was wrong, and
   the 2003 paper's own equation (2) reads "maximizing" over a `−log` term while
   its Figure 1 sums raw probabilities along the path. Cite their
   Hamiltonian-path reduction, not the transformation, and do not reproduce
   the sign.

Also applied: the Lermen ablation is now described as **consistent with** our
embedding-vs-Sonnet gap, not as support for it — different pipelines, different
task, not a controlled replication.

## 7. The novelty claim that survives

Not the invention of mixed-source reconstruction. The defensible claim, in one
sentence:

> An empirical evaluation of mixed-source **plaintext** reconstruction by modern
> semantic attackers, in which fragments carry none of the visual, physical or
> byte-level continuity that prior reassembly methods rely on, with the joint
> score factored into separate linkage and conditional-ordering components
> against a closed-form trivial-strategy reference, and measured across attacker
> families, fragmentation strategies, granularities and data types.

**[CORRECTED]** The earlier wording said "calibrated analytic baselines and
permutation nulls". Per §4A the permutation nulls exist only in the
single-token edge-case experiment, and the analytic reference is a
trivial-strategy benchmark rather than chance for a valid N-group answer, so
that clause overstated the calibration across experiments. It is also no longer
safe to write "no header anchor" as a distinction from both predecessors —
Paixão needs no anchor either (§1).

Each clause is doing work, and each is checkable:

- **"none of the continuity prior methods rely on"** — this is the clause doing
  the real work. PUP matches pixels/DCT/median-edge across the byte cut;
  Paixão's CNN matches pixel content across the physical cut. Both signals are
  unavailable by construction in Game J: `prompt_J` ships a plaintext string
  and nothing else, so `score_pair` has only language. Separately, PUP is also
  anchored at k known headers while Paixão and Game J are not — keep the two
  axes apart (§1).
- **"modern semantic attackers"** — the LLM and embedding attackers are new
  relative to 2006 and 2020, which is a real but *incremental* claim, and
  ShredBench already establishes LLM reconstruction in the visual domain.
- **"factored into linkage and conditional ordering"** — `decompose`,
  `F1_J = F1_L · q`, with no counterpart in either predecessor's metric (§4).
- **"a closed-form trivial-strategy reference"** — `analytic_baseline` and
  `advantage`, on every Game J unit. Neither predecessor reports any baseline
  at all, which is the real point. But see §4A: it is not chance for a valid
  N-group answer, prose Game J has no random-partition baseline, and the
  permutation nulls cover the single-token experiment only.

**What we must now concede explicitly, in the paper:**

- Mixed-source reconstruction has 2006 and 2020 precedents; we are not first.
- **Both predecessors vary the number of mixed sources and we do not.** Paixão
  sweeps k = 1…100 and finds accuracy does not degrade; PUP is defined for
  arbitrary k. Our N = 7 is fixed. This is now the *third* independent reason
  to concede the fixed-N limitation — Lermen's §6.4 was the first, Paixão's
  k-sweep the second, PUP's generality the third. It has stopped being a
  footnote and belongs in Limitations as a named gap.
- Paixão achieves >90% accuracy on 100 mixed documents in the visual domain. If
  our attackers do poorly on 7 in the plaintext domain, the contrast is a
  *finding about available signal*, and it must be framed that way rather than
  as a capability result — the tasks are not commensurable, and their accuracy
  metric credits the document seam while ours does not.

## 8. Open items

- **Read Memon & Pal (2006) in full** before citing it for anything specific.
  Everything in §0 about PUP is secondary. A paywalled claim should not anchor a
  novelty concession in a submitted paper.
- Check whether the CVPR 2020 companion's 505-shred / 20-document instance is
  a *single* mixed instance (as the abstract reads) or 20 separate single-page
  instances — that changes how directly it predates Game J. The Pattern
  Recognition paper's k-sweep is unambiguous, so the concession stands either
  way.
- **Add a random-valid-partition baseline to prose Game J** (§4A). Free, local,
  and it closes the only calibration hole a reviewer is certain to find: a
  seeded random partition into exactly 7 groups with random intra-group order,
  scored through the same `decompose`. Prose Game J currently has no such row
  while identifier J and Game O both do.
- **Compute `reconstruction_detail` for Game J** (§4B). Also free. Per
  predicted group against its matched true document. Until it exists, no
  contiguous-text or readability claim may be made about Game J, which is the
  game the paper leads with.
- **Establish why the 370 Game O Random rows have no `longest_run`.** Every
  other Game O attacker has 370/370. `reconstruction_detail` returns `None`
  when `sorted(guess) != sorted(truth)`, and the CSV has an `expectation`
  column, so the likely explanation is that Random's O score is analytic rather
  than a sampled permutation — **but I did not verify this, and it should not go
  in the paper as an explanation until someone does.**
- An **N-sweep** is worth considering but should not be done merely because
  Paixão ran one: their finding that accuracy holds up as image shreds are
  mixed says nothing about what happens with more plaintext sources. If it is
  run, **N cannot be varied in isolation** — changing N at fixed fragments per
  document changes the pool's total fragment count and total text, and changing
  N at fixed pool size changes fragments per document. Either confound alone
  could produce the whole effect. One of the two must be held constant by
  design and the choice stated. **Not costed, not proposed — flagged only.**
