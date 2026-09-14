# POST-HOC EXPLORATORY EMBEDDING ADVERSARY — design for approval

**Status: design only.** Nothing has been downloaded, installed or run. It
touches no final or headline data until the user approves this document, and
its settings are frozen in RUN_DECISIONS before it does. Written 2026-09-13,
after the final one-shot and Memon-inspired results were visible, so it is
**post hoc and exploratory** under results plan §28, whatever it finds.

## The question it adds

Does a modern, local, free semantic representation recover **source linkage**
without a language model? The existing attackers span:
- Memon-inspired: lexical TF-IDF grouping, F1_L ≈ 0.25–0.34 on prose;
- one-shot Sonnet: F1_L ≈ 0.65–0.88.

The embedding attacker sits between them. If its linkage approaches Sonnet's,
the membership protection fragmentation provides is weak even against cheap
attackers. If it stays near TF-IDF, the LLM's contextual reasoning, not
semantic similarity alone, is what defeats fragmentation. It is also the
standard reviewer question: "would sentence embeddings have done it?"

## Design (the user's preferred minimal design, which I agree with)

**Embedding-based grouping + the same corrected, deterministic, directional
ordering module used by Memon-inspired.** Only the grouping changes, so any
difference from Memon-inspired in F1_J is attributable to linkage. Ordering
stays the frozen Memon-inspired module, which is at chance on this corpus
(q ≈ 0.5). The attacker should therefore be read mainly through **F1_L**, and
its F1_J will be capped by chance-level q. That cap is intended, and it is
stated in advance.

### Representation
- **Proposed default:** `sentence-transformers/all-mpnet-base-v2`.
  - MPNet-base, 109M parameters, 768-dimensional, mean pooling, Apache-2.0.
  - Max sequence length 384 word pieces. Our longest fragments are well
    under that; the maximum is to be checked on development data.
  - The exact Hugging Face revision commit hash and the file SHA-256s are
    recorded at download time and frozen in RUN_DECISIONS before any final pool.
- Each fragment is embedded independently. No fine-tuning.
- Embeddings are L2-normalized, and similarity is cosine (a dot product).

### Why this model, and the biomedical alternative
- **all-mpnet-base-v2 (recommended).** It is the sentence-transformers
  project's own general-purpose default: the most widely used, documented and
  benchmarked choice. A reviewer recognises it as "the standard embedding
  model", not one picked to help or hurt the attacker. Weakness: general-domain
  training, so clinical terminology in PMC case reports (drug names, rare
  diagnoses) may embed less discriminatively.
- **Biomedical alternative:** a PubMedBERT-based sentence model, for example
  `pritamdeka/S-PubMedBert-MS-MARCO` or `NeuML/pubmedbert-base-embeddings`
  (the exact candidate would be pinned the same way). Strength: vocabulary
  and pretraining matched to clinical case reports, so it is arguably the
  stronger attacker for this corpus. Weaknesses: they are community
  fine-tunes, with less standard training documentation and less
  recognition; and it is one more choice a reviewer can question. Its
  pretraining predates our post-cutoff corpus, so there is no document
  contamination either way.
- **Rule: the model is chosen before any run, never from final or headline
  scores.** Two acceptable pre-commitments:
  1. **mpnet only** (recommended: one exploratory attacker, one number).
  2. **mpnet as the primary exploratory attacker plus the biomedical model as a
     pre-declared secondary**, both reported whatever they show. Running both
     and reporting the better one is not allowed.

### Grouping
- Average-linkage agglomerative clustering on cosine distance, cut to
  **exactly the known N = 7** documents (`scipy.cluster.hierarchy.cut_tree`).
  This is identical to the frozen Memon-inspired grouper except for the
  similarity (`memon_joint.group_known_n`).
- The same tiny seeded jitter (1e-6, seed 42) breaks exact ties.
- No threshold of any kind: the cut is fixed by N.

### Ordering
- Within each predicted group, the frozen Memon-inspired module:
  character-bigram boundary likelihood (n = d = 2) → W = tanh(Δ/2) →
  `order_from_sim.order_cluster`, which is now SHA-256-seeded and
  deterministic. No new parameter.
