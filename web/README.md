# F1 Analytics web replay

The SvelteKit proof of concept replaces the Evidence presentation layer for the
race replay while keeping the immutable DuckDB snapshot as its source of truth.

From an activated project virtual environment, generate the browser bundles and
start the app:

```bash
npm install
npm run data
npm run dev
```

`npm run data` verifies `data/dashboard/latest.duckdb` against its SHA-256
manifest, validates the replay contract and writes one Arrow/JSON pair per race
under `static/data`. Generated data is ignored by Git.

Checks:

```bash
npm run check
npm test
npm run build
```

The production build uses the `/f1-data-analytics` GitHub Pages base path. During
development the application is served from `/`.
