# Week 3 — Unify the table + scale to prose

**Assignment (due Sunday):** produce one publishable identifier comparison table
(random / Memon / LLM, both games, aligned protocol, single run) **and** stage a
prose corpus that drops into the scorer with zero code changes.
- **Michael:** scale fix + unified harness — swap Game O ordering from exhaustive
  permutation search to greedy nearest-neighbor; merge random / Memon / LLM into
  one harness (one pass, one seed, one table).
- **Arafat:** align Game L to the global 50-way ("stolen database") protocol; write
  the fragment-ID leak up as a methods note.
- **Both:** relative paths. **Prose corpus:** ~25 clinical notes, variable
  fragment counts (not fixed at 4).

This folder = the two per-person deliverable zips, extracted. Each subfolder has
its own `MANIFEST.md` with a full file-by-file breakdown.

## `michael_week3/` — unified harness + prose corpus (Michael)

| File | Function |
|---|---|
| `harness.py` | Unified harness. Runs random / Memon-Greedy / Memon-MST / LLM in one pass, seed 42, 10,000 random runs, one table per content type. Entry point. |
| `loader.py` | JSONL loading, answer-key parsing, LLM-guess loading. |
| `orderers.py` | Ordering + grouping algorithms: random, greedy nearest-neighbor, MST; Memon n-gram/NCD scoring. |
| `scoring.py` | Kendall τ (Game O) + pairwise P/R/F1 (Game L). |
| `data/prose_fragments.jsonl`, `data/prose_answer_key.jsonl` | Prose corpus — 104 fragments, 25 synthetic clinical notes, 3–6 fragments each (variable, mean 4.2). |
| `data/fragments.jsonl`, `data/answer_key.jsonl` | Identifier dataset (added so the harness runs — was missing from the original zip). |
| `data/llm_ordering_guesses.jsonl`, `data/llm_grouping_guesses.jsonl` | Arafat's aligned 50-way LLM guesses (copied in so the harness LLM row populates). |
| `harness_run_output.txt` | His run output (both content types). |

Run: `python harness.py` (deps: numpy, scipy, tabulate).

## `arafat_week3/` — aligned LLM adversary + methods note (Arafat)

| File | Function |
|---|---|
| `run_llm_adversary.py` | LLM adversary. Game O per record; **Game L now one global 50-way call**. Model a parameter (`claude-sonnet-5`), Anthropic OpenAI-compat endpoint, IDs masked, relative paths, resumable. |
| `score_llm.py` | Standalone scorer (Kendall τ + pairwise F1). |
| `llm_ordering_guesses.jsonl`, `llm_grouping_guesses.jsonl` | Game O + aligned 50-way Game L output. |
| `methods_note_id_leak.txt` | The fragment-ID leak write-up (before/after, diagnosis, masking fix) — going in the paper. |
| `partA_update.txt` | His status update + aligned results table. |
| `fragments.jsonl`, `answer_key.jsonl` | Identifier dataset (added so `score_llm.py` runs — was missing from the original zip). |

Run: `python score_llm.py` (score existing guesses) or `python run_llm_adversary.py` (regenerate; needs API key).

## Aligned results (identifiers, Claude Sonnet)

```
Game            Random   Memon    NCD     LLM
O (tau)          ~0.00    0.06    0.14     0.21
L (F1)           ~0.02   0.0267  0.0223    0.017
```
Ordering: LLM wins. Linkage: LLM at the floor once IDs are masked — thesis holds.

## Known issues / what's missing

- **Scorer schema mismatch (open blocker):** `harness.py` (`loader.py:259`)
  expects grouping as `{"groups": {...}}`; Arafat's file is
  `{"pool_id": 0, "guessed_groups": [...]}`. The harness errors on it, so the
  LLM linkage cell shows `-` in the unified table even though `score_llm.py`
  reads the same file fine. One format has to move before the table is publishable.
- **Prose has no LLM arm:** nobody ran the adversary on the prose corpus, so the
  prose LLM row is empty. Prose is the contrast arm the paper lands on — this is
  the main remaining gap.
- `run_llm_adversary.py` hardcodes `group_size=4` in `repair_partition`; needs
  loosening before it runs on variable-length prose.
- `apikey.env` intentionally absent.
