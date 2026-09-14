### Table A — Corpus and design summary

| family | corpus | game | sample | pool_size | condition | attackers | primary_metric |
|---|---|---|---|---|---|---|---|
| Headline J | prose (PMC case reports) | J | 46 pools | 7 documents | semantic / sentence, full length (reference cut) | Analytic one-bucket; Memon-inspired; One-shot Sonnet; Hierarchical (pending) | raw F1_J |
| Grid J | prose | J | 24 pools (2-25) x 9 cells | 7 documents | 9 retained strategy x granularity cells (D5) | Analytic one-bucket; Memon-inspired; One-shot Sonnet | raw F1_J |
| Identifier J | synthetic identifier records | J | 20 pools | 7 records (28 fields) | one fragment per field | Analytic 0.10; Schema-order 0.20; Random; Memon-inspired; One-shot Sonnet | F1_J; schema advantage with 90% CI (±0.10 rule) |
| Headline O | prose | O | 100 documents (length-stratified) | 1 document | semantic / sentence, full length | Random; Jaccard-Greedy; Jaccard-MST; One-shot Sonnet | Kendall tau |
| Grid O | prose | O | 30 documents x 9 cells | 1 document | 9 retained cells | Random; Jaccard-Greedy; Jaccard-MST; One-shot Sonnet | Kendall tau |

Pool 1 (screening) is excluded from every primary estimate (§24).
