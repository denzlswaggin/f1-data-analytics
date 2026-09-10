# Race-control v2: validation and limits

Package 2 of [the remediation plan](data-trust-remediation-plan.md), on
`fix/race-control-comparability`, after merged PR #69 (`ca1cf1c`).
Baseline snapshot: `20260910T2250-shared-pit-context`.
New snapshot: `20260910-race-control-v2`.

## Publication rules

- Estimated total lap distance is `lap_number - 1 + lap_progress`. Compare leader
  and driver only at the same replay timestamp. Its nonnegative whole-lap part
  estimates lap deficit; missing timing, inconsistent ordering or distance within
  0.02 laps of a positive integer is unknown, not a confirmed lapping event.
- Keep position eligibility separate from time eligibility. Changed or unknown
  deficits suppress time comparison, not otherwise valid position evidence.
  Red flags publish position evidence only.
- Publish median-centred gap changes only with at least five individually
  time-comparable drivers. The cohort count and exclusion reason are stored on
  both event and driver rows and shown on the dashboard. Five is a publication
  safeguard, not a validated confidence threshold.
- Keep the original fixed third leader crossing after the end signal. Verify
  two complete, timed, contiguous green laps of the reference leader, with the
  same driver leading at the first and third crossings. Missing reference timing,
  stale end-signal leader observations, or another neutralisation rejects recovery.
- Use actual lap timestamps, not equal-number laps of different drivers. Any
  contradictory or missing-status lap wholly contained in the recovery interval
  rejects it. An unfinished lap starting inside it also rejects it when its end
  cannot be bounded by the next observed lap start.
- A flag on a boundary-straddling lap cannot be localised to the recovery interval.
  Requiring every overlapping lap aggregate to be green would reject all events:
  trailing cars necessarily complete earlier SC laps after the leader's crossing.
  `recovery_clean` therefore means verified green reference laps with no conflicting
  wholly-contained evidence, **not** independently proven green full-field coverage.

## Reproduced Bahrain example

2025 round 4, event `2025-04-sc-01`, Russell:

| Quantity | Before | After |
|---|---:|---:|
| Gap at deployment / checkpoint | 8.61 / 1.35 s | unchanged |
| Estimated lap deficit before / after | 0 / 1 | 0 / 0 |
| Raw gap gain | suppressed | 7.26 s |
| Median-centred relative gap gain | suppressed | -30.33 s |
| Comparable time cohort | 1 | 20 |

At the checkpoint Piastri is at lap 38 plus progress 0.0002, Russell at lap 37
plus progress 0.9860: their distance difference is 0.0142 laps, not a whole lap.
The cohort median raw gain is 37.59 seconds. Russell's -30.33 is his raw change
relative to that median; it is **not** a causal loss or measured race-control cost.

## Rebuilt data

| Check | v1 | v2 |
|---|---:|---:|
| Events retained | 66 | 66 |
| Eligible position events | 50 | 41 |
| Eligible events lacking required green recovery | 9 | 0 |
| Driver observations retained | 1,169 | 1,169 |
| Eligible position observations | 907 | 748 |
| Published median-centred time observations | 301 | 642 |

V2 publishes time evidence for 38 events, with cohorts from 7 to 21 drivers.
The remaining three position-eligible events have no usable time cohort. No
small cohort is shown as a misleading zero-gain headline. All excluded event
and driver observations remain available for inspection.

No new races were ingested and unrelated marts were not recomputed. Replay
coverage remains 39 races, latest represented race date 2026-08-23.

## Reproduction and tests

```powershell
.\.venv\Scripts\python.exe -m analytics.cli race-control-impact --all
.\.venv\Scripts\python.exe scripts/check_race_control_impact.py data/warehouse/f1.duckdb
```

The read-only checker enforces clean eligible recovery, minimum published cohort,
driver/event cohort agreement, per-driver exclusion reasons, and exact centering.
It returns zero violations on the rebuilt data. Synthetic regressions cover
finish-line seams, stable/lost whole laps, nullable progress, clock misalignment,
uncertain boundaries, cohorts of one/two/four/five, missing recovery records,
straddling SC laps, future untimed laps and stale leader timing. Snapshot tests
execute both SQL sources with empty sentinels and real position-only rows.

## Remaining limitations

Replay gaps and progress are reconstructed; no independent official-lapping
validation is claimed. Lap-status aggregates cannot locate every flag exactly.
The five-driver rule does not quantify statistical or selection uncertainty.
Existing pit labels still infer stops from stint/tyre transitions and are not
an exhaustive official pit-event count. This package does not resolve the
separate racecraft, presentation or model-robustness findings in packages 3–6.
