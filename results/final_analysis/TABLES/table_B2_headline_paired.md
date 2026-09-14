### Headline J: paired attacker comparisons (pools)

| family | metric | a | b | analysis_label | n_pairs | mean_diff | mean_lo | mean_hi | median_diff | median_lo | median_hi | t_lo | t_hi | frac_a_higher |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| headline | F1_J | One-shot Sonnet | Memon-inspired | prespecified | 46 | 0.5540 | 0.5288 | 0.5793 | 0.5382 | 0.5137 | 0.5935 | 0.5283 | 0.5798 | 1.0000 |
| headline | F1_J | One-shot Sonnet | Analytic one-bucket | prespecified | 46 | 0.5732 | 0.5507 | 0.5958 | 0.5597 | 0.5289 | 0.6056 | 0.5499 | 0.5965 | 1.0000 |
| headline | F1_J | Memon-inspired | Analytic one-bucket | prespecified | 46 | 0.0191 | 0.0096 | 0.0292 | 0.0128 | 0.0019 | 0.0280 | 0.0090 | 0.0293 | 0.6522 |
| headline | F1_J | Embedding (post-hoc exploratory) | Memon-inspired | post-hoc exploratory | 46 | 0.0131 | 0.0028 | 0.0233 | 0.0118 | 0.0056 | 0.0264 | 0.0022 | 0.0240 | 0.6957 |
| headline | F1_J | One-shot Sonnet | Embedding (post-hoc exploratory) | post-hoc exploratory | 46 | 0.5409 | 0.5141 | 0.5680 | 0.5317 | 0.5059 | 0.5768 | 0.5130 | 0.5688 | 1.0000 |
| headline | F1_J | Embedding (post-hoc exploratory) | Analytic one-bucket | post-hoc exploratory | 46 | 0.0322 | 0.0218 | 0.0433 | 0.0193 | 0.0104 | 0.0446 | 0.0212 | 0.0433 | 0.8043 |
| headline | F1_L | One-shot Sonnet | Memon-inspired | prespecified | 46 | 0.5427 | 0.5167 | 0.5661 | 0.5495 | 0.5173 | 0.5815 | 0.5172 | 0.5682 | 1.0000 |
| headline | F1_L | Embedding (post-hoc exploratory) | Memon-inspired | post-hoc exploratory | 46 | 0.0245 | 0.0049 | 0.0443 | 0.0187 | 0.0109 | 0.0362 | 0.0041 | 0.0449 | 0.6957 |
| headline | F1_L | One-shot Sonnet | Embedding (post-hoc exploratory) | post-hoc exploratory | 46 | 0.5182 | 0.4873 | 0.5465 | 0.5354 | 0.5177 | 0.5561 | 0.4874 | 0.5490 | 1.0000 |
| headline | q | One-shot Sonnet | Memon-inspired | prespecified | 46 | 0.3242 | 0.3027 | 0.3458 | 0.3206 | 0.2925 | 0.3624 | 0.3016 | 0.3468 | 1.0000 |
| headline | q | Embedding (post-hoc exploratory) | Memon-inspired | post-hoc exploratory | 46 | 0.0040 | -0.0027 | 0.0106 | 0.0034 | -0.0020 | 0.0097 | -0.0029 | 0.0109 | 0.5870 |
| headline | q | One-shot Sonnet | Embedding (post-hoc exploratory) | post-hoc exploratory | 46 | 0.3201 | 0.2994 | 0.3412 | 0.3091 | 0.2932 | 0.3473 | 0.2982 | 0.3421 | 1.0000 |
| headline | A_J | One-shot Sonnet | Memon-inspired | prespecified | 46 | 0.6503 | 0.6232 | 0.6779 | 0.6319 | 0.6084 | 0.6856 | 0.6223 | 0.6782 | 1.0000 |
| headline | A_J | Embedding (post-hoc exploratory) | Memon-inspired | post-hoc exploratory | 46 | 0.0157 | 0.0035 | 0.0278 | 0.0138 | 0.0064 | 0.0306 | 0.0029 | 0.0285 | 0.6957 |
| headline | A_J | One-shot Sonnet | Embedding (post-hoc exploratory) | post-hoc exploratory | 46 | 0.6346 | 0.6055 | 0.6643 | 0.6171 | 0.6026 | 0.6796 | 0.6042 | 0.6649 | 1.0000 |

a - b per pool; percentile bootstrap resamples each pool once with both attackers' scores; 95% CIs; t-interval as sensitivity.
