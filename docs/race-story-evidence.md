# Race story serving correction

The published race story used `mart_race_story`, a legacy same-cell mean model
that did not use shared pit exclusions. It ranked even three-lap samples and
called a finish ahead of model rank an execution gain. Its pit count came from
stint count minus one, and absent pass analysis became zero detections.

The dashboard source now builds its story from all recorded results in loaded
lap scopes. Pace is the median of finite lap deltas in `traffic_adjusted_laps`:
these already apply shared pit exclusions and a leave-one-driver-out median
of at least three same-lap, same-compound peers. Publication requires five
comparable laps. Results without that evidence survive with a null pace rank.
Ranks cover eligible drivers only; finish/rank differences require the entire
result field to have an estimate. Their labels describe the numerical comparison,
not execution, skill or causation. Different lap samples remain a limitation.

Pass counts require a race processing receipt and at least some usable running
order for that driver. This distinguishes unavailable processing from a processed
zero, but does not certify complete driver coverage or correct physical events.
Pit counts are rows in the recorded pit-strategy input, not inferred tyre changes.
Races without any recorded stop input have unknown counts. A recorded zero is
not independently verified absence of a visit. Grid position zero is not used
as a numeric starting position in grid-gain arithmetic.

## Snapshot evidence

Evaluated on snapshot `20260914-racecraft-integrity` (SHA-256
`ead8a7cb49900b74da08e840d6c7e9724fab3e4c76aabe52124309f4a0f88664`):

- 1,222 result rows remain available; 470 have no publishable peer-pace estimate.
- 59 driver rows have unknown pass counts instead of an inferred zero.
- Only 15 race fields have pace estimates for every result driver.
- Monaco 2025 Russell changes from legacy mean delta +0.707544 s/rank 14 to
  pit-excluded median delta +0.314 s/rank 11. These are different estimands;
  the change cannot be attributed solely to one pit lap.
- Monaco Gasly has three comparable laps and no published rank, replacing the
  legacy rank 5. The result remains visible.
- Existing robust pace input covers only four 2024 races, all 24 in 2025 and
  eleven in 2026. Rebuilding missing analytical coverage remains necessary;
  the source does not silently fall back to the old model for uncovered races.

The initial serving correction did not rewrite the legacy snapshot mart. The
subsequent recorded-results migration below removes that remaining stale model.
This is not platform-wide validation.

## Coverage rebuild

The subsequent `20260914-peer-coverage` snapshot (SHA-256
`4b6a0eb4f683cc47c7e95f44b3c258d850d72e77881ec76981cbd5c08d1f632f`) rebuilds traffic pace, pace
consistency and tyre settling together from a separate copy of the operational
warehouse. The snapshot publication base preserves all other existing analytical
tables, including the Racecraft processing receipts and Driver DNA tables.

| Evidence | Before | After |
| --- | ---: | ---: |
| Traffic/consistency races | 39 | 59 |
| Comparable lap evidence | 33,136 | 51,084 |
| Driver/race summaries | 764 | 1,147 |
| 2024 covered races | 4 | 24 |
| Story rows lacking publishable pace | 470 | 90 |
| Complete pace fields | 15 | 25 |

All 1,222 result rows remain visible. The remaining 90 missing pace estimates
are not filled with model fallback. No additional timing observations were
invented and no peer/sample thresholds were relaxed. Monaco 2025 Russell lap 62
remains excluded. The three standard checks (`check_pit_context.py`,
`check_robust_estimates.py`, `check_metric_evidence.py`) report zero violations.
Racecraft receipt validation also passes on the publication candidate.

Reproduce the analytical dependency order on an isolated warehouse using
`build_all_traffic_adjusted_pace`, `build_all_pace_consistency`, then
`build_all_tyre_warmup` from `analytics.pipeline`, with the same explicit
`Settings(duckdb_path=...)`. Keep the copy's database filename `f1.duckdb`:
existing dbt views refer to that catalog name. Run the checks before promoting
the six resulting tables and exporting a new immutable snapshot version.

## Recorded-results migration

`mart_race_story` is now a compatibility table of recorded results, not a second
pace model. dbt builds all result rows in loaded lap scopes and counts recorded
pit visits. Its legacy pace, pace-rank and outcome/rank fields are null, its
pace-sample count is zero, and its methodology is `recorded-results-v1`.
Consumers needing the analytical story must use the corrected serving analysis;
the old columns must not be coalesced to zero or ranked. The dashboard's robust
peer-pace calculation and coverage remain intact.

The snapshot contract requires the new marker and the result identity columns
used by serving SQL. Validation rejects non-null retired estimates, old labels,
missing or extra result rows, duplicate result keys, and mismatches in finish or
classification against staging. These checks establish consistency with the
recorded source, not independent physical truth. The `20260914-recorded-results`
snapshot migrates all 1,222 compatibility rows while retaining the peer-coverage
rebuild and other analytical tables. Historical version files remain immutable.

Eight dbt data tests pass on the rebuilt operational copy. The executable SQL
regression preserves pit-lane grid semantics and stop counts; mutation tests
demonstrate rejection of a changed finish and a restored legacy pace rank.

## Verification

`tests/test_race_story_evidence.py` executes the actual serving SQL against missing
and complete synthetic evidence. It checks preserved results, unknown counts,
minimum sample requirements, partial-field rank suppression and recorded visits.
All three changed source queries also execute on the full published snapshot.
The main pages display coverage counts, omit unsupported winner narratives and
label the fastest lap as the fastest loaded green lap rather than an official
fastest-lap claim. Source extraction and strict dashboard build verify rendering
contracts, not the truth of external timing feeds.
