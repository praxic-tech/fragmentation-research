# Where does an LLM defender actually cut?

**Finding: an LLM asked to fragment a document for defense reproduces linguistic
intuitions, not adversarial ones. It will not break a clause — even though
breaking clauses is precisely what defeats reassembly.**

20 documents, `claude-sonnet-5`, thinking disabled, $0.0956 total. Cut decisions
cached in `results/llm_cut_decisions.jsonl`; rebuild the cell for free with
`python datagen/llm_cutter.py --out-dir results/grid/llm_cut --offline`.

Method: the document is split into clause units and shown numbered; the model
returns the indices to cut before. It therefore has free choice of granularity
anywhere from clause-level to whole-document, and cannot alter the text.
Profiled with `analysis/cut_position_profile.py` against rule-based strategies
on the *same 20 documents*.

## 1. It lands slightly coarser than a sentence

| cell | frags/doc | words/frag (mean) | median |
|---|---|---|---|
| **llm-cut** | **31.9** | **24.7** | **20** |
| semantic × sentence | 39.2 | 20.0 | 18 |
| semantic × clause | 49.6 | 15.8 | 14 |
| semantic × token-window k=12 | 66.0 | 11.9 | 12 |
| coherence-sever × sentence | 36.5 | 21.5 | 19 |

Given the whole range to choose from, it settles just *coarser* than sentence
granularity — the most human-natural unit on the menu, and the second-least
fragmented option available.

## 2. It never breaks a clause — the headline result

Share of cuts landing on each boundary type:

| cell | paragraph | sentence | clause | **mid-clause** |
|---|---|---|---|---|
| **llm-cut** | 21.9% | 66.6% | 10.4% | **0.0%** |
| semantic × sentence | 19.3% | 80.7% | 0.0% | 0.0% |
| semantic × clause | 15.2% | 63.4% | 21.4% | 0.0% |
| semantic × token-window | 0.8% | 4.2% | 1.6% | **93.4%** |
| coherence-sever × sentence | 20.3% | 79.6% | 0.0% | 0.0% |

Zero mid-clause cuts, against token-window's 93.4%. The model was told to cut
"wherever reassembly would be hardest" and still respected every linguistic
unit. It is defending the way a careful editor would, not the way an adversary
would want to be attacked.

## 3. Which is why it leaves more signal exposed than the dumbest rule

Share of fragments opening with a discourse connective or a pronoun needing an
external antecedent — dangling links a reassembler can exploit:

| cell | connective | pronoun | **total exposed** |
|---|---|---|---|
| coherence-sever × sentence | 3.7% | 11.8% | **15.5%** |
| semantic × sentence | 3.4% | 11.0% | **14.4%** |
| semantic × clause | 2.7% | 10.7% | **13.4%** |
| **llm-cut** | 2.5% | 9.4% | **11.9%** |
| semantic × token-window | 0.4% | 1.5% | **1.9%** |

llm-cut is marginally better than the sentence strategies, and **6× worse than
structure-blind token-windowing**. A fixed 12-token window with no idea what a
sentence is beats a frontier model that was explicitly asked to make
reassembly hard.

## 4. It has no consistent policy

Share of available clause boundaries actually cut, per document:

| | value |
|---|---|
| mean | 0.65 |
| median | 0.58 |
| min | 0.26 (`prose_0011`, 24 of 92) |
| max | **1.00** (`prose_0001`, `prose_0003`, `prose_0004` — every boundary) |
| stdev | 0.23 |

Three of twenty documents were cut at *every single boundary* — maximum
fragmentation — while another was cut at 26%. Correlation between document
length and cut rate is **−0.07**, so this is not a length heuristic being
applied consistently. It is the same prompt producing opposite strategies.

That matters for the grid: llm-cut is not one condition, it is a mixture. Report
the cut-rate distribution alongside its score, or the cell's mean is an average
over two different defenses.

## 5. Which boundaries, specifically

Words the model cuts *before*, over 617 chosen cuts:

| opening word | share | | opening bigram | share |
|---|---|---|---|---|
| the | 14.1% | | **the patient** | **4.4%** |
| and | 5.8% | | at the | 1.8% |
| a | 5.3% | | there was | 1.1% |
| at | 3.6% | | she was | 1.0% |
| in | 3.2% | | and the | 0.8% |
| on | 2.4% | | due to | 0.8% |

Determiners and prepositions dominate — the openings of new sentences. The
`and` / `while` / `after` / `as` / `due to` entries are the 10.4% of cuts that
used a clause boundary rather than a sentence boundary: coordination and
subordination markers.

### It is NOT cutting at topic shifts

`prose_0013` reads as though the model cut along clinical narrative sections
(history → exam → imaging → biopsy → surgery → outcome), which would be a
serious defensive weakness, since those sections have a canonical order an
adversary could exploit. **That reading does not survive measurement.**

Lexical similarity between the two clause units either side of a boundary, cut
versus not cut:

| metric | at CUT boundaries | at NOT-CUT boundaries | Cohen's d |
|---|---|---|---|
| Jaccard, content words | 0.0294 | 0.0311 | **−0.026** |
| TF-IDF cosine | 0.0516 | 0.0509 | **+0.010** |

Both null, in opposite directions. The second metric is the one validated to
carry signal on this corpus (d = +0.458 separating same-record from
different-record pairs), so this is not an instrument failure.

