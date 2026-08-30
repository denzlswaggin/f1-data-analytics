# Versioned dashboard snapshots

The public Evidence site never reads the mutable operational warehouse. After a
successful scheduled pipeline run, `Publish Dashboard Snapshot` exports the
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

To roll back, replace `latest.json` with a prior version's manifest. Consumers
will verify the referenced database before installing it.
