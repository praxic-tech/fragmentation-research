# Prose corpus — build, provenance, and the findings that came out of it

**Status: live.** `data/prose/` is this corpus. It replaced the 25-document
hand-written synthetic set on 2026-08-10; the old one is in
`archive/superseded_corpora/synthetic25_*`.

| file | contents |
|---|---|
| `prose_raw.jsonl` | `{record_id, text}` — full untouched body, paragraph breaks kept as `\n`. **Source of truth.** Every cut strategy reads this. |
| `prose_fragments.jsonl` | `{record_id, fragment_id, text}` — the `semantic × sentence` cut of `prose_raw`. |
| `prose_answer_key.jsonl` | `{record_id, source_pmcid, order[]}` |
| `prose_documents.jsonl` | as pulled, with `source_pmcid` |
| `prose_meta.jsonl` | per-document length metadata for the length covariate |

500 documents, 16,524 fragments, 315k words. `prose_fragments.jsonl` is
reproducible from `prose_raw.jsonl`:

```bash
python datagen/prose_cutter.py --out-dir data/prose --strategy semantic --granularity sentence
```

## Why post-cutoff

These are **real** case reports published **February 2026 or later** — after
Sonnet 5's January 2026 cutoff — so a high LLM score cannot be explained by
memorisation. That makes the prose arm a genuine reconstruction result rather
than a possible recall result.

**Gate 2a: PASS** (re-verified 2026-08-10 against NCBI). 500/500 post-cutoff,
0 pre-cutoff, 0 unresolved dates.

```bash
python datagen/verify_postcutoff.py --data data/prose
```

An earlier `flagged_precutoff.txt` listing 68 documents was a prose_v3 artifact:
those PMCIDs had no month in NCBI's metadata at pull time and were correctly
treated as suspect. All 68 now resolve as post-cutoff. The file has been deleted
to stop it being read as a live warning.

## Build pipeline

`datagen/pull_prose.py` provides the networking and filtering layer (PubMed
ESearch → PMID→PMCID → commercial-use licence check → BioC full text).
`datagen/pull_prose_v4.py` is the current entry point and imports from it.

Three bugs in the original starter script made it return **zero** documents:
`"open access"[filter]` is not a valid PubMed filter; the BioC endpoint needs
the full `PMC…` id, not the bare number; and the licence check used a prefix
test, so `"CC BY-NC".startswith("CC BY")` admitted every non-commercial licence.

Extraction also tracks the enclosing **heading** and keeps only paragraphs under
a case-narrative heading, because PMC tags whole case reports as `INTRO` and
`section_type` cannot separate framing from narrative. That yields clinical
narrative rather than journal-article framing. `--all-sections` restores the
broad behaviour.

## Findings

### 1. The synthetic corpus had an inverted lexical signal

