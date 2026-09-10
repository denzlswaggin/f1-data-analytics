# Shared pit context: validation results

Package 1 of [data-trust remediation](data-trust-remediation-plan.md).

Baseline snapshot: `20260910T2200-racecraft` at main `96fc7a2`.
Rebuilt snapshot: `20260910T2250-shared-pit-context`.
No external API backfill or new race ingestion was performed. Replay coverage
remains 39 races, with analytical lap staging covering 60 races. Latest represented
race date remains 2026-08-23; export time is not race-data freshness.

## Reproduced Monaco regression

2025 round 8, George Russell: the recorded pit visit at lap 62 has no stint
change. Both lap 62 and its following lap 63 were previously eligible clean-air
consistency observations. They are now excluded using `jolpica` evidence, with
`pit_in_lap` and `pit_out_lap` reasons respectively.

| Consistency model output | Before | After |
|---|---:|---:|
| Modelled laps | 19 | 17 |
| Unexplained slow-lap cost, seconds | 20.418104 | 0.855574 |
| Cost per ten modelled laps, seconds | 10.746371 | 0.503279 |
| Worst pace residual, seconds | 18.657294 | 1.599836 |

The trend and peer references are refitted after exclusions; the new value is
not obtained by simply subtracting the pit duration. These remain descriptive
model residuals, not an independently measured or causal driver time loss.

## Dataset-level checks

`marts.pit_lap_context` contains 67,388 race-lap rows: 4,161 observed pit-boundary
rows, 24 inferred-only boundary rows, 63,180 `no_pit_observed` rows and 23 `unknown`
rows. Boundary rows are not a count of stops. Historical FastF1 timestamp fields
are all null; observed provenance here is from existing Jolpica records.

Ten formerly included traffic laps are excluded:

- 2025 R6: ALB 26/27, ANT 26, SAI 26, TSU 27, VER 26/27.
- 2025 R8: RUS 62/63.
- 2025 R15: LEC 52.

| Mart | Before | After |
|---|---:|---:|
| Traffic lap evidence | 34,214 | 34,204 |
| Eligible consistency driver-races | 535 / 766 | 535 / 766 |
| Eligible pit-window matchups | 305 / 385 | 305 / 385 |
| Eligible tyre-settling candidates | 193 / 2,142 | 193 / 2,142 |
| Eligible pit-timing candidates | 41 / 2,142 | 41 / 2,142 |
| Eligible racecraft episodes | 1,824 / 6,166 | 1,819 / 6,136 |

Unchanged candidate counts do not imply that every underlying numeric output is
unchanged. Racecraft episodes can split or disappear when a pit boundary interrupts
a previously continuous battle; the remaining known racecraft defects are deferred
to package 3.

Reproduce cross-mart checks with:

```powershell
.\.venv\Scripts\python.exe scripts/check_pit_context.py data/dashboard/latest.duckdb
```

All checks returned zero violations: duplicate context keys, missing context for
traffic/consistency/tyre evidence, and pit boundaries included in traffic evidence,
eligible consistency laps, or eligible/baseline tyre observations.

Regression coverage includes no-tyre-change stops, nullable historical input,
additive warehouse migration, multiple evidence sources, missing/zero/negative
pit timing, additional stops in strategy windows, stale clean-air flags,
full/incremental parity and removal of an empty corrected partition.

## Remaining limitations

- Source completeness is not established by a missing pit record.
- Model robustness, confidence wording, race-control and racecraft defects from
  the audit are not resolved by this package.
- Existing full Dagster replay/overtake assets rebuild only `CURRENT_SEASON` and
  replace their marts. This validation used explicit all-season analytical CLI
  commands without rematerializing those ancestors; do not infer that a full
  asset-graph refresh preserves historical replay coverage. That orchestration
  issue needs a separate correction.
- These are code, data-contract and model-input checks, not independent annotation
  of every real-world pit visit or browser-interaction verification.
