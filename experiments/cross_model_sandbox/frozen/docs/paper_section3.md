# Threat Model, Reassembly Game, and Reconstruction-Resistance

*Draft Section 3 of the reconstruction-resistance paper. This is the rigor spine — the formal frame that turns "we shuffled text and tried an LLM" into a defined security evaluation. Sections marked **[ADVISOR]** are where a cryptographer (Syta) should refine before submission.*

---

## 3.1 Setting and intuition

We study **fragmentation as a privacy mechanism**: a document is cut into pieces and their order is withheld. The security question is not whether the pieces are *encrypted* (a separate, solved layer) but whether, **given the plaintext pieces with their order removed**, an adversary can reassemble the original document or recover the sensitive associations inside it.

We deliberately give the adversary the *plaintext* fragments. This models the worst case — "even if every other layer fails and the pieces are laid bare, what does order-deprivation alone buy?" — and isolates the property we are actually measuring. A scheme that resists reassembly on plaintext fragments resists it a fortiori when the fragments are also encrypted.

Two recovery goals, corresponding to two content regimes:

- **Ordering recovery** — reconstruct the sequence (relevant to prose, narrative records).
- **Association recovery** — re-link atoms that belong together, e.g. a name to its SSN (relevant to structured, identifier-heavy records). Order is irrelevant here; *linkage* is the sensitive thing.

Our central hypothesis is that these two regimes behave **oppositely**, because ordering recovery exploits *linguistic* signal (which prose has and identifiers lack), while association recovery requires *database* signal that fragmentation removes and no language model can supply.

This is a general claim about fragmentation as a privacy mechanism — it is not a claim about, or limited to, any one fragmentation system. We instantiate and test it against synthetic, fabricated fragments (§3.7); a deployed system is, at most, one motivating example of where the question matters in practice, not the object under study.

---

## 3.2 Notation

- A **document** `D = (u_1, ..., u_m)` is an ordered sequence of *units* (sentences, or finer atoms).
- A **fragmentation scheme** `Frag` maps `D` to an ordered fragment list `(F_1, ..., F_n)` under a chosen **cut strategy** `σ ∈ {random, semantic, entity-aware}` and **granularity** `g`. Each `F_i` is a contiguous span of units.
- The **true order** is the identity permutation on `(F_1, ..., F_n)`; reconstruction must recover it (up to the equivalence in §3.6).
- An adversary receives the **multiset** `S = {F_1, ..., F_n}` (order stripped) together with **public knowledge** `pub` (defined below), and outputs a guess.
- For association recovery, each document carries a ground-truth **linkage** `L` (e.g., the set of (name, SSN) pairs that co-refer); the adversary outputs a guessed linkage `L̂`.

---

## 3.3 Adversary model

The adversary `A` is given:

- **The full fragment multiset** `S` for a target document (and, in the cross-document variant, the pooled multiset across many documents — the "stolen database" case).
- **`pub`:** the cut strategy `σ` and granularity `g` in use; all *public* models (the semantic-boundary model is non-secret and is given to the adversary); the general content distribution (the adversary may be trained or prompted on same-distribution data); and unlimited query access to one or more LLMs.

The adversary is **denied** exactly one thing: any secret that determines order or linkage that was never placed in the fragments. (A concrete fragmentation system might realize this secret as a hardware-rooted ordering factor; our study does not depend on any particular realization.) In this *plaintext* study that secret is simply *absent from `S` by construction* (we stripped order), which is what we are measuring the value of.

The adversary is also **denied auxiliary context**: no external corpus, web access, named-record set, or other out-of-band source to corroborate against. This is deliberate and load-bearing. Recent de-anonymization work (e.g. inference-driven linkage) derives the adversary's power precisely from corroborating weak cues against public information; we exclude that channel to isolate the *intrinsic* reconstruction signal carried by the fragments themselves. Our setting is therefore a closed-world lower bound — strictly weaker than a web-enabled agentic adversary, and correspondingly a conservative measure of what order-deprivation alone withholds.

We consider the adversary **capability-maximal in practice** (best available LLMs, repeated queries, fine-tuning). This is conservative: if reconstruction fails *here*, it fails against weaker real attackers too.