Same-record sentence pairs were *less* lexically similar than different-record
pairs (Cohen's d, same vs different record):

| metric | synthetic prose | real PMC prose |
|---|---|---|
| word-bigram | **−0.370** | +0.217 |
| char-4gram | **−0.275** | +0.359 |
| tfidf-cosine | **−0.077** | **+0.458** |

Within a synthetic note, sentences deliberately covered different things
(history → exam → imaging → diagnosis) and shared no vocabulary; across notes,
every record opened with the same template. Lexical similarity therefore grouped
by **section type**, not by record.

No similarity tuning can fix a signal pointing the wrong way. This is the
independent reason the real corpus matters: the synthetic data did not merely
make Memon look weak, it made linkage structurally impossible and misstated the
LLM-vs-Memon gap. **Deserves its own subsection in the paper** — evaluating
fragmentation defenses on synthetic corpora can invert the signal the attack
depends on.

### 2. Memon's published Game L is degenerate

On every corpus it collapsed nearly everything into one cluster and padded the
group count with singletons, so its F1 was blob arithmetic, not linkage:

| corpus | largest cluster | Memon F1 | trivial "one big cluster" F1 |
|---|---|---|---|
| synthetic prose (25 rec) | 53 / 104 (51%) | 0.0459 | **0.0615** |
| prose_v2 (96 rec) | 1039 / 1148 (91%) | 0.0190 | **0.0189** |
| prose_v3 (500 rec) | 5401 / 5936 (91%) | 0.0037 | **0.0037** |
| identifiers (50 rec) | 151 / 200 (76%) | 0.0298 | 0.0297 |

It **lost to doing nothing** on synthetic and **exactly equalled it** on the
real corpora. Cause: `greedy_grouping` is single-linkage (merge on ANY similar
pair), chaining through a similarity matrix that is 83.5% exact zeros.
`mst_grouping` fails equivalently — cutting the weakest MST edges snips off
leaf singletons instead of splitting the blob.

**The fix** (TF-IDF cosine + average linkage + deterministic tie-break jitter)
is in `adversaries/memon_linkage.py`:

| corpus | trivial | legacy Memon | **fixed** | vs trivial |
|---|---|---|---|---|
| prose_v2 (96 rec) | 0.0189 | 0.0190 | **0.0539** | **2.9×** |
| prose_v3 (500 rec) | 0.0037 | 0.0037 | **0.0222** | **6.0×** |
| identifiers (50 rec) | — | 0.0298 | **0.0171** | at floor ✓ |
| synthetic prose | 0.0615 | 0.0459 | 0.0231 | fails (inverted signal) |

Both guardrails hold: beats trivial on real prose with the margin *growing* with
scale, and identifiers stay at chance so the two-regime thesis is safe.

**Now the only grouping on the live path.** `harness.eval_memon` always uses the
fixed variant for Game L; `method` selects the Game O ordering heuristic only.
Both Memon rows therefore report identical Game L figures, because greedy and
MST are two *ordering* heuristics sharing one grouping algorithm. The degenerate
implementations are reachable solely via `--grouping legacy-greedy|legacy-mst`,
for reproducing tables the team saw before the fix.

The degeneracy finding still earns an appendix — it is a methodological
contribution, not a live threat to the headline metric.

### 3. The cutter had two tokenizers, and the granularity axis inverted

Found and fixed 2026-08-10. `prose_cutter._split_sentences` used a regex while
`_split_clauses` used spaCy, so the sentence→clause comparison measured "clause
splitting" *plus* "switched tokenizer". Measured consequences: the regex
disagreed with the corpus's own split on **342 of 500 documents**, and **50 of
500 documents produced fewer clause fragments than sentence fragments** — an
axis meant to run coarse→fine running backwards on 10% of the corpus.

Both cutters now share one spaCy base (`prose_cutter._split_sentences`, imported
by `coherence_sever`), with clauses subdividing those same sentence units.
Verified: `semantic × sentence` reproduces `prose_fragments.jsonl` exactly.

Measured granularity ratios on the promoted corpus:

| granularity | fragments | mean/doc | ratio |
|---|---|---|---|
| sentence | 16,524 | 33.0 | 1.00 |
| clause | ~21,200 | ~42 | **1.31** |
| token-window k=12 | ~26,900 | ~54 | 1.66 |

Clause at 1.31× is a **much weaker manipulation than the 1.8× the cost model
assumes** — see the note in RUN_PLAN §6.

### 4. ID masking was dropping fragments (found by scaling the corpus)

`harness.mask_fragment_ids` drew each masked label as
`random.randint(100000, 999999)` and stored `id_map[label] = original`. That is
a birthday problem against a 900,000-value space:

| corpus | fragments | expected collisions | fragments silently dropped |
|---|---|---|---|
| identifier (50 rec) | 200 | 0.02 | 0 |
| identifier (500 rec) | 2,000 | 2.2 | ~2 |
| **prose (500 docs)** | **16,524** | **152** | **128 measured** |

Each collision overwrote an `id_map` entry, and `unmask_groups` filters on
`if mid in id_map` — so those fragments vanished from **every Game L score**,
silently. It was also nondeterministic: separate `eval_memon` calls consumed
different RNG state, drew different collisions, and produced different linkage
numbers for what is now provably the same algorithm on the same input. That
discrepancy is what exposed it.

Invisible at 200 fragments, which is why it survived three weeks of results.
**Every Game L figure computed on a corpus larger than a few thousand fragments,
before 2026-08-10, is slightly wrong.**

Fixed: labels are now a shuffled permutation of exactly `len(fragments)`
distinct values — collision-free by construction, with an assertion. Verified
zero loss and exact round-trip on both corpora; label-index vs true-position
correlation is +0.001 (prose), so the shuffle still hides order.

## Fidelity check

`analysis/verify_fragments.py` proves a cell only ever *partitions* its source —
no invented words, no paraphrase, no reordering. Exits non-zero on failure, so
it can gate a pipeline. Run it on any cell before scoring it:

```bash
python analysis/verify_fragments.py --cell data/prose results/grid/llm_cut
```

Live corpus, 500 documents:

| check | result |
|---|---|
| **hallucination** | **PASS — 0 invented tokens** |
| dropped content | 0.12% — 399 of 335,742 tokens, in 111 docs |
| reconstruction | 384/500 exact |
| structure | PASS — key and fragments agree exactly |

**The 0.12% is the `MIN_SENT_CHARS = 15` filter, not a bug**, and it is inherited
from the corpus build (`pull_prose_v4.split_sentences` applies the same rule).
What it discards is figure-citation debris: spaCy breaks `(Fig. 1A-D).` after
`Fig.`, orphaning `1A-D).`, which then falls under the length floor. Sampled
examples: `'1A-D).'`, `'8).'`, `'[VEGFR1]).'`, `'2D and E).'`.

Two consequences to be aware of:

- `prose_raw.jsonl` legitimately contains slightly more text than
  `prose_fragments.jsonl`. Any cell cut from raw inherits the same 0.12%, so
  cells remain comparable to each other and to the corpus — verified identical
  (0.21% on the same 20-document sample) across sentence, clause,
  coherence-sever and llm-cut.
- **`token-window` drops nothing** (0.00%), because it does not route through
  the sentence splitter. It is the one granularity whose fragments reconstruct
  its source exactly, 20/20. Worth stating in the paper rather than leaving as
  an unexplained asymmetry between granularities.

At least one dropped unit is real narrative rather than debris (`'Routine'` in
`prose_0004`), so the filter is not perfectly targeted. 0.12% is small enough
not to threaten any result, but it should be disclosed rather than discovered.

## Known wrinkles

- **Fragment IDs leak.** `prose_0000_frag_000` encodes record and position. The
  harness masks IDs for Game L, but Game O and any run outside the harness do
  not. The masker and the refuse-to-send pre-flight check (RUN_PLAN Step 1) are
  still unbuilt.
- **`prose_meta.jsonl` was refreshed** when the corpus was regenerated uncapped;
  `n_fragments` matches the live corpus and `truncated` is now false everywhere.
  The original pull capped 5 documents at 100 fragments.
- **Closed-world for prose linkage is enforced by the harness, not the data.**
  These are real published papers; an adversary with a search engine could look
  up which sentences co-occur. Post-cutoff does not help there. State it as an
  assumption of the setup (RUN_PLAN §8 item 1).
