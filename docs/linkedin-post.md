# LinkedIn post (draft)

---

🏎️ Who's the fastest qualifier in F1 — once you take the car out of the equation?

I built a data platform to find out. The trick: teammates drive **identical
cars**, so the qualifying gap between them isolates driver skill. Chain those gaps
across the 2024–2026 seasons with a least-squares "Massey"
rating, and you get one three-season leaderboard:

1️⃣ George Russell
2️⃣ Oliver Bearman
3️⃣ Andrea Kimi Antonelli
The ranking measures *margin over teammate* in these three seasons. A debatable
result, on purpose.

The fun part is the number; the point is the engineering. It's a full modern data
stack, all reproducible:

🔹 Ingestion — rate-limited API client → partitioned Parquet
🔹 Warehouse — DuckDB (dev) + Postgres (prod)
🔹 dbt — tested, documented, cross-dialect models
🔹 Dagster — the whole graph orchestrated on a race-weekend schedule
🔹 Evidence.dev — a BI-as-code dashboard on GitHub Pages

Plus a second insight from FastF1 telemetry: race-level tyre degradation by
compound, shown with its sample coverage and limitations.

Code + live dashboard 👇
github.com/denzlswaggin/f1-data-analytics

#DataEngineering #dbt #Dagster #DuckDB #Formula1 #Analytics
