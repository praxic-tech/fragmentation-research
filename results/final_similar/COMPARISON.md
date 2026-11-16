# Similar pools against headline pools (RUN_DECISIONS D20, post-hoc exploratory)

Mean within-pool cosine: similar 0.138, headline 0.069. Same 322 documents and fragments; only pool membership differs. Diff = similar − headline, 95% bootstrap CI (10,000 resamples of pools within each set, seed 42).

| Attacker | F1_J similar | F1_J headline | diff F1_J | diff F1_L | diff q | Reading (D20) |
|---|---|---|---|---|---|---|
| T0-classical | 0.176 | 0.234 | -0.058 [-0.080, -0.037] | -0.085 [-0.119, -0.052] | +0.006 [-0.035, +0.047] | similarity helps the defence |
| T0-PUP | 0.103 | 0.109 | -0.006 [-0.015, +0.003] | -0.008 [-0.025, +0.008] | -0.010 [-0.025, +0.007] | similarity of this kind does not protect |

Descriptive, not in D20: within the similar pools, F1_J for the most similar third, the middle third and the least similar third, and the Spearman correlation of pool cosine with F1_J.

| Attacker | most similar | middle | least similar | Spearman ρ (p) |
|---|---|---|---|---|
| T0-classical | 0.157 | 0.164 | 0.207 | -0.55 (7.74e-05) |
| T0-PUP | 0.104 | 0.104 | 0.101 | +0.05 (0.723) |

Pending: One-shot Sonnet, T3-crossenc, T2-pythia1.4b, T1-pythia160m.
