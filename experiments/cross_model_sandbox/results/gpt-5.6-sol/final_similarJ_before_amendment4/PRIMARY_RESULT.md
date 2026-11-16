# gpt-5.6-sol: similar pools (D20) Game J, primary result

Post-hoc exploratory (PREREGISTRATION.md, 2026-11-13). Primary verdict = the preregistered rule applied to the scored rows (a unit without an answer, or a unit's recorded `repair.policy_share` over `joint_game.POLICY_CAP` = 0.25, refuses the cell). The frozen gate's own output is kept in `final_headlineJ*/verdict.json` as `frozen_gate_output`.

## 46 pools: REFUSED

- units without an answer: 2 ['sim_015', 'sim_041']
- units over the cap: 0 
- SECONDARY, answered units only: F1_J 0.7840, F1_L 0.8785, q 0.8940
- completion 44/46; D6 units 0; invalid after repair 0/44; mean policy_share 0.0000; units over cap 0
- excluded before the frozen score: {'content_filter': [], 'not_run': ['sim_015', 'sim_041'], 'not_completed': ['sim_015', 'sim_041'], 'repair_not_sent_or_not_completed': []}
- frozen gate output: {'prose': ['J']}

## 41 pools (without the 5 epub-2025 pools): not applicable

- the 41-pool sensitivity removes headline pools by name; the similar pools regroup the same 322 documents (7 have a 2025 first-online date)

## Usage

- responses 44, input tokens 381198, output tokens 2759205 (reasoning 2677556), cost $28.3544
- transport attempts 5, requests with a transport error 5 of 44 rows
