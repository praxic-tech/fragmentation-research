# Cross-model sandbox: Game J on other models

> **POST-HOC EXPLORATORY.** This is a cross-model robustness check added after
> the prespecified study was run and frozen. It is not part of the
> prespecified design, it does not replace or revise any Sonnet result, and
> anything it produces must carry the label "post-hoc exploratory" wherever it
> is reported.

The question: do the paper's Game J results (one-shot reconstruction of mixed,
order-stripped fragments) hold when the attacker is a different model, in
particular a free hosted model or one small enough to run on a single consumer
GPU? The study used one generative model (`claude-sonnet-5`); this sandbox
tests others on the **byte-identical prompts** and scores them with the
**unchanged scorer**.

## Rules for any agent working here

1. **Write only inside `experiments/cross_model_sandbox/`.** Everything else in
   the repository is read-only: the manuscript, primary results, raw responses,
   frozen prompts, decision log, all of it. Do not write, rename, delete,
   format or regenerate anything outside this directory.
2. **Never modify anything under `frozen/`.** Run `python tools/verify_frozen.py`
   at the start and end of every session. It must pass.
3. **Ask the user before anything that calls a model**, every time: hosted or
   local, free or paid. State the model, the provider or runtime, how many
   requests, and the expected time and cost. Free tiers only, unless the user
   explicitly approves spending money.
4. **Never print, log or commit an API key or `.env` contents.** Keys go in a
   `.env` file in this directory. It is gitignored.
5. **Preregister before the first call to a model.** See "Before any model is
   called" below. Commit the preregistration, then run.
6. The existing Sonnet results and the frozen primary experiments are never
   altered, re-run or re-scored differently. They are the reference.
7. **Do not edit the paper.** Integration into the manuscript is done later by
   the authors, from the main repository.
8. Attacker names follow `frozen/docs/adversaries.md` exactly. Never "Memon"
   alone (it is "Memon-inspired"), never "pre-LLM state of the art".

## Layout

| path | status | what goes there |
|---|---|---|
| `frozen/` | **read-only copies** | Everything copied from the repo, at the same relative path it has there. The copied code finds its root as the parent of its own directory, so it resolves every path inside `frozen/` and runs unchanged. Checksums in `frozen/SHA256SUMS`. |
| `tools/` | modifiable | `verify_frozen.py` (integrity check) and `selfcheck_sonnet.py` (end-to-end regression test). |
| `work/` | modifiable | New code: model callers, wrappers, analysis. |
| `models/<model_slug>/MODEL.json` | modifiable | Model config and provenance, one directory per model (fields below). |
| `PREREGISTRATION.md` | write once per model, before its first call | The fixed protocol for each model. |
| `raw/<model_slug>/` | append-only | Raw provider/runtime responses, one `<spec_tag>.results.jsonl` per wave, in the row format below. Never edited after writing. |
| `results/<model_slug>/<game>/` | generated | Scored rows and `REPORT.txt` from the frozen scorer. |
| `results/SUMMARY.md` | generated | Cross-model comparison table against the Sonnet reference. |
| `logs/` | generated | Run logs. |
| `COPIED_FILES.json` | read-only | Exactly what was copied, grouped by purpose. |

## What is in `frozen/`

`COPIED_FILES.json` lists every file. In short:

- **Request specs**, `frozen/runs/*.json`: the rendered prompts exactly as Sonnet
  received them, plus a `sidecar` per request holding the alias map (prompt
  label to fragment id) and the shown order. The sidecar is the only way back
  from a model's labels to a score. **Send `request["prompt"]` verbatim. Never
  rebuild prompts.**

  | spec | requests | prompt chars, median / max | what it is |
  |---|---|---|---|
  | `final_headlineJ.json` | 46 | 33,272 / 75,956 | headline: 46 pools of 7 full-length documents |
  | `gradient_J.json` | 60 | 6,336 / 9,334 | granularity gradient, 2/3/4-word fragments |
  | `single_token_edge_J.json` | 40 | 8,574 / 12,997 | sentence vs single-token fragments |
  | `final_identifierJ.json` | 20 | 1,314 / 1,330 | identifier records |
  | `final_gridJ_w1..w4.json` | 216 | about 27,000 / 33,065 | the 9-cell strategy × granularity grid |

