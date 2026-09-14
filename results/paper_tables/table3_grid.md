**Table 3. Full retained prose grid, Game J (and Game O τ), One-shot Sonnet.**

| Cell (strategy / granularity) | Frags/doc | Words/frag | F1_J [95% CI] | b_J | A_J [95% CI] | F1_L [95% CI] | q [95% CI] | F1_L Memon / Embed† | Game O τ [95% CI] | Completed |
|---|---|---|---|---|---|---|---|---|---|---|
| random / sentence | 24.6 | 19.5 | 0.801 [0.772, 0.829] | 0.128 | 0.772 [0.739, 0.804] | 0.862 [0.837, 0.886] | 0.926 [0.905, 0.946] | 0.253 / 0.248 | 0.935 [0.892, 0.968] | 24/24 |
| random / clause | 30.9 | 15.5 | 0.754 [0.724, 0.784] | 0.130 | 0.718 [0.683, 0.752] | 0.835 [0.811, 0.857] | 0.899 [0.879, 0.919] | 0.258 / 0.246 | 0.905 [0.852, 0.945] | 24/24 |
| random / token-window | 40.3 | 11.9 | 0.634 [0.599, 0.670] | 0.132 | 0.579 [0.538, 0.619] | 0.747 [0.718, 0.775] | 0.845 [0.818, 0.870] | 0.262 / 0.246 | 0.909 [0.875, 0.942] | 23/24 |
| semantic / sentence | 24.6 | 19.5 | 0.739 [0.707, 0.769] | 0.128 | 0.700 [0.665, 0.735] | 0.879 [0.851, 0.904] | 0.838 [0.820, 0.856] | 0.285 / 0.315 | 0.841 [0.792, 0.887] | 24/24 |
| semantic / clause | 30.9 | 15.5 | 0.679 [0.643, 0.714] | 0.130 | 0.631 [0.591, 0.671] | 0.823 [0.784, 0.858] | 0.823 [0.802, 0.844] | 0.256 / 0.260 | 0.791 [0.725, 0.851] | 24/24 |
| coherence-sever / clause | 22.6 | 21.3 | 0.726 [0.702, 0.749] | 0.131 | 0.684 [0.657, 0.711] | 0.849 [0.832, 0.864] | 0.851 [0.830, 0.873] | 0.249 / 0.274 | 0.816 [0.745, 0.874] | 24/24 |
| coherence-sever / token-window | 40.2 | 11.9 | 0.700 [0.670, 0.730] | 0.132 | 0.655 [0.620, 0.689] | 0.860 [0.829, 0.889] | 0.810 [0.790, 0.830] | 0.265 / 0.268 | 0.943 [0.917, 0.967] | 24/24 |
| subject-verb / sentence | 40.9 | 11.7 | 0.553 [0.527, 0.579] | 0.130 | 0.487 [0.457, 0.516] | 0.689 [0.659, 0.719] | 0.800 [0.782, 0.819] | 0.257 / 0.251 | 0.733 [0.666, 0.794] | 24/24 |
| subject-verb / clause | 48.5 | 9.9 | 0.498 [0.476, 0.521] | 0.131 | 0.422 [0.397, 0.449] | 0.646 [0.621, 0.670] | 0.768 [0.746, 0.791] | 0.259 / 0.250 | 0.724 [0.652, 0.792] | 24/24 |

Grid pools 2–25 (24 pools of 7 documents per cell; documents capped at 30 reference sentences). One-shot Sonnet unless stated; 95% percentile-bootstrap CIs over pools. b_J is the pool-mean analytic one-bucket baseline. F1_L for Memon-inspired / embedding (post hoc) shown for reference; both sit at q ≈ 0.5.
Game O τ: the same attacker ordering single documents with membership given (30 documents per cell; CI over documents). random / token-window: one pool (pool_002, 322 fragments) exhausted the 128k output budget and is excluded as a resource-bounded non-completion, never scored 0.
Semantic / sentence is standard sentence splitting and the reference cut; the headline (Table 2) is the same cut at full length.
