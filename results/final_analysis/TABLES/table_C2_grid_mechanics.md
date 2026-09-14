### Fragmentation mechanics per grid cell (§13; word counts)

| cell | pools | doc_words_mean | frags_per_doc | frags_per_pool | frags_per_pool_min | frags_per_pool_max | frag_words_mean | frag_words_median | frag_words_sd | frag_words_min | frag_words_max | frags_per_1000_words |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| random / sentence | 24 | 477.6607 | 24.5595 | 171.9167 | 136.0000 | 205.0000 | 19.4996 | 13.9583 | 18.8372 | 1.0000 | 159.0000 | 51.5276 |
| semantic / sentence | 24 | 477.6607 | 24.5595 | 171.9167 | 136.0000 | 205.0000 | 19.4996 | 17.6250 | 10.1907 | 2.0000 | 142.0000 | 51.5276 |
| subject-verb / sentence | 24 | 477.6607 | 40.9405 | 286.5833 | 236.0000 | 344.0000 | 11.6886 | 9.3333 | 9.7462 | 1.0000 | 111.0000 | 85.9422 |
| random / clause | 24 | 477.6607 | 30.9048 | 216.3333 | 178.0000 | 257.0000 | 15.5009 | 10.8750 | 15.0994 | 1.0000 | 158.0000 | 64.7959 |
| semantic / clause | 24 | 477.6607 | 30.9048 | 216.3333 | 178.0000 | 257.0000 | 15.5009 | 13.4583 | 9.4845 | 1.0000 | 80.0000 | 64.7959 |
| coherence-sever / clause | 24 | 477.6607 | 22.6488 | 158.5417 | 125.0000 | 200.0000 | 21.2667 | 14.2083 | 20.1239 | 1.0000 | 183.0000 | 47.5289 |
| subject-verb / clause | 24 | 477.6607 | 48.4881 | 339.4167 | 288.0000 | 414.0000 | 9.8697 | 7.5208 | 8.4588 | 1.0000 | 70.0000 | 101.7152 |
| random / token-window | 24 | 477.6607 | 40.2798 | 281.9583 | 238.0000 | 336.0000 | 11.8574 | 8.6042 | 11.0827 | 1.0000 | 115.0000 | 84.3361 |
| coherence-sever / token-window | 24 | 477.6607 | 40.2202 | 281.5417 | 236.0000 | 333.0000 | 11.8765 | 12.0000 | 1.2046 | 1.0000 | 15.0000 | 84.2021 |

Averaged over each cell's 24 pools; per-pool values in GRID_J.csv. frags_per_1000_words is descriptive, not a causal decomposition.
