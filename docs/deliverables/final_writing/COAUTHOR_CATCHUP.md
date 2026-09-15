# Co-author catch-up: what changed since week 6

**For:** Michael Anyaegbunam and Mohammed Arafat
**Read with:** `docs/PAPER_WRITING_PACKET.md` (the full reference; section numbers below point into it)
**Covers:** everything from the week-6 integration (your code merged 28 Aug; second passes merged 3 Sep) to the final results (14 Sep).

The week-7 methods brief (10 Sep) and the final writing assignments (13 Sep) mentioned some of this in passing. This note is the whole picture in one place. Nothing in it is new work for you except the review checklist at the end.

---

## The short version

1. **The headline game changed from L to J.** The attacker now gets all fragments of 7 documents, mixed, and must recover *which document* and *what order* in one answer. There is no standalone Game L anymore; linkage is read out of the J answer. Game O stays as a reference.
2. **New metrics.** Ordered-pair F1 (F1_J), with the exact split F1_J = F1_L × q into a linkage part and an ordering part.
3. **New baseline.** The analytic "one-bucket" baseline, computed in closed form, replaces the sampled trivial floor. It is called a *baseline*, not a floor.
4. **Renamed attackers.** "Memon-Greedy" and "Memon-MST" are now **Jaccard-Greedy** and **Jaccard-MST**. After a leak fix they sit at chance, and they appear in Game O only.
5. **New statistical attacker, "Memon-inspired."** It combines TF-IDF grouping, Michael's character-bigram boundary statistic, and a new ordering search. It plays Game J. It is not a faithful Memon implementation.
6. **The LLM adversary moved to the paid Batches path.** It now runs claude-sonnet-5 with a one-shot J prompt, masked labels, per-unit shuffling, a 128k output budget, one repair round, and a rule for non-completion.
7. **Two attackers were added after the fact, and one was dropped.** An embedding attacker (all-mpnet-base-v2) was added post hoc. A hierarchical attacker was built and then dropped without running. A post-hoc single-token experiment was also run.
8. **Design locked down.** A development / headline pool split; pool 1 became screening data; the grid was pruned to 9 cells; three cutters were re-cut (subject-verb, coherence-sever, token-window); identifier J was added.
9. **Everything ran.** The final run was 652 one-shot units: 651 completed, 1 non-completion, $119.37 of API credit. Prose stays highly reconstructable. Identifiers do not.

---

## 1. Timeline since week 6

| date | what happened | where it's recorded |
|---|---|---|
| 28 Aug | Week-6 deliverables integrated: Michael's cutters and `run_grid`, Arafat's auditable harness. Pool partition built (71 pools of 7), ID masker and preflight check added, bug 12 fixed. | commits 8f6e025, c7a1b43 |
| 3 Sep | Second passes merged; the grid loop now scores; four fixes to the LLM adversary (details in §4.3). | cda38ba, 3a3f5af |
| 5–10 Sep | **Game J built**: joint game, joint metrics, the Memon-inspired attacker, and the paid batch path. | joint_game.py, joint_metrics.py, memon_joint.py, batch_game.py |
| 10 Sep | **D1:** the classical orderers had leaked the true order; fixed and renamed Jaccard-*. **D2:** 25 development / 46 headline pools. | RUN_DECISIONS D1, D2 |
| 10–11 Sep | **Pool 1** paid as a staged slice. It exposed undersized output caps and a presentation-seeding flaw, both fixed. It then became screening data. | D4, D5, D7 |
| 11 Sep | **D5:** grid pruned to 9 cells. **D6:** 128k output budget, and the non-completion rule. **D7:** re-cuts plus per-unit presentation seeds. **D8:** hierarchical attacker configured; masking side-channel control run. | D5–D8 |
| 13 Sep | Budget raised to $210 cash. Identifier J added. **Headline and grid J and identifier J ran; then headline and grid O.** Results plan and statistics frozen. Attacker names made authoritative. | D9–D13, `docs/adversaries.md` |
| 13–14 Sep | Post-hoc embedding attacker designed, frozen, and run. | D14 |
| 14 Sep | Post-hoc single-token experiment designed, frozen, and run. Hierarchical run dropped. | D16, D17 |
| 14 Sep | Analysis package and paper-writing packet written. | `results/final_analysis/`, `docs/PAPER_WRITING_PACKET.md` |

