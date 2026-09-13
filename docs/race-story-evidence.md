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

The serving SQL changes do not rewrite immutable snapshot marts. The legacy
`mart_race_story` remains inside the snapshot and must not be interpreted as the
corrected dashboard model. Its upstream dbt implementation and broader downstream
coverage need a later coordinated rebuild. This is not platform-wide validation.

## Verification

`tests/test_race_story_evidence.py` executes the actual serving SQL against missing
and complete synthetic evidence. It checks preserved results, unknown counts,
minimum sample requirements, partial-field rank suppression and recorded visits.
All three changed source queries also execute on the full published snapshot.
The main pages display coverage counts, omit unsupported winner narratives and
label the fastest lap as the fastest loaded green lap rather than an official
fastest-lap claim. Source extraction and strict dashboard build verify rendering
contracts, not the truth of external timing feeds.
