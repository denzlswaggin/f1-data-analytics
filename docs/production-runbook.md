# Production runbook

The Compose stack is the smallest durable deployment of the platform: one Postgres instance
stores both the analytics warehouse and Dagster metadata, while named volumes
retain the Parquet lake, FastF1 cache, and compute logs. It is suitable for a
single-host portfolio deployment. For a managed AWS data plane, use the
[reviewable Terraform template](../deploy/terraform/aws/README.md). The template
is not evidence that infrastructure has been deployed.

## Start and verify

```bash
cp .env.production.example .env.production
# Set a unique F1_PG_PASSWORD and the current F1_CURRENT_SEASON.
make prod-up
make prod-smoke
```

Dagster is served on `http://localhost:3001`. Enable the
`latest_round_refresh` schedule in Dagster after the first successful manual
materialization of the current season's `raw.races` asset. The schedule runs at
06:00 every Monday and selects the greatest round whose race date is before the
current day, so it never launches a whole-season FastF1 reload. The daemon, run
history, event log, schedules, and sensor state
survive container restarts because Dagster storage uses Postgres.

Dagster is the authoritative ingestion scheduler. GitHub Actions only exports a
read-only dashboard snapshot after the Monday run; it does not run a second,
ephemeral ingestion pipeline.

`make prod-smoke` fails unless all containers are healthy, definitions load,
the current season has non-empty audit records for races/results/qualifying,
and the latest load is at most eight days old. Each invocation appends its
results to `ops.pipeline_health_history`. For a direct check:

```bash
docker compose --env-file .env.production exec dagster-webserver \
  f1-ingest health --max-age-hours 192
```

Core sources are mandatory. If a deployment also promises heavy FastF1 data,
set `F1_HEALTH_REQUIRED_RESOURCES=laps,telemetry,positions,race_control`; only
listed sources become hard health gates. An ad-hoc policy can instead repeat
`--require-resource telemetry` on the CLI. This avoids reporting an intentionally
lightweight deployment as unhealthy.

Review recent availability and freshness outcomes with:

```sql
select checked_at, season, check_name, passed, detail
from ops.pipeline_health_history
order by checked_at desc, check_name;
```

Keep at least 30 days of this small table and graph the pass ratio and
`latest_load_age` detail in the platform monitor. Alert on any failed check and
on absence of a recorded check after the scheduled refresh window.

## Failure alerts

Set `F1_ALERT_WEBHOOK_URL` to an HTTPS endpoint owned by the incident system or
a Slack/PagerDuty relay. If it needs authentication, store
`F1_ALERT_WEBHOOK_BEARER_TOKEN` in the deployment secret manager. Dagster's
failure sensor posts an event, severity, message, run ID, and job name. It never
logs the endpoint or token. Test routing in a non-production channel by causing
a disposable Dagster test job to fail; a successful HTTP response proves
delivery, while webhook delivery errors remain visible in structured daemon
logs without hiding the original run failure.

## Routine operations

```bash
make prod-logs       # follow Postgres, webserver, and daemon
make prod-backup     # timestamped dump + SHA-256 manifest in data/backups
make prod-down       # stops services but preserves every named volume
```

`make prod-backup` writes to a partial filename, validates that `pg_dump`
produced bytes, atomically publishes the dump, and writes a checksum manifest.
Copy both files off the host after each race weekend. The local lake
volume is a second recovery source for raw data; for a remote deployment set
`F1_LAKE_URI` to versioned object storage and apply its lifecycle/backup policy.

Schedule the backup command after every refresh with the host scheduler or the
workload platform, and alert on a non-zero exit. A guarded
[crontab example](../deploy/cron/f1-maintenance.crontab.example) runs weekly
backups and a monthly drill; install it only after both commands succeed
interactively. Managed RDS point-in-time
backups and S3 versioning are additional recovery layers, not substitutes for a
portable dump. Do not put database passwords in command arguments; the tooling
passes `PGPASSWORD` only to the PostgreSQL child process.

Do not use `docker compose down -v` during normal operation: `-v` deletes the
warehouse, lake, caches, and logs.