- **Alternatives considered and not recommended:**
  - A BERT next-sentence-prediction head, or a cross-encoder scoring
    "A then B". Both are directional and probably stronger on order, but each
    introduces a second model and choices (which model, which calibration,
    ordering search over its scores). It would also confound linkage and
    ordering, which is exactly what the minimal design avoids.
  - Embedding-similarity chaining (a greedy or MST path over cosine). It is
    symmetric, so it has no direction, the same defect as the Jaccard floors.

### Presentation and controls
- Masking and presentation are inherited: the fragments go in the per-unit
  seeded shuffled order the model's prompt used, with masked labels.
  `assert_ids_masked` guards the input.
- It is scored by `joint_game.score_row`, the scorer every J attacker goes
  through.

## Every tunable parameter and where its value comes from

| parameter | value | source |
|---|---|---|
| embedding model | all-mpnet-base-v2 (or the pre-declared pair) | fixed standard default, chosen now, before data |
| model revision / hashes | pinned at download | frozen before any final pool |
| pooling | mean (the model's own configuration) | fixed default |
| max sequence length | 384 (model default) | fixed default; development check that nothing truncates |
| normalisation / similarity | L2 / cosine | fixed standard |
| linkage | average | inherited from the frozen Memon-inspired grouper |
| cut | exactly N = 7 | inherited (known-N game J) |
| tie jitter | 1e-6, seed 42 | inherited |
| ordering n, d | 2, 2 | inherited (D12) |
| ordering search | order_cluster, SHA-256 seed | inherited (D13) |
| batch size | 64 | computation only; floating-point effects checked on development data |

**What needs development calibration: nothing is tuned.** A development-only
smoke run (pool 1 screening cells and the 25 development pools' reference cut,
never a final or headline pool) checks three things: the pipeline runs,
nothing truncates, and embeddings are reproducible across batch sizes to
within floating-point noise. No parameter is chosen from its scores.

## Resources (estimates; confirmed before asking for the download)
- **Download:** about 420–440 MB of model weights, plus the Python packages
  `sentence-transformers`, `transformers`, `tokenizers`,
  `huggingface_hub`, `safetensors`, `scikit-learn` and a **CPU** build of
  `torch`, roughly 250–400 MB of wheels. About 0.7–0.9 GB in total, from
  Hugging Face and PyPI. This needs the user's explicit approval.
- **RAM:** about 0.5 GB for the model in fp32, and 1.5–2.5 GB peak while
  embedding in batches of 64. The machine has 31 GB (14 GB free).
- **CPU / GPU:** CPU only. The Intel Iris Xe is not used by PyTorch here, and
  8 logical cores are enough.
- **Runtime:** the final J pools hold roughly 70–80k fragment texts
  (46 headline, 216 grid, 20 identifier). At an estimated 100–250 short texts a
  second on this CPU, that is about 5–15 minutes of embedding, plus seconds of
  clustering and ordering per pool.
- **Cost:** free, fully local, no API.

## Anticipated failure modes
- **Topic, not source.** Case reports in one pool that share a condition, or
  generic clinical sentences ("the patient was discharged"), embed alike, so
  documents merge or split.
- **Short fragments.** Token-window and clause fragments carry little
  semantic content, and their embeddings are weak. Expect the largest drop
  there, which is itself informative about granularity.
- **Identifiers.** Names, SSNs, account numbers and addresses have no semantic
  link to their record. Expect clustering by field type (as Memon-inspired
  does), which lands **below** the analytic baseline. That is the expected,
  correct outcome.
- **Unbalanced clusters.** An exactly-N average-linkage cut can produce one
  large cluster and several small ones; the cluster-size distribution is
  reported.
- **Floating-point nondeterminism** across batch sizes or threads. It is
  checked on development data, and the jitter makes tie-breaking stable.
- **Ordering at chance** is inherited by design, so F1_J is roughly
  F1_L × 0.5 and should never be compared to Sonnet's F1_J as an "ordering"
  result.

## Execution plan after approval
1. The user approves this design, and one model option.
2. The user approves the download: files, sources and sizes, stated first.
3. Install into the project environment, then pin and record the package
   versions, the model revision and the SHA-256s.
4. Development-only smoke run.
5. Freeze everything in RUN_DECISIONS (a new entry).
6. Run on all 282 final J pools. Report it as **POST-HOC EXPLORATORY
   EMBEDDING ADVERSARY**, in its own table rows and never merged into the
   prespecified attacker comparisons.
