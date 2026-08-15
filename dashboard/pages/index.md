---
title: F1 "True Pace" — Teammate-Normalised Driver Ratings
---

Teammates drive **identical machinery**, so the qualifying gap *between teammates*
isolates driver skill from the car. Those pairwise gaps are chained into one
cross-era leaderboard via a least-squares fit on the teammate graph. Higher
rating = faster than teammates. Data: 2006–2025, via Jolpica-F1.

```sql top_drivers
select
    rank,
    driver_name,
    rating,
    n_comparisons,
    first_season,
    last_season
from f1.driver_ratings
where n_comparisons >= 40
order by rating desc
limit 15
```

## Fastest qualifiers of the era

<BarChart
    data={top_drivers}
    title="Teammate-normalised pace rating (min. 40 head-to-heads)"
    x=driver_name
    y=rating
    swapXY=true
    sort=false
    labels=true
/>

<DataTable data={top_drivers} rows=15>
    <Column id=rank title="#" />
    <Column id=driver_name title="Driver" />
    <Column id=rating fmt='0.000' />
    <Column id=n_comparisons title="Head-to-heads" />
    <Column id=first_season title="From" fmt='0000' />
    <Column id=last_season title="To" fmt='0000' />
</DataTable>

## Explore a driver's season-by-season pace

```sql drivers_list
select distinct driver_id, driver_name
from f1.season_pace
order by driver_name
```

<Dropdown data={drivers_list} name=driver value=driver_id label=driver_name defaultValue="max_verstappen" />

```sql driver_seasons
select
    season,
    mean_pace_gap,
    teammate_win_pct,
    races_compared
from f1.season_pace
where driver_id = '${inputs.driver.value}'
order by season
```

<LineChart
    data={driver_seasons}
    title="Mean qualifying gap to teammate by season (negative = faster)"
    x=season
    y=mean_pace_gap
    yAxisTitle="pace gap %"
/>

<DataTable data={driver_seasons}>
    <Column id=season fmt='0000' />
    <Column id=mean_pace_gap title="Mean gap %" fmt='0.000' />
    <Column id=teammate_win_pct title="Quali win %" fmt='0.0' />
    <Column id=races_compared title="Races" />
</DataTable>

---

_Built with dbt + DuckDB; solved in Python. See the [repo README](https://github.com/denzlswaggin/f1-data-analytics) for methodology._
