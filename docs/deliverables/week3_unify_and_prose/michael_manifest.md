# Michael Anyaegbunam — Week 3 deliverable

Assignment (posted 2026-07-12): swap Game O ordering from exhaustive permutation
search to greedy nearest-neighbor; merge random / Memon / LLM into one harness
(one pass, one seed, one table); relative paths. Prose corpus was "whoever has
bandwidth" — he took it.

Source: commit f9c496f "Add files via upload" (2026-07-19), praxic-tech/fragmentation-research.
Prose corpus + run output came separately (not in the repo).

## Contents

| File | What it is |
|---|---|
| `harness.py` | Unified harness. Runs random / Memon-Greedy / Memon-MST / LLM in one pass, one seed (42), 10,000 random runs, prints one table per content type. Entry point. |
| `loader.py` | JSONL loading, answer-key parsing, LLM-guess loading. |
| `orderers.py` | Ordering + grouping algorithms: random, greedy nearest-neighbor, MST. Memon n-gram/NCD scoring folded in here. |
| `scoring.py` | Kendall tau (Game O) and pairwise P/R/F1 (Game L). |
| `data/prose_fragments.jsonl` | Prose corpus — 104 fragments, 25 synthetic clinical notes, sentence-cut. |
| `data/prose_answer_key.jsonl` | Prose answer key, `{record_id, order[]}` format. |
| `harness_run_output.txt` | His run output (both content types). Was `output.txt`. |

## Run

```
python harness.py
```
Deps: numpy, scipy, tabulate. Expects data under `./data/`.

## Not included / known gaps

- **`data/fragments.jsonl` and `data/answer_key.jsonl` are missing.** The
  identifier dataset was never committed to the repo and wasn't handed over.
  Without it only the prose half of the harness will run.
- Week 2 files (`memon.py`, `baseline-loader.py`, `baseline-run2.py`, commit
  df91eb5) are deliberately excluded — `harness.py` imports only
  loader/orderers/scoring, and `orderers.py` supersedes them.
- No LLM guesses for prose exist (`prose_llm_*.jsonl`); nobody ran the adversary
  on the prose corpus, so the LLM row of the prose table is empty.

## Verification notes

- Greedy nearest-neighbor swap: done. Variable fragment counts handled (prose
  ranges 3–6 per record, mean 4.2) — nothing hardcoded to 4.
- Relative paths: done, no `C:\Users\...` remaining.
- Single-run unified table: done, seed 42 / 10,000 runs printed in the footer.
- **Open bug:** the harness cannot read Arafat's grouping file. `loader.py:259`
  requires a top-level `"groups"` key; Arafat's file emits
  `{"pool_id": 0, "guessed_groups": [...]}`. This is why the identifier table
  shows `LLM ... L: F1 = -` instead of the 0.017 he reported. One of the two
  formats has to move before the table is publishable.
