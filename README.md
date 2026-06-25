# Reconstruction-Resistance of Fragmented Documents Against LLM Adversaries

## What this is

An empirical study of **fragmentation as a privacy mechanism**: when a document is cut into pieces and the order is stripped, can a modern LLM put it back together — and does that depend on what kind of content it is?

This is **not** a paper about any one fragmentation system. A deployed system (SCRMBL) is the motivating use case, not the subject — every cryptographic primitive in it is established prior art, so a novelty claim there doesn't hold up. The open question is empirical, general, and doesn't require that system to exist or work: it's about LLMs and content type.

## Research question

> Can a modern LLM-class adversary reassemble order-deprived document fragments, and how does success depend on (a) cut strategy, (b) content type, and (c) fragment granularity?

**The novel axis:** in a *closed-world* setting — the adversary gets only the stripped fragments and public models, with **no auxiliary context** to corroborate against — does non-linguistic content (atomic identifiers — SSNs, account numbers) resist reassembly where linguistically coherent content (prose) does not? This is deliberately the complement of recent open-world de-anonymization work (e.g. InferLink), where the adversary's power comes from corroborating cues against the web; we forbid that and ask what intrinsic linkage signal survives order-deprivation alone.

## Pre-registered hypothesis

Committed *before* running any data:

- **Ordering recovery** (prose) — LLMs exploit linguistic/coherence signal → expected to succeed well above baseline.
- **Association recovery** (atomic identifiers) — no linguistic signal links a name to a number → expected to stay near random, regardless of LLM capability.
- **Mixed records** — resistance tracks identifier density, falling between the two.

A narrowed result (e.g., only pure identifiers resist) still confirms the thesis and is reported as a real finding, not a failure.

## How it's tested

No system build required. Fragments are fabricated directly: synthetic documents → cut → shuffle → handed to an LLM → scored against a baseline (random, and classical statistical reassembly). Three crossed variables: cut strategy × content type × granularity.

## Outline

1. **Introduction** — HNDL motivation, the gap between old statistical-reassembly work and modern LLM capability.
2. **Related Work** — three-way positioning: (a) classical statistical reassembly (Memon lineage), (b) LLM sentence-ordering, and (c) recent LLM de-anonymization / linkage (InferLink, tournament-style attribution, DP-reconstruction). The spine is the closed-world vs. open-world line: prior linkage work gives the adversary auxiliary context; we deny it, isolating intrinsic reconstruction signal.
3. **Threat Model & Reassembly Game** — formal adversary + success definitions. *(See `paper_section3_reassembly_game.md` — drafted, this is the rigor spine.)*
4. **System as Testbed** — brief description of the motivating architecture, as the instrument, not the contribution.
5. **Experimental Design** — cut strategy × content type × granularity; metrics (Kendall's τ, perfect-match, re-identification precision/recall).
6. **Results** — the resistance curve by content type.
7. **Discussion** — implications for fragmentation as a privacy mechanism.
8. **Limitations** — empirical, not a proof; LLM capability shifts over time; closed-world scope — a web-enabled agentic adversary (InferLink-style) is strictly stronger, and our resistance result holds specifically for the no-auxiliary-context setting.
9. **Conclusion**

## Ownership

- **Threat model / reassembly game (§3)** — lead, with advisor (cryptographer) review before anything goes public.
- **Cutter, adversary harness, baseline, results** — build/attack track.
- **Literature positioning** — lit-review track.

## Status

Draft. Threat model section needs a cryptographer's review before any formal security-definition claims are posted to arXiv/ePrint.
