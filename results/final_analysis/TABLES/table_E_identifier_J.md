### Table E — Identifier J (20 frozen pools of 7 records)

| attacker | completed | F1_J_mean | F1_J_lo | F1_J_hi | precision_J_mean | recall_J_mean | F1_L_mean | F1_L_lo | F1_L_hi | q_mean | q_micro | A_J_mean | A_schema_mean | A_schema_lo90 | A_schema_hi90 | raw_schema_diff_mean | L_precision_mean | L_precision_lo | L_precision_hi |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Random | 20 | 0.0555 | 0.0554 | 0.0557 | 0.0555 | 0.0555 | 0.1111 | 0.1109 | 0.1113 | 0.4998 | 0.4996 | -0.0494 | -0.1806 | -0.1808 | -0.1804 | -0.1445 | 0.1111 | 0.1109 | 0.1113 |
| Memon-inspired | 20 | 0.0540 | 0.0420 | 0.0663 | 0.0482 | 0.0619 | 0.1254 | 0.1090 | 0.1424 | 0.4326 | 0.4262 | -0.0511 | -0.1825 | -0.1953 | -0.1693 | -0.1460 | 0.1112 | 0.0955 | 0.1279 |
| One-shot Sonnet | 20 | 0.0833 | 0.0679 | 0.0988 | 0.0833 | 0.0833 | 0.1321 | 0.1131 | 0.1536 | 0.6266 | 0.6306 | -0.0185 | -0.1458 | -0.1622 | -0.1295 | -0.1167 | 0.1321 | 0.1131 | 0.1536 |
| Analytic one-bucket | 20 | 0.1000 | 0.1000 | 0.1000 | — | — | 0.2000 | 0.2000 | 0.2000 | 0.5000 | — | 0.0000 | -0.1250 | -0.1250 | -0.1250 | -0.1000 | — | — | — |
| Schema-order | 20 | 0.2000 | 0.2000 | 0.2000 | — | — | 0.2000 | 0.2000 | 0.2000 | 1.0000 | — | 0.1111 | -0.0000 | -0.0000 | -0.0000 | -0.0000 | — | — | — |

F1_J CIs 95%; A_schema = (F1_J - 0.20)/0.80 with 90% CI (the frozen rule); raw F1_J - 0.20 alongside. q is a template diagnostic. Random = D11/D13 random identifier baseline (10,000 draws per pool).
