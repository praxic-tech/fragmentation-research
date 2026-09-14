### Identifier: frozen near-baseline decision (±0.10, 90% CI)

| attacker | A_schema_mean | ci90_lo | ci90_hi | raw_diff_mean | raw_ci90_lo | raw_ci90_hi | t90_lo | t90_hi | near_schema_baseline | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| Random | -0.1806 | -0.1808 | -0.1804 | -0.1445 | -0.1446 | -0.1444 | -0.1808 | -0.1804 | no | NOT near: entire 90% CI below -0.10 (below the schema-aware baseline) |
| Memon-inspired | -0.1825 | -0.1953 | -0.1693 | -0.1460 | -0.1563 | -0.1355 | -0.1964 | -0.1686 | no | NOT near: entire 90% CI below -0.10 (below the schema-aware baseline) |
| One-shot Sonnet | -0.1458 | -0.1622 | -0.1295 | -0.1167 | -0.1298 | -0.1036 | -0.1631 | -0.1285 | no | NOT near: entire 90% CI below -0.10 (below the schema-aware baseline) |

Primary criterion: the entire 90% percentile-bootstrap CI on the normalized schema advantage inside [-0.10, +0.10]. Nonsignificance is never read as equivalence.