**The boundaries the model chose to cut are lexically indistinguishable from the
ones it skipped.** Combined with the 0.26–1.00 cut-rate spread, the picture is a
model that reliably respects sentence structure but applies no detectable
semantic criterion for *which* sentence boundaries to cut. The `prose_0013`
section structure is what a case report looks like when you cut it at sentence
boundaries at all — not evidence of section-aware cutting.

## 6. Position

| cell | 0% | 10% | 20% | 30% | 40% | 50% | 60% | 70% | 80% | 90% |
|---|---|---|---|---|---|---|---|---|---|---|
| llm-cut | 7.9 | 10.0 | 10.5 | 10.5 | 9.2 | 9.7 | 9.3 | 10.7 | **12.3** | 10.0 |
| semantic × sentence | 9.0 | 10.3 | 11.5 | 10.7 | 9.7 | 9.3 | 9.8 | 9.5 | 10.7 | 9.4 |
| semantic × token-window | 9.6 | 10.2 | 10.1 | 10.1 | 9.9 | 10.2 | 10.0 | 10.0 | 9.8 | 10.1 |

Mildly non-flat where the rule-based strategies are flat by construction: it
cuts less at the opening and most in the final fifth. Weak, and 20 documents is
not enough to lean on it — worth rechecking if the cell is run at full scale.

## Cost

$0.0956 for 20 documents with thinking disabled — **$0.0053/doc**, projecting to
**$2.66 interactive / $1.33 batched** for all 500. RUN_PLAN §4 prices the
llm-cut ordering cell at $3.65, so it is comfortably inside budget.

**Adaptive thinking must stay off for this task.** Three initial calls at
`max_tokens=2000` with default (adaptive) thinking returned *empty answers* —
the entire output budget went to reasoning, ~$0.07 billed for nothing. That
reproduces the RUN_PLAN §2 observation about an ordering call hitting its cap
with zero answer tokens. `llm_cutter.py` now raises `ZeroAnswerError` on this
rather than logging it as a parse failure, and `--thinking off` is the default.

## Fidelity — the model invented nothing

Returning indices rather than text makes corruption structurally hard; this
verifies it rather than asserting it (`analysis/verify_fragments.py`, 20 docs):

| cell | hallucinated tokens | dropped | reconstruction |
|---|---|---|---|
| **llm-cut** | **0** | 0.21% | 13/20 exact |
| semantic × sentence | 0 | 0.21% | 13/20 |
| semantic × clause | 0 | 0.21% | 13/20 |
| semantic × token-window | 0 | **0.00%** | **20/20** |
| coherence-sever | 0 | 0.21% | 13/20 |

Zero invented tokens everywhere. llm-cut's dropped figure is *identical* to the
rule-based cells, which is the point — it comes from the shared
`MIN_SENT_CHARS` filter upstream, not from the model. The model's own choices
cost nothing in fidelity.

## Next: v2-adversarial, and why the prompt alone is not the fix

`--prompt v2-adversarial` is written and ready to run. It states the attacker's
method explicitly ("a fragment that begins a new sentence, or starts with a
connective or a pronoun whose referent sits elsewhere, tells them where it
belongs") and removes the implicit tidiness constraint ("fragments do not need
to be grammatical, readable, or self-contained").

**But a prompt change cannot produce mid-clause cuts under `--units clause`.**
The model is only offered clause boundaries; cutting inside one is not an option
it can express. `--units word` offers every whitespace token as a candidate,
which is what makes the 0.0% mid-clause figure a real measurement of judgement
rather than a property of the menu. It costs roughly 2× input, since every token
carries an index.

Recommended sequence, each on the same 20 documents so they are comparable:

```bash
python datagen/llm_cutter.py --out-dir results/grid/llm_cut_v2 --limit 20 --prompt v2-adversarial --budget 0.20
python datagen/llm_cutter.py --out-dir results/grid/llm_cut_w --limit 20 --prompt v2-adversarial --units word --budget 0.40
python analysis/cut_position_profile.py --cell results/grid/llm_cut --compare results/grid/llm_cut_v2 results/grid/llm_cut_w
python analysis/verify_fragments.py --cell results/grid/llm_cut_v2 results/grid/llm_cut_w
```

The v1 prompt is kept, not replaced — deleting it would make everything above
unreproducible. Cached decisions are keyed on **(document, model, prompt,
unit-type)**, so a new prompt or provider can never silently replay v1's
answers. Earlier cache rows without those fields are read as v1 +
`claude-sonnet-5` + clause, which is what they are.

### On running this with a free-tier key

`--provider groq` switches base URL and default model
(`llama-3.3-70b-versatile`); the key is read from `GROQ_API_KEY`, falling back to
`LLM_API_KEY` / `API_KEY`. Anthropic's `thinking` parameter is skipped
automatically off that host, since sending it returns a 400.

One thing to record if you do: the defender then becomes a **different model
from the adversary**, and the numbers are not comparable to the Sonnet baseline
above. That is a legitimate configuration — arguably a more realistic one, since
a defender and an attacker need not share a model — but it is a different
experiment and the paper has to say which model cut the documents.

## Caveats

- **20 documents**, non-random (the first 20 by record_id). Enough for the
  boundary-type result, which is categorical and unanimous; not enough for the
  position result.
- Cut points are restricted to clause boundaries, so "0.0% mid-clause" is partly
  by construction — the model *could not* cut mid-clause. What the result
  actually shows is that it did not even push to the finest granularity it was
  offered: only 10.4% of its cuts used a clause boundary that was not also a
  sentence or paragraph boundary.
- Thinking disabled. Whether adaptive thinking picks different cut points is
  unmeasured and would cost roughly 7× more to find out.
