# Tiers 1 and 2 against the other attackers (RUN_DECISIONS D19)

Headline only (the scope fixed for tiers 1 and 2). Means with 95% paired bootstrap CIs (10,000 resamples, seed 42). Diff = tier minus attacker.

Not run by the results freeze: T2-pythia1.4b.

## T1-pythia160m

Game J headline (46 pools): F1_J 0.168 [0.160, 0.177], F1_L 0.327 [0.312, 0.343], q 0.515, base 0.149, A_J 0.022 (of the means), exact records 0/322

| Attacker | F1_J | tier − attacker, F1_J | tier − attacker, F1_L |
|---|---|---|---|
| T3-crossenc | 0.544 [0.521, 0.567] | -0.376 [-0.397, -0.354] | -0.362 [-0.391, -0.334] |
| T0-classical | 0.234 [0.219, 0.251] | -0.066 [-0.079, -0.053] | -0.011 [-0.033, 0.007] |
| T0-PUP | 0.109 [0.102, 0.116] | 0.059 [0.050, 0.070] | 0.112 [0.093, 0.132] |
| One-shot Sonnet | 0.723 [0.702, 0.743] | -0.554 [-0.575, -0.533] | -0.554 [-0.574, -0.533] |
| Memon-inspired | 0.168 [0.156, 0.183] | -0.000 [-0.013, 0.012] | -0.012 [-0.037, 0.010] |
| Embedding (post-hoc exploratory) | 0.182 [0.167, 0.198] | -0.013 [-0.028, -0.000] | -0.036 [-0.065, -0.011] |
| Analytic one-bucket | 0.149 [0.143, 0.157] | 0.019 [0.009, 0.030] | 0.029 [0.009, 0.048] |

Game O headline (100 documents; random τ = 0): τ 0.031 [0.003, 0.060]

| Attacker | τ | tier − attacker |
|---|---|---|
| T3-crossenc-O | 0.639 [0.602, 0.673] | -0.608 [-0.653, -0.561] |
| T0-classical-O | 0.504 [0.468, 0.539] | -0.474 [-0.518, -0.428] |
| T0-PUP-O | 0.016 [-0.009, 0.040] | 0.015 [-0.025, 0.054] |
| One-shot Sonnet | 0.769 [0.734, 0.801] | -0.738 [-0.779, -0.695] |
| Jaccard-Greedy | -0.005 [-0.031, 0.021] | 0.036 [-0.003, 0.076] |
| Jaccard-MST | 0.012 [-0.017, 0.040] | 0.019 [-0.016, 0.053] |
