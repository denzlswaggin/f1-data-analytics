# Race-control validation: every published race, 2024–2026

This audit covers every completed race offered by the Race-Control Impact page
in snapshot scope: 24 races in 2024, 24 in 2025 and 14 through the 2026 Spanish
Grand Prix. It validates source-to-mart reconciliation for the full population;
Madrid is a golden case, not a separate implementation path.

## Result

The frozen machine-readable report is
[`validation/race-control-2024-2026-audit-v1.json`](../validation/race-control-2024-2026-audit-v1.json).
Every race contains its source-message count, SHA-256 source-partition fingerprint,
deployment count, modelled events, boundary evidence, component availability and
explicit limitations.

| Season | Races | Source messages | Events | All components | Withheld components | No deployment marker | Source-limited |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2024 | 24 | 2,129 | 25 | 5 | 8 | 10 | 1 |
| 2025 | 24 | 2,178 | 31 | 8 | 9 | 6 | 1 |
| 2026 | 14 | 2,558 | 31 | 5 | 8 | 0 | 1 |
| **Total** | **62** | **6,865** | **87** | **18** | **25** | **16** | **3** |

All 87 source deployment markers reconcile exactly to 87 published events. Every
complete event end reconciles to an explicit end message, every superseded event
to the next deployment, and every finish-under-neutralisation event to the
chequered-flag timestamp. The audit reports zero structural violations.

`verified_no_neutralisation_marker` means that the loaded race-control partition
contains no supported SC, VSC or red-flag deployment marker. It does **not** infer
truth from silence and does not claim that no accident, local yellow or other
race-control action occurred.

## Source-limited races

Three races are retained with an explicit limitation instead of fabricated data:

- **[2024 Japanese GP](https://www.formula1.com/en/latest/article/verstappen-leads-home-perez-for-red-bull-one-two-at-japanese-gp-after-early.1rtPVvnBYJgZIEppNtk6ZD):**
  the source feed contains the lap-one red flag but no explicit
  standing/rolling-start marker. Formula 1's official report confirms
  the later standing restart. The event boundary and driver deltas remain withheld.
- **[2025 Belgian GP](https://www.formula1.com/en/latest/article/piastri-wins-wet-dry-belgian-gp-after-late-pressure-from-title-rival-and.7QmPcUP90MvR5iX0w3j91):**
  the red flag occurred during the aborted starting procedure,
  before a race baseline existed. The official report confirms the delayed start,
  red flag, subsequent Safety Car laps and racing from lap five. A driver-level
  before/after impact would be ill-defined.
- **[2026 Monaco GP](https://www.formula1.com/en/latest/article/antonelli-secures-brilliant-victory-in-chaotic-monaco-grand-prix-amid-multiple-shock-retirements.27e644586K83z0NZd6efsz.27e644586K83z0NZd6efsz):**
  the source contains two Safety Car deployments and a red flag,
  matching Formula 1's official report, but the position feed failed the existing
  replay coverage gate. No driver impact is published from incomplete replay.

## Boundary edge cases checked externally

Official Formula 1 race reports confirm the parser edge classes that caused the
former generic `No record` states:

- [Australia 2024](https://www.formula1.com/en/latest/article/sainz-storms-to-victory-amid-drama-in-australia-as-zhou-retires-and.4ZVm82EhKLMcVIHurBPr8N.4ZVm82EhKLMcVIHurBPr8N)
  and [Azerbaijan 2024](https://www.formula1.com/en/latest/article/piastri-edges-out-leclerc-for-dramatic-azerbaijan-gp-win-amid-late-race.3ZnRWkx1JNAx8lX8HbS2py)
  finished under VSC.
- [Canada 2025](https://www.formula1.com/en/latest/article/russell-takes-solid-victory-as-piastri-and-norris-collide-late-on-in.2cri9oFCALqhfsbvpqDfBq)
  finished under the Safety Car.
- [China 2024](https://www.formula1.com/en/latest/article/verstappen-charges-to-victory-over-norris-and-perez-in-action-packed-chinese.3Uz5CwNh5tEQt62umIGhob)
  changed from VSC to a full Safety Car.
- Japan 2024 restarted after the opening-lap red flag.
- Belgium 2025 was red-flagged before the racing start.
- Monaco 2026 contained two Safety Cars and a red flag.

These references supplement the population audit. Articles are positive edge-case
checks, not a complete negative oracle; the loaded Formula 1 live-timing messages
remain the population source for all 62 races.

The frozen external-probe pack contains 15 positive cases. All 15 have full source
coverage and exact-lap matches; it reports no false negatives or uncovered cases.
Population precision and false-positive rate remain deliberately unclaimed because
race-report prose is not an exhaustive negative annotation set.

## Reproduction

```bash
.venv/bin/python -m analytics.cli race-control-impact --all
.venv/bin/python scripts/audit_race_control_coverage.py \
  data/warehouse/f1.duckdb \
  --output validation/race-control-2024-2026-audit-v1.json
.venv/bin/python scripts/check_race_control_impact.py data/warehouse/f1.duckdb
```

The audit fails on missing race partitions, source deployments omitted from the
mart, invented mart events, or published boundaries that do not match an explicit
end, superseding deployment or chequered flag. Missing replay and missing source
end markers remain visible limitations and never become zero-valued effects.
