# Gemma 4 12B, headline Game J: primary result

**REFUSED** under the preregistered rule (PREREGISTRATION.md, "Primary result and
the integrity gate": a unit over `joint_game.POLICY_CAP` makes the refusal the
primary result).

- Units over the cap (0.25), by the scored rows' recorded `repair.policy_share`: 9
  - pool_061 0.412 (126 of 306 fragments placed by the policy)
  - pool_005 0.393 (70 of 178)
  - pool_031 0.385 (95 of 247)
  - pool_064 0.382 (78 of 204)
  - pool_007 0.352 (122 of 347)
  - pool_008 0.310 (75 of 242)
  - pool_065 0.309 (116 of 375)
  - pool_038 0.290 (58 of 200)
  - pool_070 0.251 (62 of 247)
- Units with no parseable answer after repair: 0
- D6 non-completions (128k exhausted, not scored): 8 (pool_003, 017, 018, 024,
  037, 053, 054, 066)
- Transport errors: 0
- Invalid after repair: 38/38 (one repair round, as preregistered)
- Completion: 38/46

`final_headlineJ/verdict.json` says "refused: none". That is the frozen gate's
output and is wrong for this cell: for Game J the gate takes the policy share as
1 - coverage_frac, and coverage_frac is measured after the completion policy has
filled the gaps, so it is always 1.0 here. The scorer is left unchanged; see
logs/RUNLOG.md, 2026-11-13.

## Secondary: answered units only

`final_headlineJ_answered_units_only/` (frozen `score(..., allow_partial=True)`,
written by `work/runner/score_secondary.py`). Per-pool means over the 38 scored
pools: **F1_J 0.2615, F1_L 0.4655, q 0.5629**. Reported only beside the
refusal, never in its place.
