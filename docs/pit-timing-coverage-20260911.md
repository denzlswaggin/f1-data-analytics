# Pit timing coverage refresh — 11 September 2026

Recomputed all 60 completed races with loaded results from 2024–2026 using the
existing v3 model and the replay inputs filled by the race-control history work.
No eligibility thresholds, evaluation windows or bootstrap policies were relaxed.
The 2026 data currently contains 12 completed rounds, through 23 August.

| Season | Races | Observed transitions | Eligible before | Eligible after | Races with estimates before → after |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2024 | 24 | 824 | 6 | 33 | 1 → 12 |
| 2025 | 24 | 819 | 23 | 23 | 12 → 12 |
| 2026 | 12 | 499 | 7 | 7 | 5 → 5 |
| Total | 60 | 2,142 | 36 | 63 | 18 → 29 |

The refresh adds 27 eligible stops (+75%), all in 2024. Coverage remains limited
because the model requires a complete green window, clean-air field references
and all settling offsets. More observed stops do not automatically support more
counterfactual estimates.

| First failed rule after refresh | Stops |
| --- | ---: |
| Non-green evaluation window | 702 |
| Insufficient old reference laps | 564 |
| Incomplete evaluation window | 267 |
| Unsupported compound | 264 |
| Incomplete warmup profile | 228 |
| Additional stop in window | 16 |
| Missing race replay | 15 |
| Insufficient new mature laps | 11 |
| Unsupported actual baseline | 6 |
| Noisy old stint model | 4 |
| Noisy new stint model | 2 |

These 2,079 exclusions are mutually exclusive first-failure counts. An incomplete
window can result from retirement or the race ending, and a reference shortage
can reflect traffic or peer availability. Neither should be presented as a
definite missing source feed. Replay availability is checked separately at race
level on the dashboard.

Monaco 2026 has no admitted replay because its position coverage failed the
existing replay quality gate. A previously unhandled empty replay crashed the
per-race pit timing builder. It now retains the observed transitions with no
published estimates: stops passing the earlier structural checks receive
`missing_race_replay`; earlier first-failure reasons remain unchanged.

The local before/after report is `data/pit-timing-refresh-20260911.json`. The
replacement dashboard snapshot version is
`20260911-pit-timing-history-2024-2026`. Publication checks reported zero violations
for bootstrap quality, extrapolation limits, summary/scenario consistency and
unsupported estimate suppression.

Validation also covered all 60 race scopes and 2,142 stop selections against the
exported snapshot: every stop resolves to seven scenario records and excluded
stops have no supported scenarios. Python tests, Ruff, Mypy, strict Evidence
sources and the strict production build passed. The local page returned HTTP
200 after restart. Visual browser verification was unavailable because no browser
was connected.

A shorter-window model remains a separate proposed study; it is not part of this
refresh and would need validation before adding estimates to this page.
