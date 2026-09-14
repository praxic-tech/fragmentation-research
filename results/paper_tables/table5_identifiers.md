**Table 5. Structured identifiers, Game J: attackers against the analytic and schema-order baselines.**

| Attacker / baseline | F1_J [95% CI] | F1_L [95% CI] | q | Linkage precision [95% CI] | A_schema [90% CI] | F1_J − 0.20 [90% CI] | Near baseline? |
|---|---|---|---|---|---|---|---|
| Schema-order baseline | 0.200 [0.200, 0.200] | 0.200 [0.200, 0.200] | 1.00 | — | 0.000 | 0.000 | (baseline) |
| Analytic one-bucket baseline | 0.100 [0.100, 0.100] | 0.200 [0.200, 0.200] | 0.50 | — | -0.125 | -0.100 | (baseline) |
| Random partition | 0.056 [0.055, 0.056] | 0.111 [0.111, 0.111] | 0.50 | 0.111 [0.111, 0.111] | -0.181 [-0.181, -0.180] | -0.144 [-0.145, -0.144] | no: entire 90% CI below −0.10 |
| Memon-inspired | 0.054 [0.042, 0.066] | 0.125 [0.109, 0.142] | 0.43 | 0.111 [0.096, 0.128] | -0.182 [-0.195, -0.169] | -0.146 [-0.156, -0.135] | no: entire 90% CI below −0.10 |
| Embedding (post hoc)† | 0.054 [0.043, 0.065] | 0.109 [0.100, 0.120] | 0.49 | 0.073 [0.068, 0.079] | -0.183 [-0.195, -0.171] | -0.146 [-0.156, -0.137] | no: entire 90% CI below −0.10 |
| **One-shot Sonnet** | 0.083 [0.068, 0.099] | 0.132 [0.113, 0.154] | 0.63 | 0.132 [0.113, 0.154] | -0.146 [-0.162, -0.129] | -0.117 [-0.130, -0.104] | no: entire 90% CI below −0.10 |

20 pools of 7 synthetic records (name, SSN, account, address; 28 fragments). F1 CIs are 95%; the schema advantage A_schema = (F1_J − 0.20)/(1 − 0.20) carries the frozen 90% CI. Frozen rule (D11): joint reconstruction is 'near the schema-order baseline' only if the whole 90% CI lies within ±0.10. No attacker met it; every attacker fell below the baseline.
q is a template diagnostic only: the field order is visible from field format, so the schema-order baseline reaches q = 1 with no record knowledge. Linkage precision (exploratory): the share of an attacker's claimed same-record pairs that are real, against 1/7 = 0.143 for template-respecting random assignment. All 140 Sonnet groups held exactly one field of each type.
† Post-hoc exploratory attacker (D14).
