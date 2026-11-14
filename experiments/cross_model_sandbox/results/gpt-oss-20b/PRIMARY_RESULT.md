# gpt-oss-20b: headline Game J, primary result

Post-hoc exploratory (PREREGISTRATION.md, 2026-11-13). Primary verdict = the preregistered rule applied to the scored rows (a unit without an answer, or a unit's recorded `repair.policy_share` over `joint_game.POLICY_CAP` = 0.25, refuses the cell). The frozen gate's own output is kept in `final_headlineJ*/verdict.json` as `frozen_gate_output`.

## 46 pools: REFUSED

- units without an answer: 6 ['pool_001', 'pool_006', 'pool_015', 'pool_039', 'pool_059', 'pool_067']
- units over the cap: 32 pool_009 1.0, pool_017 1.0, pool_018 1.0, pool_019 1.0, pool_021 1.0, pool_023 1.0, pool_024 1.0, pool_028 1.0, pool_029 1.0, pool_031 1.0, pool_032 1.0, pool_035 1.0, pool_037 1.0, pool_050 1.0, pool_053 1.0, pool_058 1.0, pool_061 1.0, pool_065 1.0, pool_069 1.0, pool_056 0.9198, pool_070 0.7004, pool_066 0.6123, pool_054 0.5771, pool_026 0.5349, pool_020 0.4866, pool_048 0.4747, pool_038 0.425, pool_011 0.4179, pool_030 0.4068, pool_041 0.3764, pool_003 0.3621, pool_005 0.2978
- SECONDARY, answered units only: F1_J 0.0759, F1_L 0.1396, q 0.5477 (defined on 21 of 40)
- completion 40/46; D6 units 3; invalid after repair 35/40; mean policy_share 0.6502; units over cap 32
- excluded before the frozen score: {'content_filter': [], 'not_run': [], 'not_completed': [], 'repair_not_sent_or_not_completed': []}
- frozen gate output: {'prose': ['J']}

## 41 pools (without the 5 epub-2025 pools): REFUSED

- units without an answer: 6 ['pool_001', 'pool_006', 'pool_015', 'pool_039', 'pool_059', 'pool_067']
- units over the cap: 28 pool_017 1.0, pool_018 1.0, pool_019 1.0, pool_021 1.0, pool_023 1.0, pool_024 1.0, pool_028 1.0, pool_029 1.0, pool_031 1.0, pool_032 1.0, pool_035 1.0, pool_037 1.0, pool_050 1.0, pool_053 1.0, pool_058 1.0, pool_061 1.0, pool_065 1.0, pool_069 1.0, pool_070 0.7004, pool_066 0.6123, pool_054 0.5771, pool_026 0.5349, pool_020 0.4866, pool_048 0.4747, pool_038 0.425, pool_030 0.4068, pool_003 0.3621, pool_005 0.2978
- SECONDARY, answered units only: F1_J 0.0713, F1_L 0.1324, q 0.5362 (defined on 17 of 35)
- completion 35/41; D6 units 3; invalid after repair 31/35; mean policy_share 0.6655; units over cap 28
- excluded before the frozen score: {'content_filter': [], 'not_run': [], 'not_completed': [], 'repair_not_sent_or_not_completed': []}
- frozen gate output: {'prose': ['J']}

## Usage

- responses 90, input tokens 787610, output tokens 6164374 (reasoning 0), cost $0.5688
- transport attempts 4, requests with a transport error 4 of 90 rows

- superseded attempts (logs/gpt-oss-20b/superseded_coreweave_117964, never scored): 14 responses, cost $0.1501; total cost including them $0.7189