The week-6 run plan (a 500-document headline O, 71-pool linkage, a 12-cell ordering grid, repeats) was **replaced** by this design. Don't cite its step costs or cell counts.

---

## 2. Game L → Game J

**What you knew:** Game O asks for the order of one document's fragments. Game L asks which fragments belong together. They were scored separately (τ and pairwise F1) and reported as two columns.

**What changed:** the headline is now **Game J (joint)**. The attacker gets every fragment from a pool of **7 documents**, mixed and shuffled, with masked labels. It is told there are 7 documents, and must return 7 groups with each group in its reconstructed order. Why:

- **It is the actual threat model.** Someone holding a fragmented store has everything mixed and is told nothing. O hands the attacker membership for free; L never asks for order. Each is an oracle the real world doesn't provide.
- **L falls out of J for free.** Drop the order from a J answer and you have a grouping, scored as F1_L. So no standalone L experiment was run. **Wording rule:** say "the linkage component of Game J", never "Game L results".
- **O survives as a reference, not a ceiling.** It is a different prompt on different units, and changing the task can hurt a prompted model as easily as help it. So J is not bounded by O, and "J minus O" is not reported. The F1_J = F1_L × q split (§3) is how the paper says which half failed.

**Pools of 7 everywhere** (already announced in week 6) replaced the week-3 global 50-way setting. Pool size sets the chance baseline, so it never varies. The partition was built once (seed 42, 28 Aug) and never regenerated.

---

## 3. Metrics and the analytic baseline

Packet §7 has everything in plain English; this is the summary.

- **F1_J (primary).** Your pairwise F1, but a pair counts only if the two fragments share a document **and** are in the right relative order. Two identities are checked in `harness/test_joint_metrics.py`:
  - ignore direction and it is exactly your old linkage F1 (now called F1_L);
  - with perfect membership it equals **(1 + τ)/2, not τ**. Random order gives 0.5, full reversal gives 0.
- **q = C/K.** Of the pairs the attacker linked correctly, the share it also put in the right direction. Chance is 0.5. Aggregated as q_micro = ΣC/ΣK; if a pool has no correct links, q is undefined, not 0.
- **F1_J = F1_L × q**, exactly, per pool.
- **The analytic one-bucket baseline.** "Put every fragment in one group, in arbitrary order", computed in closed form from each pool's true group sizes. With T true within-document pairs and P pairs in the bucket:
  - E[F1_L] = 2T/(P + T)
  - E[F1_J] = T/(P + T)

  It replaces the Monte Carlo trivial floor, which was noisy and on one small pool landed on 0 by luck. It is a **baseline, not a floor**: an answer of all singletons scores 0, which is lower. On the headline pools it is F1_L 0.299 and F1_J 0.149. **F1_L 0.30 does not mean "30% of documents recovered"**: that is what saying "everything belongs together" scores.
- **A_J = (F1_J − b_J)/(1 − b_J)**, computed per pool and then averaged. 0 at the baseline, 1 at perfect.
- **Identifiers get a second baseline, "schema-order".** Each field's type is visible from its format (an SSN looks like an SSN), so anyone can put the fragments in name → SSN → account → address order for free. That scores F1_J = 0.20 with q = 1.0 and no record knowledge at all. Identifier q therefore measures the template, not reconstruction.
- **Visible-text metrics** (V_L, V_J, permutation nulls, A_VJ) exist only for the single-token experiment (§6).

