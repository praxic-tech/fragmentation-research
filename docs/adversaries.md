# Adversaries — the authoritative names and definitions

This file is the single source for attacker names in every paper table and
figure. It was written 2026-09-13 from a code and git-history audit. Earlier
documents that disagree carry dated clarification notes that point here
(RUN_DECISIONS D1 and D12, RUN_PLAN, paper_section3, the writing assignments).

**No attacker in this study is a faithful implementation of Shanmugasundaram &
Memon.** A faithful implementation needs their PPM-derived directional
adjacency model and their maximum-weight Hamiltonian-path / tree-pruning
reassembly. Neither exists here. Never write "Memon" alone, and never "pre-LLM
state of the art".

## Definition table

| attacker | authored / implemented by | grouping / linkage | ordering | directional? | game O / game J | faithful vs inspired / custom | role in paper |
|---|---|---|---|---|---|---|---|
| Random | Michael (week 1); per-document seeding for the final O floor by Aiden | random partition into the known N (J: identifier only, D11) | random permutation | — | O; identifier J (D11) | custom | trivial baseline |
| Analytic one-bucket | Aiden (`harness/joint_metrics.py`) | every fragment in one group | arbitrary (closed-form expected value) | — | J, every pool | custom | trivial baseline |
| Schema-order | Aiden (`analysis/identifier_schema_baseline.py`, D11) | every fragment in one group | the field template, with each field's type read from its format | template only | identifier J only | custom | trivial baseline (structure-aware) |
| Jaccard-Greedy | Michael (`harness/orderers.py`); D1 masking and determinism fix by Aiden | **none** (see "the game L trap" below) | greedy nearest-neighbour path over word-bigram Jaccard | symmetric | **game O only** | custom, **not** Memon | classical floor |
| Jaccard-MST | Michael (`harness/orderers.py`); D1 fix by Aiden | **none** | maximum-spanning-tree path over word-bigram Jaccard | symmetric | **game O only** | custom, **not** Memon | classical floor |
| Memon-inspired | Aiden (`adversaries/memon_joint.py`, `harness/order_from_sim.py`, the TF-IDF grouper in `adversaries/memon_linkage.py`); Michael (`adversaries/memon.py` boundary statistic) | TF-IDF cosine + average-linkage clustering, cut to exactly N | character-bigram boundary likelihood → antisymmetric weight → deterministic local ordering search | ordering: directional; grouping: symmetric | game J (all 282 final J pools) | **inspired**, not faithful | statistical attacker |
| One-shot Sonnet | Arafat (original LLM adversary); Aiden (game J prompt, masking, paid batch path) | the model | the model | yes | O and J | n/a (LLM) | strong semantic attacker |
| Hierarchical / decomposed Sonnet | Aiden (`adversaries/hierarchical.py`, `adversaries/hier_batch.py`) | TF-IDF blocker (k = 20, D8) → Sonnet pair judgements → exactly-N clustering | Sonnet pairwise directions → rank aggregation (`order_from_sim`) | yes | J (headline; **pending**) | custom | strong semantic attacker (decomposed / scalable) |

Michael's week-2 compression-distance (NCD) baseline is in no final table.

## Jaccard-Greedy and Jaccard-MST

**What they are.** Michael's original classical game-O orderers
(`harness/orderers.py`, uploaded 2026-07-19). His harness labelled them
**"Memon-Greedy" / "Memon-MST"**. That label was wrong: they share nothing
with the Memon method beyond "build a path through fragments". Both score a
pair of fragments by the **word-bigram Jaccard** overlap of their texts, which
is **symmetric**, so neither has a native directional ordering signal, and
neither has a joint-linkage mechanism.
- **Greedy:** start at one of the two fragments with the lowest average
  similarity, then repeatedly append the most similar unvisited fragment. Keep
  the better of the two chains.
