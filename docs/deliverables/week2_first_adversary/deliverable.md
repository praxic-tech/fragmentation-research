# Week 2 — First non-random adversaries (LLM + statistical)

**Assignment:** Build the first two adversaries that should rise above the random
floor, so we can print one comparison table — random vs. statistical vs. LLM —
for one content type (identifiers), both games.
- **Person A (Arafat):** LLM adversary via API. Model name a parameter, temperature 0.
- **Person B (Michael):** Memon-style n-gram / compression-distance baseline
  (Shanmugasundaram & Memon 2003) — the middle baseline; the paper's headline
  number is *LLM advantage over this*.

**Results (identifiers):** Game O τ — LLM 0.34 > NCD 0.14 > Memon 0.06 > random ~0.
Game L — LLM F1 0.22 *looks* high but sits on this setup's ~0.20 floor (pools of
5), i.e. at chance. **The finding:** the model was cheating off consecutive
fragment-ID numbers; once IDs were masked, linkage collapsed to chance. (Formal
write-up + the aligned 50-way rerun are in Week 3.)

## Files

| File | Author | Function |
|---|---|---|
| `run_llm_adversary.py` | Arafat (Person A) | LLM adversary, both games. Groq `llama-3.3-70b-versatile`, temp 0, model as a parameter. Masks fragment IDs → `item_N` before the model sees them. **Game L uses pools of 5** (superseded by the 50-way version in Week 3). |
| `score_llm.py` | Arafat | Scorer — reuses Person B's exact Kendall-τ and pairwise-F1 formulas so numbers line up. |
| `Record_Generator.py` | Arafat | Synthetic record generator (Faker; name/ssn/account/address, seed 42). **Produced the Week 1 dataset.** |
| `cutter.py` | Arafat | Cuts each record into one fragment per field, shuffles, writes `fragments.jsonl` + `answer_key.jsonl` (seed 123). **Produced the Week 1 dataset.** |
| `memon.py` | Michael (Person B) | Memon n-gram baseline: char n-gram model, boundary log-prob scoring, permutation search (Game O) + agglomerative clustering (Game L). |
| `records.jsonl` | (data) | The 50 un-fragmented source records (pre-cutter). |
| `fragments.jsonl`, `answer_key.jsonl` | (data) | Arafat's working copies — identical to the Week 1 dataset. |
| `llm_ordering_guesses.jsonl` | (output) | Arafat's Game O output (pools-of-5 run). |
| `llm_grouping_guesses.jsonl` | (output) | Arafat's Game L output (pools-of-5 run). |
| `PartA_writeup.txt` | Arafat | His status note: setup, results, the ID-leak finding, and the protocol-mismatch flag. |

## Run

```
python run_llm_adversary.py    # regenerate LLM guesses (needs API key)
python score_llm.py            # score guesses vs answer_key
python memon.py                # statistical baseline
```
Deps: openai, python-dotenv, scipy, numpy, faker.

## Known issues / what's missing

- **Protocol mismatch (the week's blocker):** Arafat's Game L is pools of 5
  (floor ~0.20); Michael clustered all 50 at once (floor ~0.02). The two linkage
  numbers can't share a table row until aligned — resolved in Week 3 by
  standardizing on the global 50-way setting.
- **Hardcoded Windows paths:** `Record_Generator.py` and `cutter.py` still write
  to `C:\Users\Arafat\Desktop\SCRMBL\outputs`. `run_llm_adversary.py` here also
  predates the relative-path fix. (Fixed in the Week 3 versions.)
- `apikey.env` is intentionally absent (kept out of the repo); the adversary reads
  `LLM_API_KEY` from it.
- No memon output file is included — `memon.py` prints results rather than saving guesses.
