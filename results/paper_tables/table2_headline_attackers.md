**Table 2. Headline prose, Game J: attacker comparison on the 46 headline pools.**

| Attacker | F1_L [95% CI] | q [95% CI] | F1_J [95% CI] | A_J [95% CI] | Exact docs | Completed |
|---|---|---|---|---|---|---|
| Analytic one-bucket baseline | 0.299 [0.286, 0.313] | 0.5 (expected) | 0.149 [0.143, 0.157] | 0.000 [0.000, 0.000] | — | 46/46 |
| Tier 0, PUP‡ | 0.215 [0.202, 0.230] | 0.505 [0.499, 0.515] | 0.109 [0.102, 0.116] | -0.048 [-0.055, -0.042] | 0/322 | 46/46 |
| Memon-inspired | 0.339 [0.314, 0.368] | 0.493 [0.486, 0.504] | 0.168 [0.156, 0.183] | 0.023 [0.011, 0.035] | 0/322 | 46/46 |
| Embedding (post hoc)† | 0.364 [0.335, 0.397] | 0.500 [0.493, 0.508] | 0.182 [0.167, 0.198] | 0.039 [0.026, 0.052] | 0/322 | 46/46 |
| Tier 0, classical‡ | 0.338 [0.314, 0.367] | 0.660 [0.637, 0.695] | 0.234 [0.219, 0.251] | 0.099 [0.082, 0.118] | 0/322 | 46/46 |
| Tier 3, fine-tuned cross-encoder‡ | 0.689 [0.658, 0.721] | 0.756 [0.733, 0.791] | 0.544 [0.521, 0.567] | 0.464 [0.435, 0.491] | 0/322 | 46/46 |
| **One-shot Sonnet** | 0.882 [0.861, 0.901] | 0.792 [0.772, 0.819] | 0.723 [0.702, 0.743] | 0.673 [0.649, 0.698] | 1/322 | 46/46 |

46 headline pools. Means with 95% percentile-bootstrap CIs over pools (10,000 resamples). q is micro-averaged (ΣC/ΣK). Exact = documents recovered with perfect membership and order. Completion = pools answered within the 128k output budget.
Paired (same pools): Sonnet − Memon-inspired F1_J 0.554 [0.529, 0.579] (higher on 46/46 pools); F1_L 0.543 [0.517, 0.566] (higher on 46/46 pools). Embedding − Memon-inspired F1_L 0.024 [0.005, 0.044] (higher on 32/46 pools); Sonnet − embedding F1_L 0.518 [0.487, 0.547] (higher on 46/46 pools).
Paired: Sonnet − tier 3 F1_J 0.178 [0.157, 0.199] (higher on 46/46 pools); F1_L 0.193 [0.166, 0.220].
† Post-hoc exploratory (D14): motivated by the observed Memon-inspired / Sonnet gap; designed and frozen before evaluation; first complete result kept; F1_L is its primary comparison.
‡ Non-LLM attacker ladder (D19): each design, its tuning and its decoder fixed on development pools before any evaluation pool was scored; first complete result kept.