**[ADVISOR]** *A formal PPT/asymptotic treatment would quantify over all efficient adversaries; we instead estimate resistance against a concrete, strong adversary set and are explicit that ours is an empirical bound, not a proof. This is standard for measurement-security papers but should be framed precisely.*

---

## 3.4 The Reassembly Game

We define two games. Both are **relative** to a baseline, because raw reconstruction scores are meaningless without knowing what trivial strategies achieve.

### Game O — Ordering Recovery

```
ReassembleO(A, Frag, σ, g, D):
  1. (F_1,...,F_n) ← Frag(D; σ, g)          # cut
  2. S ← shuffle({F_1,...,F_n})              # strip order
  3. π̂ ← A(S, pub)                           # adversary guesses an ordering
  4. return quality_O(π̂, true_order)         # e.g. Kendall's τ, perfect-match
```

### Game L — Association Recovery

```
ReassembleL(A, Frag, σ, g, D):
  1. (F_1,...,F_n) ← Frag(D; σ, g)
  2. S ← shuffle({F_1,...,F_n})
  3. L̂ ← A(S, pub)                           # adversary guesses atom linkages
  4. return quality_L(L̂, L)                  # e.g. re-identification precision/recall
```

### Baselines (mandatory)

For each game we define a **baseline adversary** `B`:
- **Random** `B_rand`: random permutation / random linkage.
- **Statistical**: the classical floors (Jaccard-Greedy and Jaccard-MST, game O only) and the Memon-inspired joint attacker (TF-IDF cosine + average-linkage grouping to exactly N; ordering by a directional character-bigram boundary likelihood, an idea inspired by Shanmugasundaram & Memon's context models, without their PPM model or Hamiltonian-path search). None is a faithful Memon implementation. Definitions: `docs/adversaries.md`.
  *Corrected 2026-09-13:* this line previously called `B_stat` "the classical content-based reassembly approach … after Shanmugasundaram & Memon 2003 — the pre-LLM state of the art". In the code `B_stat` is only the TF-IDF grouper, and "state of the art" was an overclaim.

The reported quantity is the **adversary advantage**:

```
Adv_O(A) = E_D[ quality_O(A) − quality_O(B_stat) ]
Adv_L(A) = E_D[ quality_L(A) − quality_L(B_stat) ]
```

A finding is a *gap* between the LLM adversary and the baseline, per (σ, content-type, g) cell. "The LLM reorders prose far above the statistical baseline; for atomic-identifier records it does not beat random" is the shape of the result we expect.

---

## 3.5 Reconstruction-resistance definition

Adapting the reconstruction-robustness framing of Balle, Cherubin & Hayes (IEEE S&P 2022):

> A fragmentation scheme `Frag` is **(η, γ)-reconstruction-resistant** for a content class `C`, cut strategy `σ`, and granularity `g`, against adversary class `𝒜`, if for every `A ∈ 𝒜` and every document `D` drawn from `C`:
>
> `Pr[ quality(A on Frag(D; σ, g)) ≥ η ] ≤ γ`.

In words: no adversary in the class achieves reconstruction quality `η` or better, except with probability at most `γ`. Small `γ` at a *meaningful* `η` (e.g. "more than half the document correctly ordered," or "any correct name↔SSN link") is the property we want.

The **empirical contribution** is to *estimate* the achievable `(η, γ)` frontier for each `(σ, C, g)` cell — i.e., to map where fragmentation delivers strong resistance (atomic identifiers: high `η` reachable only at vanishing `γ`) and where it collapses (prose: high `η` reachable at `γ ≈ 1`).

**[ADVISOR]** *Two things to pin down with a cryptographer: (1) the right `quality` threshold `η` that is genuinely "security-relevant" rather than arbitrary — for Game L this is cleanest (any correct sensitive linkage is a breach); for Game O it needs a defensible cutoff. (2) Whether to state this as a distributional claim over `C` (our intent) or worst-case over `D`. We choose distributional and report the full distribution, not a single point.*

---

## 3.6 Equivalence and scoring subtleties

- **Order equivalence:** some reorderings are semantically identical (e.g., independent list items). Score with rank-correlation (Kendall's τ) that tolerates local swaps, and report perfect-match separately as the strict metric.
- **Partial credit:** Game O uses τ for graded recovery; Game L uses precision/recall over linkages, because a single correct link can be a full privacy breach even if the rest is wrong. **Game L's "one correct link = breach" metric is the security-relevant headline for structured data.** Note this measures *internal* linkage — re-pairing atoms that co-occur within the stripped fragment set (e.g. name↔SSN) — not identity *resolution* against an external auxiliary source (the InferLink-style LSR/CLC sense). The word "linkage" appears in both literatures with different referents; ours is the closed-world, intrinsic one.
- **Cross-document pooling:** in the database-theft variant, fragments from many documents are pooled. An added recovery step — *clustering fragments by source document* — precedes ordering/linkage. This is strictly harder for the adversary and strictly more realistic; we report both the per-document (membership known) and pooled (must also cluster) settings.

---

## 3.7 What the experiment instantiates

| Game element | Experimental realization |
|---|---|
| `Frag`, `σ` | Python cutter: random / semantic-boundary / entity-aware |
| `g` (granularity) | sentence / sub-sentence / paragraph |
| Content class `C` | synthetic identifier records · prose (clinical notes, memos) · mixed synthetic EHR |
| Adversary `A` | multiple LLMs (varied capability) via greedy-adjacency and direct-reorder prompting; optional fine-tuned reorderer |
| Baseline `B` | random; Memon-style statistical adjacency |
| `quality_O` | Kendall's τ, perfect-match ratio |
| `quality_L` | re-identification precision/recall (any correct sensitive link) |
| Output | (η, γ) frontier per (σ, C, g) cell; advantage over baseline |

All of the above is run on fabricated fragments — documents cut and shuffled directly by the harness. No fragmentation *system*, hardware, or deployed architecture is required to populate this table; a real system is, at most, the motivating example for why the question matters, not a dependency of the experiment.

The content classes are **wholly synthetic** (e.g. Faker-generated name/SSN/account values), and this is what *guarantees* the closed-world property rather than merely assuming it. Because no synthetic identifier corresponds to a real person, there is no external record, breach corpus, or public source anywhere that an adversary could corroborate against — the name↔identifier pairing exists *only* in our held-out answer key. Real-world identifier re-identification has historically depended exactly on such auxiliary/breach data, and even on partial predictability of SSNs from public birth records (Acquisti & Gross, PNAS 2009); synthetic generation removes that channel by construction. Any correct linkage the adversary produces is therefore provably from intrinsic signal in the fragments, not from outside knowledge — which is precisely the quantity the closed-world setting is designed to measure.

**Pre-registered hypothesis (commit before running):** Adv_O is large and positive for prose and grows with LLM capability; Adv_L is ≈ 0 for atomic-identifier content regardless of LLM capability; mixed records' resistance tracks their atomic-identifier density. A *narrowed* result (e.g., "only pure-identifier content resists") still confirms the content-dependence thesis and is reported as such.

---

## 3.8 Honest scope and limitations

- This is an **empirical** resistance estimate against a concrete strong adversary, not a cryptographic proof against all efficient adversaries. We say so plainly.
- LLM capability **improves over time**; we mitigate by testing a capability range and reporting the *trend*, so the qualitative finding (content-dependence) is more durable than any single model's number.
- The plaintext-fragment assumption is **deliberately worst-case** and decouples this study from any encryption or hardware layer entirely — which is exactly why the experiment can be run **without building or assuming any particular fragmentation system**.
- Resistance for prose is *expected to be weak* (consistent with strong LLM sentence-ordering results); the contribution is the **characterization and the identifier/prose contrast**, not a claim that fragmentation hides prose.

---

## Notes for the team

- **This decouples the paper from any system build.** Everything above runs as a Python harness + LLM API calls + synthetic data. No HSM, no fragmentation-system prototype of any kind required for the paper's critical path. A full system (e.g., a deployed architecture motivating the question) is, at most, optional parallel work, not a dependency.
- **Who owns what:** the game/threat model (this document) is the lead's to own and to bring to the advisor. The cutter, the adversary harness, and the baseline are the build/attack work (cybersec team). The literature positioning (Memon lineage + LLM sentence-ordering) is the lit-review track.
- **The single most credible thing to walk into the advisor meeting holding** is this section plus the pre-registered hypothesis — it directly answers "no threat model, no security definitions."
