# POST-HOC EXPLORATORY EMBEDDING ADVERSARY — design (approved with corrections, frozen in RUN_DECISIONS D14)

**Status:** the user approved the design on 2026-09-13 with eight corrections,
all applied below. Nothing has been downloaded, installed or run. The model and
package download needs the user's separate, explicit approval. The attacker was
designed after the final one-shot and Memon-inspired results were visible, so
it is **post hoc and exploratory** under results plan §28, whatever it finds.
It never enters the prespecified attacker comparisons.

## The question it adds

Does a modern, local, free semantic representation recover **source linkage**
without a language model? The existing attackers span:
- Memon-inspired: lexical TF-IDF grouping, F1_L ≈ 0.25–0.34 on prose;
- one-shot Sonnet: F1_L ≈ 0.65–0.88.

The embedding attacker sits between them. If its linkage approaches Sonnet's,
the membership protection fragmentation provides is weak even against a cheap
attacker. If it stays near TF-IDF, something beyond semantic similarity, such
as the LLM's contextual reasoning, is doing the work. It also answers the
standard reviewer question: "would sentence embeddings have done it?"

## Design

**Embedding-based grouping + the same corrected, deterministic, directional
ordering module used by Memon-inspired.**

- **What changes.** The embedding representation used for grouping is the
  **only** architectural component changed relative to Memon-inspired.
- **How to compare.** **F1_L (the linkage component) is the primary
  comparison** with Memon-inspired and with Sonnet. F1_J differences are not
  attributed solely to linkage: different predicted clusters change which
  pairs the ordering module sees, so q can change indirectly. q and F1_J are
  reported and compared as secondary.
- **Ordering expectation.** The inherited ordering module was near chance in
  the existing Memon-inspired results (q_micro ≈ 0.49–0.52 on prose). q is
  still measured and not assumed: different predicted clusters can alter its
  performance.

### Representation
- **Model: `sentence-transformers/all-mpnet-base-v2` only.** A widely used,
  general-purpose Sentence Transformers model: MPNet-base, 109M parameters,
  768-dimensional mean-pooled embeddings, Apache-2.0.
- The Hugging Face revision is pinned to
  `e8c3b32edf5434bc2275fc9bab85f82640a19130`, with the file SHA-256s in
  RUN_DECISIONS D14.
- Each fragment is embedded independently. No fine-tuning.
- Embeddings are L2-normalized, and similarity is cosine (a dot product).
- **Domain-specific (biomedical) embeddings are not part of this run.** They
  are an alternative and a possible future sensitivity analysis. They are not a
  second model to select between, and no model is chosen from final or
  headline scores.
- **Training data and contamination.** Per its model card, the model was
  trained on more than 1 billion sentence pairs from existing datasets (for
  example S2ORC scientific abstracts). Those datasets predate the evaluated
  corpus of post-cutoff PMC case reports, which reduces the concern that it
  has memorized these documents. It is not a claim that contamination is
  absent.
- **Truncation.** The model card states that inputs longer than 384 word
  pieces are truncated by default. The smoke test measures how many fragments,
  if any, reach that limit.

### Grouping
- Average-linkage agglomerative clustering on cosine distance, cut to
  **exactly the known N = 7** documents (`scipy.cluster.hierarchy.cut_tree`).
  This is identical to the frozen Memon-inspired grouper
  (`memon_joint.group_known_n`) except for the similarity.
- The same tiny seeded jitter (1e-6, seed 42) breaks exact ties.
- No threshold of any kind: the cut is fixed by N.

### Ordering
- Within each predicted group, the frozen Memon-inspired module:
  character-bigram boundary likelihood (n = d = 2) → W = tanh(Δ/2) →
  `order_from_sim.order_cluster`, which is SHA-256-seeded and deterministic
  (D13). No new parameter.
- **Alternatives considered and not used:**
  - A BERT next-sentence-prediction head, or a cross-encoder scoring
    "A then B". Both are directional, but each adds a second model and
    calibration choices, and would change linkage and ordering together.
  - Similarity chaining over cosine (a greedy or MST path). It is symmetric,
    so it has no direction, the same defect as the Jaccard floors.

### Presentation and scoring
- Masking and presentation are inherited: the fragments go in the per-unit
  seeded shuffled order the model's prompt used, with masked labels, and
  `assert_ids_masked` guards the input.
- Scored by `joint_game.score_row`, the scorer every J attacker goes through,
  on all 282 final J pools (46 headline, 216 grid, 20 identifier).

### Identifiers — a hypothesis, not an expected success
Names, SSNs, account numbers and addresses carry little semantic link to their
record. **Hypothesis:** embedding similarity will cluster mainly by field type,
as Memon-inspired did, which would put F1_J below the analytic baseline. This
is stated in advance as a hypothesis to test. It is not an expected or
"correct" outcome, and it is reported whichever way it falls.

## Every tunable parameter and where its value comes from