The operational job is partitioned by `season × round_session` (for example,
`2026 × 8:R`). Dagster supports two multi-partition dimensions, so the second
dimension keeps the round and session together without losing either value. The
schedule uses the `R` (race) session and one latest-completed round; select any explicit
partition in Dagster to rerun a correction or backfill a missed weekend. It
refreshes the small season-level races/results/qualifying endpoints, ingests only
the selected round for laps, pit stops, weather, telemetry, positions,
race-control, and radio, then runs dbt and replaces only that race in replay and
overtakes. The existing `backfill_ingest` and `refresh_pipeline` jobs remain the
season-range interfaces for historical work.

Each of the ingest, dbt, and analytics steps publishes `duration_seconds`, its
configured budget, and utilisation in Dagster metadata. Defaults are 7,200 / 900
/ 900 seconds and can be changed with
`F1_ROUND_{INGEST,TRANSFORM,ANALYTICS}_BUDGET_SECONDS`. A budget breach fails the
run after recording the measurement; the writes are partition-idempotent, so a
retry is safe.

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

Then run that exact `season × round:R` partition of `round_refresh_job` in
Dagster. `mart_lap_telemetry` compares its stored `source_loaded_at` with the
partition audit, so late corrections rebuild the touched race without a full
telemetry refresh; replay and overtakes use the same targeted replacement
contract. Finish with `make prod-smoke`.

If the lake partition is also absent, rerun the matching ingestion asset for
that season in Dagster; API retries use exponential backoff. Empty responses are
not written, so they cannot replace a valid partition silently.

## Automated restore drill

Run a drill against each backup before relying on it:

```bash
make prod-restore-drill BACKUP=data/backups/f1-20260830T120000Z.dump
# Scheduler-friendly selection of the newest timestamped dump:
make prod-restore-drill-latest
```

The command verifies the manifest checksum, creates a randomly named temporary
database, restores with `--exit-on-error`, confirms the ingestion audit table is
queryable, and drops the temporary database even after failure. It never targets
the production database. The operator needs `CREATEDB`; grant that capability
to a dedicated restore-drill identity rather than the normal ingestion role.
Record the result and duration in the operations monitor. Run this at least
monthly and after PostgreSQL major-version or backup-tooling changes.

## Restore Postgres after host loss

Start a fresh stack, stop the Dagster services, and restore the custom-format
dump into the empty database. Restoring overwrites database state, so confirm
the target host and dump before running it.

```bash
docker compose --env-file .env.production stop dagster-webserver dagster-daemon
docker compose --env-file .env.production exec -T postgres \
  pg_restore --clean --if-exists --no-owner -U f1 -d f1 < data/backups/f1-20260830T120000Z.dump
docker compose --env-file .env.production start dagster-webserver dagster-daemon
make prod-smoke
```

When database/user names differ, substitute the values from
`.env.production`. Verify the adjacent checksum manifest and complete a restore
drill before using a dump in an incident.

## Managed data-plane notes

The AWS template keeps RDS private, encrypts it, delegates the master password
to Secrets Manager, retains automated backups, and prevents accidental destroy.
The lake bucket blocks public access, requires TLS, encrypts objects, and keeps
old versions for a bounded recovery window. Attach the emitted least-privilege
lake policy to the Dagster workload role and inject the RDS secret at runtime.

CloudWatch CPU and free-storage alarms can publish to an existing SNS topic via
`alarm_sns_topic_arn`. Add provider-native alarms for connection saturation,
replica/failover events, and backup failures according to the chosen RDS class.
Keep Terraform state in an encrypted, locked remote backend controlled by the
deployment organization.

## Incident checklist

1. Preserve logs and the failed Dagster run ID; do not delete volumes.
2. Run `f1-ingest health` and inspect the failing asset check.
3. Distinguish source outage, empty source data, warehouse failure, and a dbt
   data-test failure.
4. Retry transient source failures. Restore a known-good lake partition for
   corrupted warehouse rows.
5. Rebuild only affected downstream assets, run the smoke check, and record the
   cause and repair in the Dagster run notes or incident log.
