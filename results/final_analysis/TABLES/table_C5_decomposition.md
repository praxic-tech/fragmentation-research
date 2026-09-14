### Linkage vs ordering decomposition (§14)

| condition | attacker | F1_L | q_micro | F1_J |
|---|---|---|---|---|
| headline (full length) | One-shot Sonnet | 0.8817 | 0.7918 | 0.7225 |
| headline (full length) | Memon-inspired | 0.3390 | 0.4934 | 0.1685 |
| headline (full length) | Embedding (post-hoc exploratory) | 0.3635 | 0.4996 | 0.1816 |
| random / sentence | One-shot Sonnet | 0.8620 | 0.9259 | 0.8009 |
| random / sentence | Memon-inspired | 0.2534 | 0.5167 | 0.1308 |
| random / sentence | Embedding (post-hoc exploratory) | 0.2477 | 0.5183 | 0.1285 |
| semantic / sentence | One-shot Sonnet | 0.8787 | 0.8384 | 0.7387 |
| semantic / sentence | Memon-inspired | 0.2847 | 0.4963 | 0.1422 |
| semantic / sentence | Embedding (post-hoc exploratory) | 0.3147 | 0.4980 | 0.1575 |
| subject-verb / sentence | One-shot Sonnet | 0.6890 | 0.8002 | 0.5532 |
| subject-verb / sentence | Memon-inspired | 0.2569 | 0.4908 | 0.1262 |
| subject-verb / sentence | Embedding (post-hoc exploratory) | 0.2510 | 0.4960 | 0.1247 |
| random / clause | One-shot Sonnet | 0.8350 | 0.8994 | 0.7544 |
| random / clause | Memon-inspired | 0.2579 | 0.5151 | 0.1329 |
| random / clause | Embedding (post-hoc exploratory) | 0.2464 | 0.5170 | 0.1273 |
| semantic / clause | One-shot Sonnet | 0.8230 | 0.8229 | 0.6790 |
| semantic / clause | Memon-inspired | 0.2562 | 0.5083 | 0.1304 |
| semantic / clause | Embedding (post-hoc exploratory) | 0.2598 | 0.5072 | 0.1322 |
| coherence-sever / clause | One-shot Sonnet | 0.8487 | 0.8512 | 0.7258 |
| coherence-sever / clause | Memon-inspired | 0.2495 | 0.5048 | 0.1261 |
| coherence-sever / clause | Embedding (post-hoc exploratory) | 0.2735 | 0.4997 | 0.1376 |
| subject-verb / clause | One-shot Sonnet | 0.6456 | 0.7681 | 0.4980 |
| subject-verb / clause | Memon-inspired | 0.2594 | 0.5049 | 0.1312 |
| subject-verb / clause | Embedding (post-hoc exploratory) | 0.2503 | 0.5071 | 0.1271 |
| random / token-window | One-shot Sonnet | 0.7472 | 0.8445 | 0.6343 |
| random / token-window | Memon-inspired | 0.2616 | 0.5107 | 0.1336 |
| random / token-window | Embedding (post-hoc exploratory) | 0.2461 | 0.5133 | 0.1263 |
| coherence-sever / token-window | One-shot Sonnet | 0.8604 | 0.8104 | 0.7005 |
| coherence-sever / token-window | Memon-inspired | 0.2650 | 0.5140 | 0.1360 |
| coherence-sever / token-window | Embedding (post-hoc exploratory) | 0.2675 | 0.5190 | 0.1390 |
| identifier | One-shot Sonnet | 0.1321 | 0.6306 | 0.0833 |
| identifier | Memon-inspired | 0.1254 | 0.4262 | 0.0540 |
| identifier | Embedding (post-hoc exploratory) | 0.1095 | 0.4920 | 0.0537 |

F1_L mean over pools; q_micro = sum C / sum K; F1_J = F1_L x q holds per pool (max residual 2.2e-16). Diagnostic.
