# Memon-inspired: before / after the SHA-256 seed fix (RUN_DECISIONS D13)

- pools compared: 282 (46 headline, 216 grid, 20 identifier)
- pools whose predicted reconstruction changed: not directly observable for the pre-fix run (it stored no reconstructions); judged from every stored count and score: 9 of 282 pools differ in any of them
- pools whose F1_J changed: 9
- pools whose F1_L changed: 0
- pools whose q changed: 9
- maximum absolute score difference: 0.0233
- post-fix runs under PYTHONHASHSEED 0 vs 987: 0 of 282 pools differ (reconstructions and every score compared)

| condition | pools | F1_J before | F1_J after | F1_L before | F1_L after | q_micro before | q_micro after |
|---|---|---|---|---|---|---|---|
| gridJ/coherence-sever__clause | 24 | 0.126097 | 0.126082 | 0.249464 | 0.249464 | 0.504872 | 0.504807 |
| gridJ/coherence-sever__token-window | 24 | 0.135818 | 0.135950 | 0.264997 | 0.264997 | 0.513611 | 0.514023 |
| gridJ/random__clause | 24 | 0.132888 | 0.132888 | 0.257881 | 0.257881 | 0.515108 | 0.515108 |
| gridJ/random__sentence | 24 | 0.130775 | 0.130775 | 0.253369 | 0.253369 | 0.516708 | 0.516708 |
| gridJ/random__token-window | 24 | 0.133557 | 0.133557 | 0.261614 | 0.261614 | 0.510656 | 0.510656 |
| gridJ/semantic__clause | 24 | 0.130329 | 0.130430 | 0.256171 | 0.256171 | 0.508018 | 0.508344 |
| gridJ/semantic__sentence | 24 | 0.142156 | 0.142156 | 0.284741 | 0.284741 | 0.496303 | 0.496303 |
| gridJ/subject-verb__clause | 24 | 0.131172 | 0.131172 | 0.259401 | 0.259401 | 0.504872 | 0.504872 |
| gridJ/subject-verb__sentence | 24 | 0.126206 | 0.126206 | 0.256866 | 0.256866 | 0.490774 | 0.490774 |
| headlineJ/prose | 46 | 0.168205 | 0.168464 | 0.339016 | 0.339016 | 0.493128 | 0.493403 |
| identifierJ/identifier__field | 20 | 0.054017 | 0.054017 | 0.125438 | 0.125438 | 0.426230 | 0.426230 |

Canonical result: post-fix run; the pre-fix run is kept only in the audit trail and the numerical effect is reported.
