# Week 5 — grid build

**Assigned 8/1/2026, due 8/8/2026.** Goal: parameterized cutter + run random/memon
across cells on the current small corpus to debug the pipeline. Small-corpus numbers
are throwaway; real results come after the larger prose corpus lands. No LLM adversary
on the grid yet — that saves tokens.

Filed by function, not by author, per the convention set in `1ecdcc9`. Author is
recorded here rather than in a folder name.

---

## What landed

| File in repo | From | Author |
|---|---|---|
| [`datagen/prose_cutter.py`](../../../datagen/prose_cutter.py) | `cutter.py` | Arafat |
| [`datagen/coherence_sever.py`](../../../datagen/coherence_sever.py) | `coherence_sever.py` | Aiden |
| [`datagen/generate_prose_raw.py`](../../../datagen/generate_prose_raw.py) | `generate_prose_raw.py` | Arafat |
| [`datagen/merge_corpus.py`](../../../datagen/merge_corpus.py) | `merge_corpus.py` | Aiden |
| [`adversaries/llm_adversary.py`](../../../adversaries/llm_adversary.py) | `run_llm_adversary.py` | Arafat |
| [`data/prose/prose_raw.jsonl`](../../../data/prose/prose_raw.jsonl) | `prose_raw.jsonl` | Arafat |

`prose_fragments.jsonl` and `prose_answer_key.jsonl` were also submitted but are
byte-identical to `data/prose/` — not copied.

### Changes made on intake

1. **Path anchoring.** Every script resolved its paths against its own folder
   (`BASE_DIR`), which was correct for a flat submission folder and wrong once the
   files sit in `datagen/` and `adversaries/`. All four now anchor **defaults** to the
   repo root and take **CLI paths as given** (relative to the working directory),
   which is ordinary CLI behavior. `apikey.env` is read from the repo root.
2. **`run_llm_adversary.py` → `adversaries/llm_adversary.py`.** It supersedes the old
   identifier-only script: generalized to variable fragment counts, CLI-configurable,
   and it emits the `{"groups": {...}}` schema the harness loader expects. It is
   already the de-facto live adversary — the week-4 prose results in `results/` are in
   its output schema. The previous version is preserved at
   [`archive/week4_llm_adversary.py`](../../../archive/week4_llm_adversary.py).
3. **Name.** `cutter.py` → `prose_cutter.py`, because `datagen/cutter.py` is the
   existing identifier cutter and the two are unrelated.

### Verified

All four scripts run from the repo root against `data/prose/`. `generate_prose_raw.py`
round-trips to a file identical to the committed `prose_raw.jsonl`. Cell output scores
end-to-end through `corpus_expansion/run_baselines.py` (see gap 2 for the caveat).

| cell | fragments (25 docs) |
|---|---|
| semantic × sentence | 104 |
| semantic × clause | 115 |
| semantic × token-window (k=12) | 99 |
| coherence-sever × sentence | 101 |
| coherence-sever × clause | 113 |
| coherence-sever × token-window (k=12) | 109 |

---

## Grid coverage — 6 of 12 cells

|  | sentence | clause | token-window |
|---|---|---|---|
| random | **missing** | **missing** | **missing** |
| semantic | built | built | built |
| coherence-sever | built | built | built |
| subject-verb | **missing** | **missing** | skipped (degenerate) |
| llm-cut | **missing** — 1 cell, model picks granularity | | |

**Michael's assignment did not arrive.** That is random cut, subject-verb (spaCy), and
the grid loop — 5 of the 6 missing cells plus the thing that runs them. Nothing else in
week 5 is blocked on it, but the grid cannot execute without it.

Aiden's `llm cutter spec` is also outstanding; it was scoped to build once the corpus
lands, so it is on schedule rather than late.

---

## Resolved on 2026-08-10 (corpus promotion)

The gaps below were closed when `corpus_expansion/` was dissolved into the
pipeline. Kept here as the record of what week 5 shipped versus what it needed.

- **Two tokenizers → one.** `prose_cutter._split_sentences` was a regex while
  `_split_clauses` used spaCy. Both now share a single spaCy base and
  `coherence_sever` imports it rather than reimplementing it. Verified:
  `semantic × sentence` reproduces `data/prose/prose_fragments.jsonl` exactly,
  and the clause-under-sentence inversion is gone (0/120 sampled, was 50/500).
- **Filename mismatch → gone.** Cutters emit `prose_fragments.jsonl` /
  `prose_answer_key.jsonl`, matching `data/prose/`. A grid cell now scores
  through `harness/run_baselines.py --data <cell>` with no renaming. Verified.
- **Answer-key schema split → gone.** Both cutters write `{record_id, order[]}`.
- **`--window-size` default → 12**, per RUN_PLAN.
- **Double cut → gone.** `cut_corpus` computes its stats during the write pass.
- **Fixed Memon → it IS the grouping now.** Not an extra row: `eval_memon`'s
  `method` argument selects the Game O ordering heuristic only, and Game L
  always uses the fixed `B_stat`. Both Memon rows share one grouping algorithm
  and differ only in ordering τ. `greedy_grouping` / `mst_grouping` are no
  longer imported by the harness; `--grouping legacy-*` reproduces pre-fix
  tables for audit. On a real clause cell the fixed grouping scores F1 0.161
  (P 0.118 / R 0.253) against random 0.039 — balanced, versus the recall-0.97
  blob the legacy path produces.
- **Corpus scale-up → done.** `data/prose` is 500 real post-cutoff documents;
  `data/identifier` is 500 records.
- **coherence-sever calibration → diagnosed, not fixed.** Added
  `--report-boundaries` so the collapse onto `semantic` is measurable. The
  threshold still needs setting against the real corpus.

## What's left

### Blocking the grid

1. **No grid loop.** Nothing iterates cells. `harness/harness.py` hardcodes its dataset
   paths ([`harness.py:52-61`](../../../harness/harness.py:52)).
   `harness/run_baselines.py --data <cell>` scores one cell, so the loop has something
   to call — but the loop itself, and the 5 missing cutter cells, are Michael's
   undelivered assignment.
2. **Fragment IDs leak record and position.** Cutters emit
   `prose_0000_frag_003`. That is exactly the pattern RUN_PLAN Step 1 requires a
   pre-flight assertion against. The harness masks IDs for Game L, but Game O and any
   run outside the harness do not. The masker and the refuse-to-send check are still
   unbuilt.
3. **coherence-sever threshold uncalibrated.** `--report-boundaries` now measures
   the collapse; nobody has run it against the real corpus and picked a threshold.
4. **Pool partition.** 500 documents into 71 fixed pools of 7, written to disk and
   never regenerated, plus the 25-pool and 180-document selections. Not started. Every
   linkage comparison is meaningless without it.
5. **Memon does not scale to the prose corpus as written.** It builds a dense
   pairwise similarity matrix: 16,524 fragments is 136M pairs and ~2.2 GB before
   `squareform` copies it. Fine per grid cell (a cell is 180 capped documents), but
   the whole-corpus Game L baseline needs blocking, sparsity, or per-pool scoring.
6. **The clause row is priced on a stale ratio.** `analysis/cost_grid.py` assumes
   clause yields 1.81× sentence fragments; measured on the shared spaCy base it is
   **1.31×**. Re-measure before that row is used to justify a budget cut.
7. Batch submitter, spend meter, zero-answer detector, malformed-partition rule,
   per-pool trivial floor, displacement metric — all unbuilt, all in RUN_PLAN §9.
