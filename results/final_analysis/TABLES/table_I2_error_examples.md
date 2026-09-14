### Error-taxonomy examples, selected by a predefined quantile rule

| rule | family | cell | pool | F1_J | b_J | records | exact_records | correct_membership_wrong_order | merged_clusters | split_records | singleton_clusters | frac_fragments_off_by_one | frac_fragments_displaced_gt5 | catastrophic_F1_le_baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| headline: nearest-rank 0th percentile of one-shot F1_J | headline | prose | pool_067 | 0.5474 | 0.1432 | 7 | 0 | 1 | 1 | 1 | 0 | 0.2597 | 0.1234 | no |
| headline: nearest-rank 25th percentile of one-shot F1_J | headline | prose | pool_025 | 0.6655 | 0.1670 | 7 | 0 | 0 | 0 | 0 | 0 | 0.1185 | 0.4593 | no |
| headline: nearest-rank 50th percentile of one-shot F1_J | headline | prose | pool_010 | 0.7120 | 0.1939 | 7 | 0 | 0 | 0 | 0 | 0 | 0.1288 | 0.4924 | no |
| headline: nearest-rank 75th percentile of one-shot F1_J | headline | prose | pool_039 | 0.7756 | 0.1441 | 7 | 0 | 0 | 0 | 0 | 0 | 0.1867 | 0.1378 | no |
| headline: nearest-rank 100th percentile of one-shot F1_J | headline | prose | pool_029 | 0.9020 | 0.1445 | 7 | 0 | 4 | 0 | 0 | 0 | 0.2247 | 0.0674 | no |
| grid: nearest-rank 0th percentile of one-shot F1_J | grid | subject-verb__clause | pool_057 | 0.4146 | 0.1280 | 7 | 0 | 0 | 2 | 2 | 8 | 0.1577 | 0.3038 | no |
| grid: nearest-rank 25th percentile of one-shot F1_J | grid | random__token-window | pool_051 | 0.5965 | 0.1292 | 7 | 0 | 0 | 1 | 1 | 0 | 0.1511 | 0.3453 | no |
| grid: nearest-rank 50th percentile of one-shot F1_J | grid | semantic__sentence | pool_051 | 0.6924 | 0.1241 | 7 | 0 | 1 | 0 | 0 | 0 | 0.1484 | 0.2692 | no |
| grid: nearest-rank 75th percentile of one-shot F1_J | grid | random__clause | pool_033 | 0.7650 | 0.1236 | 7 | 0 | 0 | 0 | 0 | 0 | 0.2653 | 0.0765 | no |
| grid: nearest-rank 100th percentile of one-shot F1_J | grid | random__sentence | pool_055 | 0.9648 | 0.1341 | 7 | 3 | 2 | 0 | 0 | 0 | 0.0738 | 0.0201 | no |
| identifier: nearest-rank 0th percentile of one-shot F1_J | identifier | identifier__field | idpool_000 | 0.0238 | 0.1000 | 7 | 0 | 0 | 7 | 7 | 0 | 0.2222 | 0.0000 | yes |
| identifier: nearest-rank 25th percentile of one-shot F1_J | identifier | identifier__field | idpool_017 | 0.0476 | 0.1000 | 7 | 0 | 0 | 7 | 7 | 0 | 0.5000 | 0.0000 | yes |
| identifier: nearest-rank 50th percentile of one-shot F1_J | identifier | identifier__field | idpool_001 | 0.0952 | 0.1000 | 7 | 0 | 0 | 7 | 7 | 0 | 0.1667 | 0.0000 | yes |
| identifier: nearest-rank 75th percentile of one-shot F1_J | identifier | identifier__field | idpool_018 | 0.0952 | 0.1000 | 7 | 0 | 0 | 7 | 7 | 0 | 0.3333 | 0.0000 | yes |
| identifier: nearest-rank 100th percentile of one-shot F1_J | identifier | identifier__field | idpool_015 | 0.1429 | 0.1000 | 7 | 0 | 0 | 7 | 7 | 0 | 0.0000 | 0.0000 | no |

Selected by nearest-rank percentile (0, 25, 50, 75, 100) of one-shot F1_J within each family, not by how they look. Illustrative, not inferential.
