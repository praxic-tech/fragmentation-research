# Mohammed Arafat — Week 3 deliverable (Part A, LLM adversary)

Assignment (posted 2026-07-12): re-run Game L grouping at the global 50-way level
(not pools of 5) to match Michael's clustering protocol; write the fragment-ID
leak up as a short methods note; relative paths.

Source: commits 63f60e7 / d67052c / dc8c313 (2026-07-18),
praxic-tech/fragmentation-research. Notes and guess files came separately.

## Contents

| File | What it is |
|---|---|
| `run_llm_adversary.py` | LLM adversary. Game O per record, Game L as ONE global 50-way call. Model is a parameter (`MODEL = "claude-sonnet-5"`), Anthropic OpenAI-compat endpoint. Masks fragment IDs to `item_N` before the model sees them. Resumable. |
| `score_llm.py` | Standalone scorer — Kendall tau (Game O) + pairwise P/R/F1 (Game L). Formulas copied from Michael's so numbers line up. |
| `llm_ordering_guesses.jsonl` | Game O output, 50 records. Was `llm_ordering_guesses (1).jsonl`. |
| `llm_grouping_guesses.jsonl` | Game L output — one `pool_id: 0` entry, 50 groups over all 200 fragments (the 50-way rerun). Was `llm_grouping_guesses (2).jsonl`. |
| `methods_note_id_leak.txt` | The ID-leak methods note (before/after, diagnosis, masking fix). |
| `partA_update.txt` | His written status update + results table. |

## Reported numbers (identifier data, Claude Sonnet)

```
Game            Random   Memon    NCD     LLM
O (tau)          ~0.00    0.06    0.14     0.21
L (F1)           ~0.02   0.0267  0.0223    0.017
```

## Run

```
python run_llm_adversary.py    # regenerate guesses (needs API key)
python score_llm.py            # score existing guesses
```
Deps: openai, python-dotenv, scipy.

## Not included / known gaps

- **`fragments.jsonl` and `answer_key.jsonl` are missing** — both scripts read
  them from the script directory. Neither was committed to the repo. Without
  them `score_llm.py` cannot run.
- **`apikey.env` intentionally excluded** (he kept it out of the repo, correctly).
  `run_llm_adversary.py` loads `LLM_API_KEY` from it.

## Verification notes

- 50-way alignment: done. The grouping file is a single global partition of all
  200 fragments into 50 groups, not 10 pools of 5.
- ID masking: present in `guess_order` / `guess_groups_global` — fragments are
  relabeled `item_N` and translated back after the model responds. The grouping
  output is scattered across ID space (no consecutive runs), which is the
  expected post-fix signature.
- Relative paths: done, `BASE = os.path.dirname(os.path.abspath(__file__))`.
- **Format mismatch with the unified harness:** this grouping file uses
  `{"pool_id": 0, "guessed_groups": [[...]]}`. Michael's `loader.py:259` requires
  a top-level `{"groups": {...}}` object and errors out on this file, so the LLM
  linkage row is blank in the unified table. `score_llm.py` reads it fine — the
  two scorers just disagree on schema.
- Minor: `run_llm_adversary.py` hardcodes `group_size=4` in `repair_partition`,
  which will need loosening before it runs on the variable-length prose corpus.
