# Production runbook

This is the smallest durable deployment of the platform: one Postgres instance
stores both the analytics warehouse and Dagster metadata, while named volumes
retain the Parquet lake, FastF1 cache, and compute logs. It is suitable for a
single-host portfolio deployment. A managed Postgres and object-store URI can
replace the local volumes without changing ingestion code.

## Start and verify

```bash
cp .env.production.example .env.production
# Set a unique F1_PG_PASSWORD and the current F1_CURRENT_SEASON.
make prod-up
make prod-smoke
```

Dagster is served on `http://localhost:3001`. Enable the
`race_weekend_refresh` schedule in Dagster after the first successful manual
materialization. The daemon, run history, event log, schedules, and sensor state
survive container restarts because Dagster storage uses Postgres.

`make prod-smoke` fails unless all containers are healthy, definitions load,
the current season has non-empty audit records for races/results/qualifying,
and the latest load is at most eight days old. For a direct check:

```bash
docker compose --env-file .env.production exec dagster-webserver \
  f1-ingest health --max-age-hours 192
```

## Routine operations

```bash
make prod-logs       # follow Postgres, webserver, and daemon
make prod-backup     # data/backups/f1.dump (warehouse + Dagster metadata)
make prod-down       # stops services but preserves every named volume
```

Copy `data/backups/f1.dump` off the host after each race weekend. The local lake
volume is a second recovery source for raw data; for a remote deployment set
`F1_LAKE_URI` to versioned object storage and apply its lifecycle/backup policy.

Do not use `docker compose down -v` during normal operation: `-v` deletes the
warehouse, lake, caches, and logs.

## Recover one corrupted or missing partition

The loader records one row in `raw.ingestion_partitions` for every successful
partition replacement. Inspect the affected resource and restore only that
season or round from Parquet:

```bash
# Season-grain Jolpica resource
docker compose --env-file .env.production exec dagster-webserver \
  f1-ingest restore-partition --resource results --season 2026

# Round-grain source; all sessions in the round are restored atomically
docker compose --env-file .env.production exec dagster-webserver \
  f1-ingest restore-partition --resource telemetry --season 2026 --round 8
```

Then materialize the affected downstream dbt assets and analytics assets in
Dagster. `mart_lap_telemetry` compares its stored `source_loaded_at` with the
partition audit, so late corrections rebuild the touched race without a full
telemetry refresh. Finish with `make prod-smoke`.

If the lake partition is also absent, rerun the matching ingestion asset for
that season in Dagster; API retries use exponential backoff. Empty responses are
not written, so they cannot replace a valid partition silently.

## Restore Postgres after host loss

Start a fresh stack, stop the Dagster services, and restore the custom-format
dump into the empty database. Restoring overwrites database state, so confirm
the target host and dump before running it.

```bash
docker compose --env-file .env.production stop dagster-webserver dagster-daemon
docker compose --env-file .env.production exec -T postgres \
  pg_restore --clean --if-exists --no-owner -U f1 -d f1 < data/backups/f1.dump
docker compose --env-file .env.production start dagster-webserver dagster-daemon
make prod-smoke
```

When database/user names differ, substitute the values from
`.env.production`. A restore drill should be run before relying on a backup.

## Incident checklist

1. Preserve logs and the failed Dagster run ID; do not delete volumes.
2. Run `f1-ingest health` and inspect the failing asset check.
3. Distinguish source outage, empty source data, warehouse failure, and a dbt
   data-test failure.
4. Retry transient source failures. Restore a known-good lake partition for
   corrupted warehouse rows.
5. Rebuild only affected downstream assets, run the smoke check, and record the
   cause and repair in the Dagster run notes or incident log.