Statistics (frozen, D13): percentile bootstrap over pools (J) or documents (O), 10,000 resamples, 95% CIs; paired comparisons resample the same pool once and carry both conditions; no multiplicity adjustment. This is the paired-bootstrap design from the week-7 brief, now implemented.

---

## 4. Attackers: what exists now, and the renames

Binding names are in `docs/adversaries.md`. Use exactly these:

| name in the paper | what it is | game | status |
|---|---|---|---|
| Random | random permutation (O); random deal into 7 groups (identifier J) | O; identifier J | baseline |
| Analytic one-bucket | closed-form baseline (§3) | J | baseline |
| Schema-order | format-read field template in one bucket | identifier J | baseline |
| **Jaccard-Greedy** | *was "Memon-Greedy"*; Michael's greedy nearest-neighbour orderer | O only | classical floor |
| **Jaccard-MST** | *was "Memon-MST"*; Michael's spanning-tree orderer | O only | classical floor |
| **Memon-inspired** | new: TF-IDF grouping + Michael's boundary statistic + ordering search | J | statistical attacker |
| One-shot Sonnet | Arafat's LLM adversary, on the paid J path | O and J | main attacker |
| Embedding (post-hoc exploratory) | all-mpnet-base-v2 grouping + the Memon-inspired orderer | J | post hoc, labelled |
| Hierarchical (decomposed) Sonnet | pairwise LLM judgements with blocking | J | built, **dropped unrun** |

### 4.1 The Memon rename (D1, 10 Sep)

- **Why the rename.** The greedy and MST orderers score fragment pairs by **word-bigram Jaccard overlap**. That is symmetric (A→B scores the same as B→A) and has nothing to do with Shanmugasundaram & Memon beyond "build a path through fragments". So "Memon-Greedy / Memon-MST" was the wrong label.
- **The leak.** In Game O they received the raw fragment IDs in true file order. Jaccard is exactly 0 for 86.7% of within-document prose pairs, so almost every step was a tie. Ties were broken by the raw ID or list position, and both reproduce the true order. The published prose τ of +0.32 (Greedy) and +0.70 (MST) was that leak. MST also iterated Python sets, so its output changed between processes.
- **The fix.** Masked labels, a per-document shuffled presentation, and truth-independent tie-breaking; MST's loops are now sorted and deterministic. The algorithms themselves are unchanged (a 6-line diff to `orderers.py`). The old behaviour is reachable only behind an audit flag.
- **Corrected result: chance.** Prose τ −0.021 / −0.011; identifiers −0.023 / −0.002 (`results/harness_results.json`). Final Game O: −0.061 to +0.024 across every condition.
- **Michael, this bears on your open week-4 question.** Identifier Memon Game O went 0.06 → 0.48 when you switched from exhaustive search to greedy/MST (0.516 by week 6). With masking and truth-independent ties, the same orderers score ≈ 0 on the same identifiers. That is consistent with the tie-breaking leak rather than a real gain. We have not reproduced the week-2 exhaustive number, so we can't say why the jump appeared exactly at the switch. If you found a cause at the time, tell us.
- **Their old "Game L" column** was never a Jaccard attack. Both rows used the shared TF-IDF grouper (the one that replaced the degenerate single-linkage grouping in week 6). So they appear in **Game O only**; no J version was built to make tables symmetrical.

### 4.2 The new Memon-inspired attacker (`adversaries/memon_joint.py`, 9 Sep)

The one statistical attacker that plays J:

