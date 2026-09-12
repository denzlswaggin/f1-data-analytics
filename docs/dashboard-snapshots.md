# Versioned dashboard snapshots

The public Evidence site never reads the mutable operational warehouse. After
Dagster's persistent round refresh finishes, `Publish Dashboard Snapshot` exports the
the explicit `DASHBOARD_CONTRACT` allowlist into an immutable DuckDB file,
validates it, calculates SHA-256, and can publish both database and manifest to
object storage. Raw tables that are not queried by the product, notably
`staging.stg_positions`, never enter the serving artifact.

On the September 2026 development snapshot this allowlist reduced the DuckDB
artifact from 1.05 GB to 124 MB (about 88%) without removing a dashboard source.
The exact size varies with replay coverage; the contract test verifies the
included table set rather than relying on that historical size.

Object layout:

```text
<snapshot root>/
  latest.json
  <version>/
    f1-dashboard-<version>.duckdb
    f1-dashboard-<version>.json
```

`latest.json` is only a pointer to an immutable, checksummed version. The Pages
workflow downloads that exact object, verifies its hash and structure, then runs
the dashboard data contract before Evidence starts. A failed export therefore
cannot replace the last known-good database.

The manifest records the source type, Git commit, pinned package versions,
methodology versions, row counts and checksum. Run `make data-audit` for a
read-only integrity, provenance and freshness report.

## Local workflow

```bash
make dbt-build
python -m analytics.cli ratings
python -m analytics.cli ratings-v2
make dashboard-snapshot
cd dashboard && npm run sources:strict && npm run build:strict
```

### Race-control history (2024–2026)

The race-control picker includes every race with loaded results in these seasons,
including races with no recognised neutralisation. Missing messages are shown
separately from a loaded feed with no intervention.

To fill historical gaps before exporting a snapshot:

```bash
python scripts/backfill_race_control.py --from-season 2024 --to-season 2026
python scripts/check_race_control_impact.py data/warehouse/f1.duckdb
make dashboard-snapshot
cd dashboard && npm run sources:strict && npm run build:strict
```

The backfill reuses existing message and position partitions, fetches missing
ones with FastF1, builds missing replays and recalculates race-control impact one
race at a time. Other race partitions are preserved. Incomplete replay feeds stay
excluded by the existing quality rules and are listed at the end of the run.
Upcoming races without loaded results are not added to the picker.

### Pit timing history (2024–2026)

After filling replay inputs, rebuild pit timing separately: its estimates are not
automatically refreshed by the race-control backfill. The command processes all
completed races, including races without replay, and preserves other partitions.

```bash
python scripts/backfill_pit_timing.py --report data/pit-timing-coverage.json
python scripts/check_robust_estimates.py data/warehouse/f1.duckdb
make dashboard-snapshot
cd dashboard && npm run sources:strict && npm run build:strict
```

Use `--from-season` and `--to-season` to restrict the default 2024–2026 range.
The report records the original race coverage before any writes and checkpoints
each completed partition. After an interrupted run, pass `--resume` with the same
report and season range. A fresh run requires a new report path so the baseline
cannot be overwritten accidentally. Resume assumes unchanged model code and inputs
for completed partitions; use a fresh report to recompute those partitions too.

The dashboard lists all completed races, shows season coverage and permits
inspection of excluded stops. Exclusion counts show the first failed rule, not
every possible problem; uncomputed diagnostics do not establish missing inputs.
See [the September coverage audit](pit-timing-coverage-20260911.md).

## Production configuration

Set repository variable `F1_DASHBOARD_SNAPSHOT_URI` to the object-store prefix
and configure separate least-privilege reader/writer roles. The publisher also
needs read-only Postgres credentials. Versioning and retention are configured on
the bucket by the production infrastructure; the workflow itself never deletes
an older snapshot.

Dagster is the only ingestion scheduler. Snapshot publication and Pages deploys
are intentionally manual while this remains a student project: both workflows
use `workflow_dispatch` and no successful snapshot run triggers a release. The
publisher fails closed if the persistent warehouse or required marts are
unavailable. Re-enable an automated release policy only after explicitly
deciding that the project is ready to operate as a public service.

To roll back, replace `latest.json` with a prior version's manifest. Consumers
will verify the referenced database before installing it.
