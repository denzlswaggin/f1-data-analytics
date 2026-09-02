# F1 analytics dashboard

This Evidence project reads an immutable DuckDB snapshot from
`../data/dashboard/latest.duckdb`. It deliberately does not query the mutable
operational warehouse.

From the repository root, prepare the complete local data contract and start the
dashboard with:

```bash
make dashboard-dev
```

Preparation validates every published insight, exports a versioned snapshot,
and refreshes the Evidence source cache before Vite starts. If analytics marts
are missing or stale, rebuild them first:

```bash
make dbt-build
python -m analytics.cli ratings
python -m analytics.cli ratings-v2
python -m analytics.cli pace-profile
make dashboard-dev
```

For an already prepared snapshot, `npm run dev` performs a fast contract check
and then starts Evidence. A missing snapshot fails with a direct recovery command
instead of rendering SQL errors and `undefined` values in the browser.
