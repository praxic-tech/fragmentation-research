# Sonnet-dependence sweep on headline Game J: final table

**Post hoc exploratory.** PREREGISTRATION.md 2026-11-13 and its amendments (below). Primary verdict = the preregistered rule applied as written (a unit without an answer after repair, or a unit's recorded `repair.policy_share` > 0.25, refuses the cell). When REFUSED, the means shown are the secondary answered-units-only figures, in brackets. Sonnet and Gemma are re-scored read-only with the same wrapper; frozen/ is byte-identical to its snapshot.

| model | lab | where it ran | max output | verdict (46 pools) | F1_J / F1_L / q, 46 pools | F1_J / F1_L / q, 41 pools | completion | D6 | transport errors | content-filter blocks | invalid after repair | mean policy_share | units over cap | tokens | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Claude Sonnet 5 (reference) | Anthropic | Anthropic Message Batches API (frozen primary run) | 128,000 | PASS | 0.7225 / 0.8817 / 0.8206 | 0.7218 / 0.8825 / 0.8192 | 46/46 | 0 | 6 req (6 attempts); not completed 0 | 0 | 0/46 | 0.0000 | 0 | in 656,644 / out 2,405,026 | – (frozen primary run) |
| gpt-5.6-sol | OpenAI | Azure OpenAI, Responses API, service_tier flex, reasoning effort max; DefaultV2 guardrail, the 2 blocked units resent under Default | 128,000 | PASS | 0.8464 / 0.9507 / 0.8907 | 0.8455 / 0.9523 / 0.8882 | 46/46 | 0 | 2 req (2 attempts); not completed 0 | 2 (pool_005, pool_037; completion side, DefaultV2) -> resent under Default: 2/2 answered | 0/46 | 0.0000 | 0 | in 392,457 / out 2,457,960 (reasoning 2,369,790) | $25.36 |
| gpt-4.1 | OpenAI | Azure OpenAI, Responses API, tier default; DefaultV2 guardrail | 32,768 | REFUSED: 0 without an answer, 44 over the cap | (0.2363 / 0.3320 / 0.6994) *secondary, answered units only* | (0.2301 / 0.3220 / 0.6999) *secondary, answered units only* | 46/46 | 0 | 0 req (0 attempts); not completed 0 | 0 | 46/46 | 0.3926 | 44 | in 797,425 / out 103,295 | $2.42 |
| deepseek-v3.2 | DeepSeek | OpenRouter, GMICloud fp8 only, reasoning enabled | 128,000 (5 rows exceeded it: provider reasoning cap 131,072) | PASS | 0.7593 / 0.9074 / 0.8368 | 0.7586 / 0.9087 / 0.8349 | 46/46 | 0 | 7 req (22 attempts); not completed 0 | 0 | 1/46 | 0.0000 | 0 | in 586,302 / out 5,579,648 (reasoning 5,419,381) | $1.85 |
| llama-4-maverick | Meta | OpenRouter, Parasail fp8 only | 32,768 | REFUSED: 0 without an answer, 10 over the cap | (0.2134 / 0.3348 / 0.6376) *secondary, answered units only* | (0.2144 / 0.3369 / 0.6383) *secondary, answered units only* | 46/46 | 0 | 1 req (1 attempts); not completed 0 | 0 | 45/46 | 0.1586 | 10 | in 776,710 / out 182,481 | $0.45 |
| gpt-oss-20b | OpenAI | OpenRouter, AkashML fp4 only, reasoning effort high, T 1.0, top_p 1.0 | 110,000 | REFUSED: 6 without an answer, 32 over the cap | (0.0759 / 0.1396 / 0.5477 (q on 21/40)) *secondary, answered units only* | (0.0713 / 0.1324 / 0.5362 (q on 17/35)) *secondary, answered units only* | 40/46 | 3 | 4 req (4 attempts); not completed 0 | 0 | 35/40 | 0.6502 | 32 | in 787,610 / out 6,164,374 | $0.57 (+ superseded $0.15) |
| Gemma 4 12B | Google | local: llama.cpp build b12110 + Vulkan, zip SHA-256 9732a5e4...6874f; QAT Q4_0 GGUF | 128,000 | REFUSED: 8 without an answer, 9 over the cap | (0.2615 / 0.4655 / 0.5629) *secondary, answered units only* | (0.2612 / 0.4638 / 0.5643) *secondary, answered units only* | 38/46 | 8 | 0 req (0 attempts); not completed 0 | 0 | 38/38 | 0.1883 | 9 | in 807,205 / out 4,279,793 | $0 (local) |
| gpt-oss-120b | OpenAI | OpenRouter, Parasail fp4 (`parasail/fp4`) only; earlier AkashML fp4 (superseded) | 110,000 | **not completed: no pinned provider delivered the 110,000 budget** | – | – | – | – | – | – | – | – | – | – | $1.48 recorded + unrecorded in-flight (see below) |
| kimi-k2.5 | Moonshot AI | OpenRouter, SiliconFlow int4 (planned) | 128,000 (planned) | **not run**: planned; dropped for budget under a rule fixed before any Kimi request (remaining $5.05 < $7.50) | – | – | – | – | – | – | – | – | – | – | – |

Transport errors: requests with at least one transport error (attempts); not completed = units still without an answer after the retry limit and the one resend. deepseek-v3.2's were all stream cut-offs at 30 minutes on the provider route. q is undefined when no linked pairs are guessed (frozen convention) and left out of the q mean; the count is shown when it differs.

## Spend

- **Azure:** $27.79 recorded (gpt-4.1 + gpt-5.6-sol, reported usage x the preregistered rates; Flex without cache discount, an upper bound) + smoke tests $0.0010. Not included: any tokens Azure billed for the 2 filtered gpt-5.6-sol responses (usage not captured).
- **OpenRouter (authoritative): key usage $4.9483** (2026-11-14T15:30 UTC). Recorded in the attempt and smoke logs: $4.5021; the difference, $0.4462, is billing for requests that never reached the attempt log (the gpt-oss-120b requests in flight when it was stopped; streams cut off by the provider).

## Superseded and unscored spend

- gpt-oss-20b on CoreWeave (11 rows + 3 length stops): $0.1501
- gpt-oss-120b on AkashML (27 rows + 2 length stops): $0.4498
- gpt-oss-120b Parasail long-generation tests (5, inconclusive): $0.1871
- gpt-oss-120b Parasail run, stopped at the length stop (13 rows): $0.8444 recorded, plus the unrecorded in-flight requests (part of the OpenRouter difference above)

## Models not run

- kimi-k2.5: planned; dropped for budget under the Kimi rule (remaining balance = $10.00 key limit - key usage = $5.05 < $7.50; usage read after models 3-6). No Kimi request was sent.
- From the preregistration: Azure-hosted gpt-oss-120b, DeepSeek-V3.2, Kimi-K2.5, grok-4-1-fast-reasoning and Llama 4 (not deployable, or zero quota on the student subscription); gpt-6.x and gpt-5.6-terra/luna (training cutoffs after the documents, or the same family as gpt-5.6-sol); gpt-5.5 (cost).

## Preregistration and amendments

- 515571f: preregistration, Sonnet-dependence sweep on headline J (seven hosted models).
- a4ef6ca: amendment 1, gpt-oss on AkashML fp4 with a fixed 110,000 output budget; Azure and OpenRouter lines concurrent.
- 69c3d8c: amendment 2, Azure content-filter blocks are platform errors, resent once under the Default guardrail; gpt-oss-120b on Parasail fp4 (cap $3); llama/deepseek in parallel; Kimi balance defined as limit minus usage.
- User decisions recorded in RUNLOG: gpt-oss-120b's long-generation test replaced by the in-run check (cc9b943); deepseek-v3.2's over-budget rows accepted as a provider deviation (e02c4d0).

## Interpretation (fixed in advance)

A model at or above Sonnet (F1_J 0.7225, F1_L 0.8817, q 0.8206) is evidence against Sonnet dependence of the headline. A lower score is NOT evidence that fragmentation protects, because it may reflect fit to a Sonnet-tuned prompt.
