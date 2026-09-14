### Table B — Headline J (46 pools, full-length reference cut)

| condition | attacker | attempted | completed | rbnc | F1_J_mean | F1_J_lo | F1_J_hi | F1_J_median | precision_J_mean | recall_J_mean | b_J_mean | A_J_mean | A_J_lo | A_J_hi | F1_L_mean | F1_L_lo | F1_L_hi | q_mean | q_micro | q_micro_lo | q_micro_hi | K0_pools | exact_records | records | repaired | transport_retry | cost_per_completed | output_tokens_mean | F1_J_t_lo | F1_J_t_hi | cost_total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| headline (full length) | Analytic one-bucket | 46 | 46 | 0 | 0.1493 | 0.1430 | 0.1567 | 0.1441 | — | — | 0.1493 | 0.0000 | 0.0000 | 0.0000 | 0.2987 | 0.2859 | 0.3134 | 0.5000 | — | — | — | 0 | — | — | 0 | 0 | — | — | 0.1421 | 0.1565 | — |
| headline (full length) | Memon-inspired | 46 | 46 | 0 | 0.1685 | 0.1557 | 0.1831 | 0.1566 | 0.1294 | 0.2645 | 0.1493 | 0.0229 | 0.0114 | 0.0352 | 0.3390 | 0.3145 | 0.3680 | 0.4965 | 0.4934 | 0.4860 | 0.5040 | 0 | 0.0000 | 322.0000 | 0 | 0 | 0.0000 | — | 0.1545 | 0.1825 | 0.0000 |
| headline (full length) | One-shot Sonnet | 46 | 46 | 0 | 0.7225 | 0.7024 | 0.7430 | 0.7131 | 0.7242 | 0.7214 | 0.1493 | 0.6731 | 0.6490 | 0.6977 | 0.8817 | 0.8612 | 0.9005 | 0.8206 | 0.7918 | 0.7723 | 0.8188 | 0 | 1.0000 | 322.0000 | 2 | 6 | 0.2757 | 52283.1739 | 0.7015 | 0.7435 | 12.6818 |
| headline (full length) | Hierarchical (decomposed) Sonnet | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — | — |

Means with 95% percentile-bootstrap CIs over pools (10,000 resamples, seed 42); t-interval columns are a sensitivity check. q_mean averages defined pools; q_micro = sum C / sum K. Hierarchical pending.
