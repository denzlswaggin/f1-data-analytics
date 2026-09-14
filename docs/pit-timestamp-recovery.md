# Observed pit timestamp recovery

The published `20260914-observed-persistence` snapshot contained 67,388 race
laps but no populated FastF1 pit-in/out timestamps. Existing exclusions relied
on recorded stops and stint boundaries. Cached FastF1 3.8.3 session processing
recovers 2,217 pit-in and 2,209 pit-out observations across all 60 loaded races.
These are source observations, not generated stops or independent video truth.

`analytics.pit_recovery.recover_pit_timestamps` requires identical lap keys,
driver numbers, lap starts, lap durations, stints, tyre ages and compounds before
filling missing timestamps. The numerical tolerance is one microsecond with no
relative tolerance. Compound comparison applies the existing `stg_laps.sql`
normalization, including missing values becoming `UNKNOWN`; original stored
values are preserved. Conflicting existing timestamps, invalid recovered times,
changed inputs, duplicate keys and missing/extra laps reject the entire race.

The first capture rejected Spa 2025 because raw missing compounds differed from
staging's `UNKNOWN`. The initial manifest is retained. Offline reconciliation
with the documented staging normalization accepts all 60 races without changing
any stored tyre value or fetching replacement observations.

Frozen normalized source Parquet, reconciled candidates and SHA-256 manifests
are in `validation/pit-recovery-20260914`. The manifest records the original
snapshot hash, FastF1 version and capture time. Capture time is when the cached
session was processed, not proof of upstream freshness. FastF1 cache warnings
and an auxiliary Jolpica rate limit do not establish full source coverage.
Raw upstream packet archives are not included; these are normalized FastF1
outputs. A missing timestamp stays missing.

Reconcile the frozen capture against the original baseline without networking:

```powershell
python -m scripts.recover_pit_timestamps `
  --snapshot path/to/original-baseline.duckdb `
  --source-capture validation/pit-recovery-20260914 `
  --output data/warehouse/new-pit-reconciliation
```

Omit `--source-capture` to process FastF1 sessions. Existing output directories
are refused. The command captures and reconciles only; it does not publish.
Publication requires rebuilding dependent pit, pace, tyre, race-control and
Racecraft analyses together and validating their evidence and processing receipts.

Recovered timestamps strengthen pit exclusions. They do not establish that every
modelled position exchange happened on track. A whole pit lap is a conservative
exclusion boundary, not an exact pit-lane interval; pass attribution still needs
aligned entry/exit intervals and reliable order observations.
