# Racecraft coverage and season profiles

> Historical report: the September 14 [input-integrity correction](racecraft-integrity.md)
> supersedes the resolved counts below. This refresh did not establish complete
> upstream overtake processing for the expanded 2024 coverage.

The September 13, 2026 refresh reprocessed every race present in the existing
replay mart. It did not download additional timing data or relax the v3 battle
thresholds.

| Measure | Before | After |
| --- | ---: | ---: |
| Races with Racecraft summaries | 39 | 59 |
| Observed episodes | 6,136 | 9,117 |
| Eligible resolved episodes | 1,819 | 2,273 |
| Driver-race summaries | 776 | 1,163 |
| 2024 races with summaries | 4 | 24 |

The missing 2024 partitions were already present in the replay mart. The public
single-race builder previously replaced both complete Racecraft tables; it now
delegates to the partition-preserving builder. The historical cause of the
partial snapshot is not established, but this overwrite path can no longer
erase unrelated races. Publication checks now require summaries for every
driver-race with usable replay order, including those with no observed battles.

The full rebuild processes one race at a time to bound memory use and publishes
the combined results after all races have been computed.

## Interpreting the expanded views

Season profiles pool episode counts and recompute the same 90% Wilson intervals
as the race-level method. They do not average race percentages or intervals.
Rates still require five eligible resolved opportunities in the relevant role.
The intervals describe sampling uncertainty within this selected subset and do
not account for repeated encounters, detection errors or interrupted episodes.

| Season | Drivers | Eligible attack profile | Eligible defence profile | Both roles |
| --- | ---: | ---: | ---: | ---: |
| 2024 | 24 | 23 | 21 | 21 |
| 2025 | 21 | 21 | 21 | 21 |
| 2026 | 23 | 22 | 22 | 22 |

Observed pressure, episode counts and distinct opponents use all observed
episodes, including short and interrupted encounters. Those additional episodes
do not enter the conversion or defence denominator. Median time to pass uses
only eligible confirmed conversions.

Pair summaries combine both directions exactly once per episode. The detail
table retains attacker and defender roles. Repeated episodes can be fragments
of one encounter, so their count is not a count of independent attempts.

Tyre context comes from each driver's own lap at the episode start. The leader
may already have crossed the timing line. A positive tyre-age difference means
the attacker had older tyres. Missing or ambiguous lap records yield null
context rather than duplicated episodes. These fields are descriptive and do
not establish a causal tyre advantage.

## Coverage and reproduction

There are 60 races in the available race-lap data, of which 59 have replay.
Monaco 2026 (round 6) remains explicitly unavailable because it has no replay.
Across the replay-covered races, 28 driver-race feeds have no usable running
order. They appear in the coverage table rather than as zero-opportunity driver
profiles. No battles are fabricated for either case.

With a complete operational warehouse, refresh and verify with:

```powershell
.venv/Scripts/python.exe -m analytics.cli racecraft --all
.venv/Scripts/python.exe scripts/check_racecraft_battles.py data/warehouse/f1.duckdb
.venv/Scripts/python.exe scripts/dashboard_snapshot.py build --output-dir data/dashboard
npm --prefix dashboard run sources:strict
npm --prefix dashboard run build:strict
```

For this refresh the local operational warehouse lacked six unrelated Driver DNA
and track-fit tables already present in the published snapshot. The new snapshot
`20260913-racecraft-profiles` therefore used the previous published snapshot as
its base, replacing only `marts.racecraft_battles` and
`marts.racecraft_driver_summary` with the recomputed warehouse tables before
running the standard snapshot exporter. Other analytical datasets were retained.

The new Evidence sources `racecraft_profiles` and `racecraft_coverage` are
derived exports; they require no additional warehouse tables. A profile with
`round = 0` represents the season. Existing race-level mart fields and the
`racecraft-v3-continuity` detection method retain their meanings.

## Validation

Regression tests cover pooled rates and Wilson intervals, the five-opportunity
threshold, zero-opportunity drivers, distinct opponents, interruption handling,
directional pair details, per-driver tyre start laps, ambiguous/missing context,
coverage gaps and partition preservation. All 16 page queries also executed
against the refreshed snapshot for 60 race scopes and three season scopes;
pair totals and attack/defence denominators reconciled in every scope.

The snapshot contract and Racecraft publication checks passed. Evidence source
extraction and strict production build passed. The final verified Evidence bundle was
106.5 MB, below the 275 MB budget. Old generated assets were archived locally
before the clean build. Interactive visual verification was unavailable because
the browser runtime had no connected browser.