- **Grouping:** TF-IDF cosine similarity → average-linkage clustering → cut to exactly 7 groups (a tiny seeded jitter breaks exact ties). This is the week-6 fixed grouper, which the repo still calls "B_stat".
- **Ordering:** **Michael's `memon.score_pair` boundary statistic** from week 2, a character model trained on the pool's own fragments. Candidate successor B of fragment A is scored by how well that model predicts B's first two characters from the text across the boundary. It is directional: s(A→B) ≠ s(B→A). Each pair becomes a weight W = tanh((s_AB − s_BA)/2), and a deterministic local search finds the order that agrees with the most weight.
- **Setting:** n = d = 2, frozen. On development data its ordering was at chance for every n from 2 to 8, so the choice can't favour it.
- **Determinism fix (D13):** the search's third starting point was seeded with Python's `hash()`, which varies between processes; now it uses SHA-256. This changed 9 of 282 pools by at most 0.023.
- **What's Memon and what isn't:** only the idea of judging adjacency by how well a character model predicts text across a boundary. It has **no PPM model and no Hamiltonian-path / tree-pruning reassembly**.
- **Result:** headline F1_J 0.168 (baseline 0.149); ordering at chance (q 0.49). Its role in the paper is a statistical floor.

### 4.3 What happened to the LLM adversary (Arafat)

Your adversary is the ancestor of the main attacker. The attack logic now lives in `adversaries/joint_game.py` (prompts, presentation) and `adversaries/batch_game.py` (the paid path); `adversaries/llm_adversary.py` remains for the older interactive runs. What changed:

- **Model and path.** `claude-sonnet-5` through the Message Batches API (50% discount; results come back hours later, keyed by request).
- **No temperature.** The week-2 brief said "temperature 0". This model rejects the temperature parameter, so none is set; it runs with default sampling and its default adaptive reasoning. The paper must not say "we varied temperature" or "temperature 0".
- **One-shot J prompt.** All fragments of the pool, "7 records in total", group and order them, "return ONLY a JSON array of 7 arrays". One prompt per pool.
- **Masking.** Your `item_N` idea became a collision-free shuffled permutation of labels like `m_0000153`. A preflight check refuses to send any prompt containing a raw fragment ID.
- **Per-unit shuffling (D7).** Label assignment and presentation order are seeded per pool from a SHA-256 of that pool's fragments. Before this fix, the shown order depended only on fragment count and correlated with the truth.
- **Masking side-channel control (G3).** On a development pool, raw IDs in true order let the model score F1_J 0.994 / 1.000, so the planted leak is fully exploited. Masked, its order agrees with the label numbers only as much as its accuracy implies. So there is no side channel; masked reconstruction is high because the model reads the content. This is the formal version of your week-3 methods note, and the note is cited as the origin.
- **One structural repair round.** If an answer is unparseable or its labels are missing, duplicated or invented, the original prompt is re-sent with bookkeeping-only feedback (never ground truth). Anything still unplaced becomes a singleton.
- **The 128k budget and non-completion (D6).** Every request gets the model's full 128,000-token output ceiling, one attempt. At least 96.7% of every J answer's output is hidden reasoning. A pool that uses up the budget without an answer is a **resource-bounded non-completion (RBNC)**: recorded, never re-asked, never scored as 0. This happened once in the whole study.
- **Fixes to your code on 3 Sep** (made by Aiden while running it): `repair_partition` let same-group duplicates through; Game L can now run per pool with per-pool resume; max_tokens is sized to the answer; a guard against duplicate output lines from two processes appending at once.
- **Bug 12 and the week-4 prose run.** `guess_order` presented fragments in true document order (23 of 25 week-4 prose ordering guesses were exactly sequential). So the week-4 prose τ 0.97 is **not a result** and is not used anywhere. Everything final was produced after the fix.

### 4.4 Added and dropped attackers

- **Embedding attacker (post hoc, D14).** Added to answer "would sentence embeddings have done it?" The embedding is the only change from Memon-inspired: all-mpnet-base-v2 cosine similarity replaces TF-IDF, and the same orderer is used. It was frozen before it ran, and its first result was kept. Headline F1_L 0.364, against Memon-inspired 0.339 and Sonnet 0.882. **Always labelled post-hoc exploratory.**
- **Hierarchical attacker.** Built and tested on development data as the design with no per-call ceiling. Its job was to rescue headline pools the one-shot attacker couldn't finish. None failed (0 of 46), so it was **dropped without running** (D17). Don't report it as a result. Some analysis-package files still say "pending"; that is out of date.

