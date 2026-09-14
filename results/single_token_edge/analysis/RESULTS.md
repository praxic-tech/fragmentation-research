# POST-HOC EXPLORATORY — CONTROLLED SINGLE-TOKEN EDGE-CASE EXPERIMENT: results

RUN_DECISIONS D16. **Post-hoc exploratory; not prespecified or confirmatory.** Frozen analysis (analysis/single_token_edge_analysis.py, committed before any result was read).

n_selected 20 pools; 10,000 permutation draws per pool × condition × null.

## One-shot Sonnet

- completion: sentence 20/20, token 20/20; RBNC: sentence none, token none
- n_effective (both conditions completed) 20; n_nonzero 20

| metric | sentence mean | token mean | paired mean diff (s − t) [95% CI] | median diff | sign test p (two-sided) |
|---|---|---|---|---|---|
| A_VJ (PRIMARY) | 0.588 | 0.016 | 0.572 [0.539, 0.607] | 0.563 | 0.0000 |
| V_J | 0.762 | 0.155 | 0.607 [0.586, 0.628] | 0.601 | 0.0000 |
| V_L | 0.889 | 0.427 | 0.462 [0.425, 0.508] | 0.437 | 0.0000 |
| A_VL | 0.777 | 0.159 | 0.618 [0.552, 0.695] | 0.581 | 0.0000 |
| A_VJ_pred | 0.592 | 0.027 | 0.565 [0.532, 0.599] | 0.558 | 0.0000 |
| F1_J | 0.585 | 0.116 | 0.469 [0.437, 0.501] | 0.477 | 0.0000 |
| F1_L | 0.761 | 0.223 | 0.538 [0.482, 0.595] | 0.544 | 0.0000 |
| A_J | 0.539 | -0.016 | 0.555 [0.520, 0.590] | 0.560 | 0.0000 |

- q_V (diagnostic only): sentence 0.860, token 0.376
- raw vs normalised sign disagreement (V_J vs A_VJ), pools: none

## Memon-inspired

- completion: sentence 20/20, token 20/20; RBNC: sentence none, token none
- n_effective (both conditions completed) 20; n_nonzero 20

| metric | sentence mean | token mean | paired mean diff (s − t) [95% CI] | median diff | sign test p (two-sided) |
|---|---|---|---|---|---|
| A_VJ | 0.043 | -0.067 | 0.110 [0.047, 0.178] | 0.065 | 0.0026 |
| V_J | 0.448 | 0.084 | 0.364 [0.326, 0.404] | 0.330 | 0.0000 |
| V_L | 0.578 | 0.203 | 0.375 [0.333, 0.422] | 0.349 | 0.0000 |
| A_VL | 0.151 | -0.168 | 0.319 [0.238, 0.407] | 0.276 | 0.0000 |
| A_VJ_pred | 0.084 | -0.062 | 0.146 [0.090, 0.206] | 0.101 | 0.0004 |
| F1_J | 0.165 | 0.084 | 0.081 [0.046, 0.118] | 0.069 | 0.0000 |
| F1_L | 0.333 | 0.167 | 0.166 [0.125, 0.212] | 0.167 | 0.0000 |
| A_J | 0.072 | -0.053 | 0.125 [0.086, 0.167] | 0.111 | 0.0000 |

- q_V (diagnostic only): sentence 0.774, token 0.413
- raw vs normalised sign disagreement (V_J vs A_VJ), pools: ['pool_017', 'pool_032', 'pool_041']

*Not security evidence at the token level: this attacker was not designed for isolated tokens.*

## Embedding (post-hoc exploratory)

- completion: sentence 20/20, token 20/20; RBNC: sentence none, token none
- n_effective (both conditions completed) 20; n_nonzero 20

| metric | sentence mean | token mean | paired mean diff (s − t) [95% CI] | median diff | sign test p (two-sided) |
|---|---|---|---|---|---|
| A_VJ | 0.104 | -0.090 | 0.194 [0.155, 0.233] | 0.201 | 0.0000 |
| V_J | 0.483 | 0.064 | 0.419 [0.394, 0.444] | 0.420 | 0.0000 |
| V_L | 0.635 | 0.215 | 0.420 [0.382, 0.458] | 0.422 | 0.0000 |
| A_VL | 0.265 | -0.151 | 0.416 [0.341, 0.489] | 0.410 | 0.0000 |
| A_VJ_pred | 0.157 | -0.038 | 0.195 [0.161, 0.229] | 0.189 | 0.0000 |
| F1_J | 0.214 | 0.121 | 0.094 [0.065, 0.124] | 0.090 | 0.0000 |
| F1_L | 0.422 | 0.238 | 0.184 [0.134, 0.237] | 0.179 | 0.0000 |
| A_J | 0.127 | -0.011 | 0.138 [0.106, 0.171] | 0.133 | 0.0000 |

- q_V (diagnostic only): sentence 0.770, token 0.298
- raw vs normalised sign disagreement (V_J vs A_VJ), pools: none

*Not security evidence at the token level: this attacker was not designed for isolated tokens.*

## Resources (one-shot Sonnet, every provider row: original, resend, repair)

| condition | rows | input tokens | output tokens | cost (credit) | at 128k | refused for credit |
|---|---|---|---|---|---|---|
| sentence | 20 | 34,611 | 106,375 | $0.57 | 0 | 0 |
| token | 31 | 164,649 | 2,682,786 | $13.58 | 3 | 0 |

Descriptive only (common metric F1_J): excerpt sentence arm 0.585 vs full-document headline 0.723.

## Claim discipline

Supports at most: on identical four-sentence excerpts from seven-document pools of PMC clinical case reports, single-token fragmentation reduced / changed null-adjusted visible joint reconstruction under the frozen one-shot Sonnet attacker relative to sentence fragmentation. It does not support: 'secure', 'prevents reconstruction', a threshold, a semantic-context mechanism, or generalisation beyond this corpus, task, attacker and resource budget. RBNC is resource-bounded non-completion, never a zero score; the complete-case paired analysis may be biased in an unknown direction. The RBNC projection made before the run was a model-based extrapolation, not an observed probability.