| parameter | value | source |
|---|---|---|
| embedding model | all-mpnet-base-v2 | chosen before any run; the only model |
| model revision / file hashes | e8c3b32e…, SHA-256s in D14 | frozen before download |
| pooling | mean (the model's own configuration) | model default |
| max sequence length | 384 word pieces (model configuration) | model default; the smoke test measures actual lengths and truncation |
| normalisation / similarity | L2 / cosine | fixed standard |
| linkage | average | inherited from the frozen Memon-inspired grouper |
| cut | exactly N = 7 | inherited (known-N game J) |
| tie jitter | 1e-6, seed 42 | inherited |
| ordering n, d | 2, 2 | inherited (D12) |
| ordering search | order_cluster, SHA-256 seed | inherited (D13) |
| batch size | 64 | computation only; the smoke test checks numerical stability across batch sizes |
| device | CPU | the only device available |

No parameter is tuned and nothing requires calibration.

## Development smoke test — score-blind

Development-only material:
- grid **pool 1** (the screening pool) in all nine cells;
- identifier records **r_0000–r_0049** (excluded from the final sample), dealt
  into pools of 7.

No final, grid pool 2–25 or headline pool is touched. **No reconstruction
score is computed or printed.** It checks:
1. **Pipeline execution** end to end, from input to a scored-format output.
2. **Actual tokenizer lengths and truncation.** The real word-piece length of
   every fragment, and how many exceed the 384 limit.
3. **Embedding reproducibility.** The same inputs twice give identical
   embeddings.
4. **Batch-size numerical stability.** Batch sizes 1, 16, 64 and 128 are
   compared by maximum absolute difference, and by whether they give the same
   predicted clusters.
5. **Clustering and scorer compatibility.** The output is a valid partition
   with exactly N groups, every masked id once, accepted by `score_row`'s
   partition check. Only validity is reported, never F1.
6. **Determinism across processes.** Two runs under different
   PYTHONHASHSEED values give identical reconstructions.
7. **CPU throughput benchmark.** Measured fragments per second on this
   machine, and a measured projection for the 62,527 final fragments.

Development scores are never used to select anything. If a check fails, the
fix is a correctness fix (reported in D14), never a tuned parameter.

## Pinned model files (revision e8c3b32edf5434bc2275fc9bab85f82640a19130)

| file | bytes | SHA-256 (LFS) or git blob id |
|---|---|---|
| model.safetensors | 437,971,872 | sha256 78c0197b6159d92658e319bc1d72e4c73a9a03dd03815e70e555c5ef05615658 |
| tokenizer.json | 466,021 | blob 7c8e194053bc80e27e19bb2125469e4f289ab2b3 |
| vocab.txt | 231,536 | blob 1c51ab79a2298a340952d3e6012042a9c84bbe4d |
| config.json | 571 | blob b9fd4298819da011007a6a4ceb728c860914fc88 |
| modules.json | 349 | blob 952a9b81c0bfd99800fabf352f69c7ccd46c5e43 |
| 1_Pooling/config.json | 190 | blob 4e09f293dfe90bba49f87cfe7996271f07be2666 |
| sentence_bert_config.json | 53 | blob 4eb670bb4e7f34e9031acec2b86d39e5c921198e |
| config_sentence_transformers.json | 116 | blob fd1b291129c607e5d49799f87cb219b27f98acdf |
| special_tokens_map.json | 239 | blob 378d4fa393d5eaccf69c437a20f1cda6ac65c14d |
| tokenizer_config.json | 363 | blob 20ae1276042f43d1c80f4f7b7f084a8704592c1d |

## Resources
- **Download** (itemised in the approval request): the 10 model files needed at
  the pinned revision (438.7 MB, almost all `model.safetensors`), plus the
  Python packages (roughly 150 MB of main wheels, about 165 MB with small
  dependencies). The repo's ONNX / OpenVINO / `pytorch_model.bin` files are not
  downloaded.
- **RAM:** about 0.5 GB for the model in fp32, and a few GB peak while
  embedding. The machine has 31 GB.
- **CPU / GPU:** CPU only.
- **Runtime:** no estimate is used. The smoke-test benchmark gives the measured
  projection, which is reported before the final run.
- **Cost:** free, fully local, no API.

## Anticipated failure modes
- **Topic, not source.** Case reports in one pool that share a condition, or
  generic clinical sentences, embed alike, so documents merge or split.
- **Short fragments.** Token-window and clause fragments carry little semantic
  content, so the embeddings are weak there.
- **Identifiers:** the field-type clustering hypothesis above.
- **Unbalanced clusters** from an exactly-N average-linkage cut; the
  cluster-size distribution is reported.
- **Floating-point nondeterminism** across batch sizes or threads, checked in
  the smoke test.

## Execution plan
1. ~~The user approves the design~~ (done, with corrections) → frozen in D14.
2. **The user explicitly approves the stated download.**
3. Install into the project environment. Record the resolved package
   versions and verify the model files against the D14 SHA-256s.
4. Score-blind development smoke test and throughput benchmark. Results go in
   a D14 addendum.
5. Run on all 282 final J pools. Report it as **POST-HOC EXPLORATORY
   EMBEDDING ADVERSARY**, in its own table rows, with F1_L as its primary
   comparison.