---

## 5. Design changes that touch your work

- **Development vs headline pools (D2).** 25 development pools (the grid) and 46 headline pools that received no requests until the final run. 21 headline documents had been used in early development (the 8-document probe, the 25-document pilot, the llm-cut cache). Don't call the headline pools "untouched"; say "headline pools", with the development contact disclosed.
- **Pool 1 is screening data (D5).** It was paid for first as a slice of the grid and exposed two operational problems (undersized output caps; presentation shuffles seeded per run instead of per pool). Its results were then used to prune the grid, so it is excluded from every final table. The grid is pools 2–25 (24 pools).
- **Grid pruned to 9 cells (D5).** Dropped: semantic × token-window, coherence-sever × sentence, and the LLM-cutter cell. Kept: random × {sentence, clause, token-window}; semantic × {sentence, clause}; coherence-sever × {clause, token-window}; subject-verb × {sentence, clause}. **Semantic × sentence is ordinary sentence splitting**, and the headline uses the same cut.
- **Re-cuts (D7).**
  - *Subject-verb (Michael's):* a cut may fall only on whitespace; four cut points had landed inside "patient’s" / "MP™". Every re-cut cell rejoins its source exactly. Fire rates after the re-cut: 66.7% of sentences and 57.0% of clauses (`ASSIGNMENTS.md`), well clear of the 20% collapse threshold.
  - *Coherence-sever:* redefined by Aiden, because its topic-shift rule fired at 82–84% of boundaries and collapsed onto semantic. It now fires on "the adjacent units share no content word". Aiden writes this strategy.
  - *Token-window:* counts 12 whitespace words for every strategy.
- **Grid documents capped** at 30 reference sentences (62 of 175 documents truncated), so granularity, not the cap, drives fragment count. The headline uses full-length documents.
- **Identifier J added (D11).** 20 pools of 7 synthetic records (28 fragments each), from Arafat's generator scaled to 500 records. It uses only records r_0050–r_0499, because r_0000–r_0049 were shown to an LLM in the week-2/3 runs. The frozen rule: joint reconstruction is "near the schema-order baseline" only if the whole 90% CI on the schema advantage lies within ±0.10.
- **The synthetic prose corpus was retired** (announced in week 6; here is the reason). In the 25 hand-written notes, same-record sentences were *less* lexically similar than different-record ones (TF-IDF Cohen's d −0.077, vs +0.458 on real PMC prose). The statistical attacker's signal pointed the wrong way. The paper reports this as a methods finding.

---

## 6. The results in one screen

Full tables are in packet §9; figures and tables are in `results/paper_figures/` and `results/paper_tables/`.

| experiment | result |
|---|---|
| Headline prose J (46 pools) | Sonnet F1_J **0.723** [0.702, 0.743], F1_L 0.882, q 0.792; baseline 0.149; exact documents 1/322 |
| Attackers, headline F1_L | analytic 0.299 · Memon-inspired 0.339 · embedding (post hoc) 0.364 · **Sonnet 0.882** |
| Grid J (9 cells × 24 pools) | Sonnet F1_J 0.498 (subject-verb × clause) to 0.801 (random × sentence); subject-verb most resistant at both granularities |
| Game O | Sonnet τ 0.769 headline, 0.724–0.943 grid; Jaccard-Greedy / MST at chance |
| Identifier J (20 pools) | Sonnet F1_J **0.083**: below both the analytic (0.10) and schema-order (0.20) baselines; every group template-perfect, but linkage at template chance (0.132 vs 1/7); 90% CI on the schema advantage [−0.162, −0.129] |
| Completion and cost | 652 one-shot units, 651 completed, 1 RBNC; $119.37 credit |
| **Post-hoc** single-token edge (20 pools) | Same four-sentence excerpts cut into sentences vs single words: Sonnet's null-adjusted joint score fell from **0.588 to 0.016** (paired difference 0.572 [0.539, 0.607], 20/20 pools); some linkage signal survived |

The story: prose stays highly reconstructable against a strong LLM under every cut tested; similarity-based attackers stay at the floor; identifiers behave qualitatively differently; and extreme atomization pushes joint reconstruction to chance on excerpts, while some linkage survives.

---

## 7. How your work is described now

**Michael**

- Random baseline and scoring (`harness/scoring.py`): your τ and pairwise-F1 functions (`score_ordering`, `score_linkage`) are still imported by the final scorer. Arafat's week-6 coverage and partition checks sit on top of them.
- Harness, loader, and the greedy / MST orderers: now **Jaccard-Greedy / Jaccard-MST**, Game O floors, after the D1 masking fix.
- `memon.py` boundary statistic: the ordering signal of **Memon-inspired**.
- Random cutter and subject-verb cutter: two of the four strategies in the paper, both in the final grid. Subject-verb is the most resistant condition.
- `run_grid.py`: drove the development grid. The final paid run went through the batch path instead, on cells cut by your cutters (`results/grid_A/*/cell_manifest.json`).
- Your writing assignment: §3.2 cutters, §4.2 metrics (moved to you from Arafat, because the scorer is yours), §5.1 statistical baselines (`docs/deliverables/final_writing/ASSIGNMENTS.md`).

**Arafat**

- Record generator and field cutter: the identifier corpus, scaled to 500 records.
- The prose cutter: now `datagen/prose_cutter.py`, the reference cut and the shared splitter every strategy imports.
- The LLM adversary: the one-shot attacker's lineage.
- The ID-leak finding: the origin of the masking requirement and of the G3 control.
- The auditable harness: coverage, partition validity, baselines beside scores.
- Your writing assignment: §3.1 reference cutter, §4.1 the one-shot adversary.
- **Unconfirmed:** did you write the pool builder (`datagen/build_pools.py`)? An earlier brief credited you, but no deliverable records it.

---

## 8. Wording rules for your review and your sections

- Never write "Memon" alone, "faithful Memon", or "pre-LLM state of the art". The week-2 brief used that last phrase; it was an overclaim.
- "Jaccard-Greedy / Jaccard-MST" for the classical orderers, Game O only.
- "The linkage component of Game J", never "Game L results".
- "Analytic one-bucket baseline", not "floor".
- Every embedding and single-token result is marked **post-hoc exploratory**.
- The hierarchical attacker is "not run (dropped)", not "pending".
- "Headline pools", not "untouched pools".
- No temperature claims for the LLM.
- Don't quote a pool-1 or week-4 score as a finding.

---

## 9. What I need from you (the co-author review)

Please read `docs/PAPER_WRITING_PACKET.md`. At minimum read §1 (summary), §2 (design history), §6 (attackers), §7 (metrics), §9 (results) and §12 (what we can and cannot claim). Then send back:

- [ ] **Errors about your own work.** Anything in the packet, or in §7 here, that misdescribes what your code does or who wrote it.
- [ ] **Claims you can't verify.** Mark any sentence you think is wrong or unsupported, with the section number.
- [ ] **Arafat:** confirm yes or no on `datagen/build_pools.py`.
- [ ] **Michael:** does the D1 explanation of the 0.06 → 0.48 jump (§4.1) match what you saw? If you found a different cause at the time, say so.
- [ ] **Handover note.** One paragraph on anything about your code that isn't written down in the repo. After the project ends, nobody can ask.
- [ ] **Your writing section**, if it isn't in yet, against `ASSIGNMENTS.md`. The "no numbers from unrun experiments" rule is lifted: everything has run, so cite numbers from `results/final_analysis/` or the packet.
- [ ] **Author contributions.** Check your rows in `docs/CONTRIBUTIONS.md`.

Review deadline: ________.
