**Table 1. Datasets, games and design summary.**

| Experiment | Corpus | Sample | Conditions | Attackers | Primary metric | Status |
|---|---|---|---|---|---|---|
| Headline J | prose (PMC case reports) | 46 pools × 7 docs (322 docs) | sentence cut, full length | One-shot Sonnet; Memon-inspired; embedding† | F1_J (F1_L, q) | prespecified |
| Grid J | prose, ≤30-sentence documents | 24 pools × 7 docs × 9 cells (168 docs) | 4 strategies × 3 granularities, 9 retained cells | One-shot Sonnet; Memon-inspired; embedding† | F1_J (F1_L, q) | prespecified; cells retained after pool-1 screening |
| Headline O | prose | 100 documents (length-stratified) | sentence cut, full length | One-shot Sonnet; Jaccard-Greedy; Jaccard-MST; Random | Kendall τ | prespecified |
| Grid O | prose | 30 documents × 9 cells | the 9 retained cells | One-shot Sonnet; Jaccard-Greedy; Jaccard-MST; Random | Kendall τ | prespecified |
| Identifier J | synthetic records (Faker) | 20 pools × 7 records (28 fields) | one fragment per field | One-shot Sonnet; Memon-inspired; embedding†; Random; analytic and schema-order baselines | F1_J vs schema baseline (90% CI rule); F1_L | prespecified (D11) |
| Single-token edge J† | prose, 4-sentence excerpts | 20 headline pools × 7 docs (140 docs) | sentence cut vs single whitespace token, identical text | One-shot Sonnet; Memon-inspired; embedding | paired A_VJ (visible-text, null-adjusted) | POST-HOC EXPLORATORY (D16) |

† Post-hoc exploratory: the embedding attacker (D14) and the single-token edge experiment (D16) were designed after the prespecified results were seen, then frozen before their own evaluation. Every pool holds N = 7 sources; the attacker is told N, sees masked aliases in a per-unit shuffled order, and never sees raw ids.
One-shot Sonnet units in the final run: 652 (651 completed, 1 RBNC) plus 40 post-hoc excerpt units (40 completed).
