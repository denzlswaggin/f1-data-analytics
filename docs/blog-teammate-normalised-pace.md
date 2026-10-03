# Who is the fastest qualifier in Formula 1? A teammate-normalised answer

*How do you compare drivers across different cars in the 2024–2026 seasons? You use the
shared-car comparison available each weekend: teammates. Setup, upgrades and
race conditions can still differ; this is not a controlled experiment.*

---

## The problem

Raw qualifying results can't tell you who's fastest, because they're dominated by
the car. Verstappen on pole tells you as much about Red Bull as about Verstappen.
Comparing teammates reduces shared car effects. It does not fully isolate driver
skill from setup, equipment differences, traffic or reliability.

## The method

**1. Teammate gaps.** For each race I compare the two drivers of a team in the
*last knockout session both set a time in* (Q3 if both reached it, else Q2, else
Q1) — the fair, apples-to-apples comparison. The gap is expressed as an additive
log-pace difference:

```
pace_gap = 100 × ( ln(t_driver) − ln(t_teammate) )
```

This is antisymmetric (`gap_ab = −gap_ba`) and additive along chains, which is the
property that lets it generalise.

**2. Chaining into one number.** Teammate gaps are local. To turn them into a
single three-season leaderboard I solve for a per-driver *pace deficit* `d` that best
explains every observed gap:

```
minimise   Σ ( d_i − d_j − gap_ij )²
```

That's a Massey-style least-squares rating on the teammate graph. Because the
graph connects drivers across seasons, the fitted comparison extends to drivers
who never shared a car. Connectivity does not make those comparisons causal. I solve
it with damped Jacobi iteration and add empirical-Bayes shrinkage so drivers with
only a handful of teammate races don't top the board on noise.

## 2024–2026 example

| Rank | Driver           | Rating | Head-to-heads |
| ---: | ---------------- | -----: | ------------: |
|    1 | George Russell        |  0.465 |            61 |
|    2 | Oliver Bearman        |  0.273 |            37 |
|    3 | Andrea Kimi Antonelli |  0.164 |            37 |
|    4 | Esteban Ocon          |  0.164 |            56 |
|    5 | Nico Hülkenberg       |  0.099 |            60 |

*(drivers with at least 20 comparisons; higher = faster than teammates)*

Russell has the highest point estimate in this three-season example. That does
not establish a statistically certain first place: individual rating intervals
do not provide a rank probability. The model estimates relative pace through
the teammate network, with regularisation and substantial contextual limitations.

### Caveats
Qualifying only (single-lap pace, least polluted by strategy/reliability).
Teammate quality isn't uniform, and the shrinkage/normalisation choices move
borderline drivers by a few places. The point isn't a definitive GOAT ranking —
it's a *reproducible, debatable* one.

## The engineering behind it

The number is the fun part; the platform is the point. It's built as a modern data
stack, all reproducible:

- **Ingestion** — a rate-limited, retrying, auto-paginating client over the
  Jolpica-F1 API (the post-Ergast successor), landing partitioned Parquet, loaded
  idempotently into **DuckDB** (dev) and **Postgres** (prod).
- **Transform** — **dbt**: staging → intermediate → marts, tested and documented,
  running cross-dialect on both warehouses.
- **Solve** — the rating is a Python (numpy) least-squares step, unit-tested with a
  closed-form chain.
- **Orchestrate** — **Dagster** assets model the whole graph
  (`raw.* → dbt → ratings`) on a race-weekend schedule.
- **Serve** — an **Evidence.dev** dashboard (BI-as-code) deployed to GitHub Pages.

A second insight — **tyre degradation** (sec/lap fall-off per compound, from a
regression on FastF1 lap data) — reuses the same pipeline and describes selected race/compound associations. It does not establish a universal
compound ordering independent of fuel, weather and traffic.

*Code and live dashboard: [github.com/denzlswaggin/f1-data-analytics](https://github.com/denzlswaggin/f1-data-analytics)*
