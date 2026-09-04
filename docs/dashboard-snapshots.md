# Versioned dashboard snapshots

The public Evidence site never reads the mutable operational warehouse. After
Dagster's persistent round refresh finishes, `Publish Dashboard Snapshot` exports the
`staging`, `intermediate`, and `marts` relations into an immutable DuckDB file,
validates it, calculates SHA-256, and publishes both database and manifest to
object storage.

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

## Local workflow

```bash
make dbt-build
python -m analytics.cli ratings
python -m analytics.cli ratings-v2
make dashboard-snapshot
cd dashboard && npm run sources:strict && npm run build:strict
```

## Production configuration

Set repository variable `F1_DASHBOARD_SNAPSHOT_URI` to the object-store prefix
and configure separate least-privilege reader/writer roles. The publisher also
needs read-only Postgres credentials. Versioning and retention are configured on
the bucket by the production infrastructure; the workflow itself never deletes
an older snapshot.

Dagster is the only ingestion scheduler. The previous GitHub Actions workflow
used an ephemeral DuckDB and discarded its data, so it was removed instead of
leaving a second scheduler that could race or imply durability. Snapshot export
runs at 08:00 UTC, two hours after Dagster's Monday refresh, and fails closed if
the persistent warehouse or its required marts are unavailable. A successful
snapshot workflow then triggers the Pages deployment, so a scheduled deployment
can never race the export or publish the previous snapshot by mistake. Pages can
still be deployed manually when an already-published snapshot needs rebuilding.

To roll back, replace `latest.json` with a prior version's manifest. Consumers
will verify the referenced database before installing it.
