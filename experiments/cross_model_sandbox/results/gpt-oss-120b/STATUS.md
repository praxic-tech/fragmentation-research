# gpt-oss-120b: headline Game J — NOT COMPLETED

**not completed: no pinned provider delivered the 110,000 budget**

Post-hoc exploratory (PREREGISTRATION.md 2026-11-13 and amendments; user
decision 2026-11-14). No row of this model is scored; no verdict, no means.

- CoreWeave (preregistered): not run for 120b; the same endpoint stopped
  gpt-oss-20b at ~117.7k total tokens (RUNLOG).
- AkashML fp4 (amendment 1): length stops below 110,000 without an answer
  (pool_019 at 109,837; pool_035 at 108,089). 27 base rows, superseded
  (`logs/gpt-oss-120b/superseded_akashml_110000/`). Cost $0.4498.
- Parasail fp4, endpoint `parasail/fp4` (amendment 2): 5 pre-run
  long-generation tests inconclusive (model-side stops), $0.1874; in-run
  check (user decision): pool_007 stopped at length after 104,412 output
  tokens (prompt 12,690; total 117,102) without an answer -> halt.
  13 base rows completed before the stop (`raw/gpt-oss-120b/`), cost
  $0.8444 recorded. The run was stopped immediately (process ended) instead
  of draining in-flight requests, since no row would be scored; requests in
  flight at that moment may be billed by OpenRouter and are not in the
  recorded cost (see the key usage in `logs/openrouter_balance.jsonl`).
- Recorded cost: $0.4498 + $0.1874 + $0.8444 = $1.4816 (plus smoke tests).