- **MST:** build a maximum spanning tree (Prim's algorithm), start at a leaf,
  and walk along the heaviest unvisited edge, jumping to the best remaining
  fragment when stuck.

**The D1 correction** (RUN_DECISIONS D1, commit ac1c72b, 2026-09-10). The
algorithms themselves are unchanged; the diff to `orderers.py` is 6 lines.
1. *The leak.* Game O handed both orderers the raw fragment IDs
   (`prose_0002_frag_000`, …) in true file order. Jaccard is exactly 0 for
   86.7% of within-document pairs, so almost every step was a tie. Ties fell
   to the raw ID or the list position, and both reproduce the true order. The
   published τ of +0.3232 (Greedy) and +0.7044 (MST) on prose was leakage.
2. *Masked, shuffled presentation.* Every orderer now sees random masked labels
   in a shuffled order, seeded per document from SHA-256 of its fragment set
   plus the run seed, using its own random generator. `assert_ids_masked`
   refuses raw IDs.
3. *Truth-independent tie handling.* Every tie now resolves on a random label
   or a shuffled position: Greedy's start and next step, and MST's leaf choice.
4. *The deterministic sorted-set fix.* MST iterated Python sets, whose order
   changes per process (τ 0.704416 / 0.704440 / 0.704190 across three hash
   seeds). Those loops are now sorted. The output is identical under
   PYTHONHASHSEED 0, 1 and 2 (test G5b, `harness/test_classic_orderers.py`).
5. *Corrected performance.* τ −0.0304 (Greedy) and −0.0175 (MST) on prose:
   chance. The old behaviour is reachable only behind `--legacy-unmasked-order`,
   which is audit-only.

**The game L trap.** The Jaccard groupings Michael first used
(`greedy_grouping` single-linkage, `mst_grouping` MST cut) were degenerate:
they collapsed about 90% of a corpus into one cluster. In week 5 they were
replaced by the TF-IDF cosine + average-linkage grouper
(`memon_linkage.memon_grouping(variant="fixed")`), shared by both. Any
historical "Jaccard-Greedy / Jaccard-MST game L" number is therefore that
TF-IDF grouper, identical for both, and **not an independent Jaccard linkage
attack**. In the final paper they appear in game O only. No game J version is
built to make the J table symmetrical.

## Memon-inspired (`adversaries/memon_joint.py`)

The separate joint statistical attacker. Its only setting is frozen at
n = d = 2 (RUN_DECISIONS D12).
- **Grouping / linkage.** TF-IDF cosine similarity, then average-linkage
  agglomerative clustering, cut to exactly the known N source documents
  (`cut_tree`), with a tiny seeded jitter for exact ties. Symmetric. Our own.
  The repository calls this grouper "B_stat", a legacy name.
- **Ordering.** A directional character-bigram boundary likelihood
  (`memon.score_pair`, Michael). It builds a character model from the pool's
  own fragments (2-character contexts, add-0.5 smoothing). A candidate
  successor B of fragment A is scored by the log-probability of B's first 2
  characters given the characters that precede them across the boundary.
  s(A→B) ≠ s(B→A).
- **Weighting.** Each pair becomes an antisymmetric weight
  W = tanh((s_AB − s_BA)/2), bounded, with no free parameter.
- **Search.** A deterministic local ordering search (`order_from_sim.order_cluster`):
  the order that agrees with the most weight, found by insertion local search
  from three deterministic starts. The third start's seed was made
  process-stable with SHA-256 on 2026-09-13 (RUN_DECISIONS D13).
- **Masking.** Masking happens inside the attacker; the fragments go in the
  per-unit seeded order the model's prompt used.

**What comes from Shanmugasundaram & Memon:** only the idea of judging whether
one fragment follows another by how well a statistical model of the
characters, trained on the fragments themselves, predicts the text across the
candidate boundary.

**What is ours, a substitution:**
- a fixed-order smoothed character model in place of PPM (which blends several
  context orders through escape probabilities);
- TF-IDF grouping (the original reassembles fragments of one file and has no
  document-grouping step);
- the tanh weighting;
- a pairwise local ordering search in place of their maximum-weight
  Hamiltonian-path / tree-pruning procedure;
- the masking and presentation controls.

**How it differs from the Jaccard pair:** its ordering signal is directional
where Jaccard's is symmetric; it is character-level where theirs is word
overlap; and it groups into exactly N, so it plays game J. On this corpus its
ordering is still at chance (q ≈ 0.5), and it is reported as a statistical
attacker whose results sit at the floor, not as a competitive one.

## Wording rules for the paper

- Use exactly: Random, Analytic one-bucket baseline, Schema-order baseline,
  Jaccard-Greedy, Jaccard-MST, Memon-inspired, One-shot Sonnet,
  Hierarchical (decomposed) Sonnet.
- "Memon-inspired" goes on `memon_joint` only, with one sentence naming the two
  substitutions (no PPM, no Hamiltonian-path search). Cite the original paper
  for the context-model idea only, and verify the reference against the source.
- The linkage number reported for game J is "the linkage component of game J"
  (results plan §29), never a separate game L experiment.
- A post-hoc exploratory embedding adversary is designed in
  `docs/embedding_adversary_design.md` and has not been run.
