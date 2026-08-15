# LinkedIn post (draft)

---

🏎️ Who's the fastest qualifier in F1 — once you take the car out of the equation?

I built a data platform to find out. The trick: teammates drive **identical
cars**, so the qualifying gap between them isolates driver skill. Chain those gaps
across every team and every season (2006–2025) with a least-squares "Massey"
rating, and you get one cross-era leaderboard:

1️⃣ Max Verstappen
2️⃣ George Russell
3️⃣ Charles Leclerc
…and Lewis Hamilton mid-pack — because the metric measures *margin over your
teammate*, and his were always elite. A debatable result, on purpose.

The fun part is the number; the point is the engineering. It's a full modern data
stack, all reproducible:

🔹 Ingestion — rate-limited API client → partitioned Parquet
🔹 Warehouse — DuckDB (dev) + Postgres (prod)
🔹 dbt — tested, documented, cross-dialect models
🔹 Dagster — the whole graph orchestrated on a race-weekend schedule
🔹 Evidence.dev — a BI-as-code dashboard on GitHub Pages

Plus a second insight from FastF1 telemetry: tyre degradation per compound
(soft falls off ~0.24 s/lap, hard barely at all — as expected).

Code + live dashboard 👇
github.com/denzlswaggin/f1-data-analytics

#DataEngineering #dbt #Dagster #DuckDB #Formula1 #Analytics