- **Corpus and pools**: `frozen/data/prose/`, `frozen/data/pools/`, and the
  per-cell fragment and answer-key files under `frozen/results/{grid_A,
  identifier_J, gradient, single_token_edge}/`. The scorer rebuilds ground
  truth from these.
- **Code**: prompt/parse/repair/score modules (`frozen/adversaries/`,
  `frozen/harness/`, `frozen/analysis/cost_model_v2.py`) and four tests.
  Reference only, do not run as-is: `frozen/analysis/game_j_adjacency.py`,
  `gradient_*.py`, `single_token_edge_analysis.py`,
  `frozen/results/final_analysis/scripts/build_master.py`, `frozen/runs/final_run_*.py`.
  These write into `frozen/results/` or call the Anthropic Batches API. To
  reuse one, copy it into `work/` and repoint its outputs.
- **Sonnet reference**: scored rows and reports (`frozen/results/final/*J/`),
  the paper's per-unit tables and key numbers (`frozen/results/final_analysis/`),
  and Sonnet's raw provider rows (`frozen/results/batches/`). The raw rows are
  gitignored in the main repo; this is the only committed copy.
- **Protocol**: `frozen/docs/RUN_DECISIONS.md` (the decision log; D4, D6, D11
  to D14 matter most here), `adversaries.md`, `results_plan.md`, `RUN_PLAN.md`,
  `corpus_build.md`, `paper_section3.md` (the game definitions),
  `single_token_edge_design.md`.

## How a new model's answers get scored

Use the frozen scoring path. Do not write a second scorer. Write raw rows in
the same format the Anthropic batch path produced, and the frozen scorer
treats them exactly as it treated Sonnet's.

**1. One row per request**, appended to `raw/<model_slug>/<spec_tag>.results.jsonl`:

```json
{"custom_id": "prose__J__pool-001", "cell": "prose", "game": "J", "unit": "pool-001",
 "fetched_at": "2026-11-12T10:00:00+00:00", "result_type": "succeeded",
 "usage": {"input_tokens": 11207, "output_tokens": 5894},
 "stop_reason": "end_turn", "text": "<the model's final visible answer>"}
```

- `custom_id` comes from `batch_submit.make_custom_id(cell, game, unit)`, using
  the request's own `cell`, `game` and `unit`. It is the key of the spec's
  `sidecar`. It slugs ids (`pool_001` becomes `pool-001`), so always call it
  and never build the string by hand.
- `stop_reason`: map an OpenAI-style `finish_reason` of `"stop"` to
  `"end_turn"`, and `"length"` to `"max_tokens"`.
- `text` is the final answer content only. For reasoning models, the reasoning
  trace goes in an extra field (e.g. `"reasoning"`), never in `text`.
- A transport failure (timeout, 429, 5xx, empty body) is
  `"result_type": "errored"` with an `"error"` string. Under D4 it is resent
  once, unchanged, in a `-rs1` wave.
- `usage` must be the token counts the provider or runtime reports, not an
  estimate.

**2. Resend, repair, score** with the frozen functions, in the same order as
`frozen/runs/final_run_steps123.py`. Run them from your own wrapper in `work/`:

```python
batch_game.build_resubmit_spec(spec, [base_file], tag + "-rs1")   # transport holes, once
batch_game.build_repair_spec([(spec, files)], 1, 1, tag + "-r1")  # ONE repair round
batch_game.score([(spec, files), (repair_spec, repair_files)], out_root)
```

