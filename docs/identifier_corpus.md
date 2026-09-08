# Identifier corpus — 500 records

**Status: live.** `data/identifier/` is this corpus. Scaled from 50 to 500
records per RUN_PLAN §6 (500 × 4 fields = 2,000 fragments, 71 pools of 7) and
promoted on 2026-08-10; the 50-record set is in
`archive/superseded_corpora/identifier50_*`.

## Built with

```bash
python datagen/record_generator.py -n 500
python datagen/cutter.py
```

Both scripts previously hardcoded `n=50` and the output folder; they now take
`-n/--count/--out` and `--data-dir`. Seeds are unchanged (generator 42, shuffle 123).

## It extends the old corpus, it does not replace it

Records are generated in index order from a seeded Faker, and fragment IDs are
assigned in (record index, field index) order. So the 500-record corpus contains
the 50-record corpus as an exact prefix. Verified:

- all 200 original `fragment_id`s present in the new corpus — **yes**
- identical `(record_id, text)` for all 200 — **yes**
- identical answer-key rows for all 200 — **yes**

Nothing computed on the 50-record corpus is invalidated. What *does* change is
the linkage task: 50-way becomes 500-way, so the existing
`results/llm_*_guesses.jsonl` (50 groups over 200 fragments) are superseded and
the adversary needs re-running at 500.

## Why it matters: the control gets 10× sharper

The identifier arm's job is to show linkage stays **at chance**. At 50 records
the noise band was wide enough to hide a real effect.

| | records | fragments | random Game L F1 | 2σ ceiling | trivial one-bucket F1 |
|---|---|---|---|---|---|
| superseded 50-record set | 50 | 200 | 0.0148 ± 0.0065 | 0.0278 | 0.0297 |
| **`data/identifier`** | **500** | **2,000** | **0.0015 ± 0.0008** | **0.0030** | **0.0030** |

Random Game O τ also tightens (±0.0670 → ±0.0212). 200 Monte Carlo runs, seed 42.

The fixed-Memon figure to beat is 0.0171 at 50 records (`docs/corpus_build.md`);
that number is pool-size dependent and **must be recomputed at 500** before it
goes in any table — see RUN_PLAN §4. Measured at 500 records, the fixed `B_stat`
returns F1 0.0027 against a random floor of 0.0015, with precision 0.0013 —
*below* the floor — but recall 0.474. Precision at chance is the control working;
the high recall means it is still forming large clusters, which is worth a look
before this is quoted as a clean at-chance result.

## Known wrinkle

Two of the 500 records share a name (499/500 unique names; SSN, account and
address are all 500/500 unique). Two identical-text fragments in different
records are unlinkable by any adversary, so this slightly lowers the achievable
ceiling rather than leaking signal. Harmless at 1/500 — noted so it isn't
rediscovered as a bug.