**3. The output budget.** The frozen code defines a non-completion (D6) as a
call that used `MODEL_MAX_OUTPUT` = 128,000 tokens. Other models have other
ceilings. Set the preregistered per-model budget from your wrapper:
`batch_game.MODEL_MAX_OUTPUT = budget` (the functions read the module global
at call time). Never edit the frozen file. A call that hits the budget is then
a resource-bounded non-completion, recorded and never re-asked, exactly as for
Sonnet.

**4. Before trusting any of it**, run `python tools/selfcheck_sonnet.py`. It
re-scores Sonnet's raw headline rows through this exact path and must
reproduce the paper (F1_J 0.7225, F1_L 0.8817, q 0.8206). It passed when the
sandbox was created.

## Input sizes, and what a model needs to handle them

- The largest prompt is 75,956 characters (headline J). Sonnet counted the
  headline prompts at **median 11,940 and max 26,851 input tokens**. Count
  with each model's own tokenizer and record the numbers. They will differ.
- **The context window must hold the prompt plus the output budget.** That
  means at least about 32k for non-reasoning models with a short answer, and
  more for reasoning models (27k in, plus the reasoning budget). 128k is not
  needed for the input. The old "128k" was Sonnet's output ceiling.
- **Local runtimes truncate silently.** Ollama, llama.cpp and LM Studio default
  to small contexts and drop the start of the prompt without an error. Set the
  context length explicitly. For every call, assert that the reported prompt
  tokens match the model tokenizer's count of the prompt. A truncated prompt
  is a broken run, not a weak result.
- The answer itself is short: a JSON list of groups, at most about 2k visible
  tokens. Sonnet's large outputs were almost all reasoning.

## Before any model is called

Write the entry for that model in `PREREGISTRATION.md`, commit it, and only
then run. Each entry fixes:

- model id, provider or runtime, and exact revision (an OpenRouter model plus
  a pinned upstream provider, or a local weights file with its SHA-256 and
  quantization);
- the model's **training cutoff and its source**. The prose corpus is real
  case reports published **February 2026 or later** (`frozen/docs/corpus_build.md`).
  A model whose cutoff is after February 2026 may have seen the documents. Its
  prose results are then possibly recall, not reconstruction, and must be
  reported as such or excluded;
- context length, output budget, temperature and other sampling parameters
  (Sonnet ran at provider defaults with no temperature parameter), and any
  reasoning or thinking setting;
- which specs it runs, in what order;
- the D4/D6 rules as applied here: one unchanged resend of transport failures,
  one repair round, a call that hits the output budget is a non-completion,
  never re-asked;
- what will be compared, and that the comparison is post-hoc exploratory.

`models/<model_slug>/MODEL.json` records the same facts plus what actually
happened: runtime and version, GPU, dates run, request counts, failures.

## Suggested order

1. `final_headlineJ` (46 requests). This is the headline number and the one
   that matters. At 46 calls it fits in a day even on a 50-requests-a-day
   free tier.
2. `gradient_J` and `single_token_edge_J` (100 requests, small prompts).
3. `final_identifierJ` (20, tiny), then the grid (216) if still useful.

Report completion and non-completion rates beside every score. A model that
cannot produce a valid answer is a finding about that model. Never record it
as a zero, and never silently drop it.

## Dependencies outside this directory

None on files. The sandbox needs only Python packages: `numpy`, `scipy`,
`openai` (an OpenAI-compatible client works for OpenRouter and for local
servers) and `python-dotenv`. `anthropic` is imported only inside
`batch_submit.make_client`, which this sandbox does not use. Versions used by
the study are in `frozen/requirements.txt`. `frozen/adversaries/llm_adversary.py`'s
`make_client` reads `frozen/.env` and targets Anthropic, so write your own
client in `work/` instead.

## Provenance

Created from commit `d842eec`, tag `pre-cross-model-experiments`, on
2026-11-11. Every file in `frozen/` was verified byte-identical to its original
at copy time.
