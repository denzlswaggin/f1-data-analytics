---
title: Who Is Fastest Beyond the Car?
---

<AppNav />

Teammate qualifying gaps reduce much of the shared car-performance effect, though
upgrades, setup, reliability and changing driver form remain possible confounders.
The pairwise gaps are chained into a cross-era leaderboard via a regularised
least-squares fit on the teammate graph. Higher rating = faster relative to
teammates. The interval is a 90% comparison-bootstrap interval, not a guaranteed
rank range.

<KeyInsight label="How to read the rating">
Higher is faster relative to teammates. Treat overlapping 90% intervals as an uncertain ordering, not a definitive rank.
</KeyInsight>

Compare two careers in [Compare Drivers](driver-comparison), contrast qualifying
and race pace in [Saturday vs Sunday](saturday-vs-sunday), or inspect the full
[methodology and data contract](methodology).

```sql rating_coverage
select * from f1.data_coverage where section = 'driver_rating'
```

<DataTrust data={rating_coverage} sampleLabel="directed comparisons" entityLabel="Drivers" method="regularised rating + 90% comparison bootstrap" />

```sql top_drivers
select
    rank,
    driver_name,
    rating,
    rating_lo,
    rating_hi,
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
    <Column id=rating_lo title="90% low" fmt='0.000' />
    <Column id=rating_hi title="90% high" fmt='0.000' />
    <Column id=n_comparisons title="Head-to-heads" />
    <Column id=first_season title="From" fmt='0000' />
    <Column id=last_season title="To" fmt='0000' />
</DataTable>

## Current form — dynamic model

Unlike the career-wide benchmark above, this model estimates a separate rating
for every driver-season. Adjacent seasons share information through a temporal
regulariser; whole race weekends are resampled together for the 90% interval.
On the expanding-window holdout it is only marginally better than the static
model, so read it as a form lens rather than a replacement leaderboard.

```sql latest_dynamic_ratings
select
    season,
    rank,
    driver_name,
    rating,
    rating_lo,
    rating_hi,
    form_delta,
    n_comparisons
from f1.driver_ratings_v2
where season = (select max(season) from f1.driver_ratings_v2)
order by rank
limit 15
```

<BarChart
    data={latest_dynamic_ratings}
    title="Latest-season teammate-normalised form"
    x=driver_name
    y=rating
    swapXY=true
    sort=false
    labels=true
/>

<DataTable data={latest_dynamic_ratings} rows=15>
    <Column id=rank title="#" />
    <Column id=driver_name title="Driver" />
    <Column id=rating fmt='0.000' />
    <Column id=rating_lo title="90% low" fmt='0.000' />
    <Column id=rating_hi title="90% high" fmt='0.000' />
    <Column id=form_delta title="YoY change" fmt='+0.000;-0.000' />
    <Column id=n_comparisons title="Head-to-heads" />
</DataTable>

## Explore a driver's season-by-season pace

```sql drivers_list
select distinct driver_id, driver_name
from f1.season_pace
order by driver_name
```

<FilterBar title="Explore one driver" description="Follow season-by-season form and teammate gap.">
    <Dropdown data={drivers_list} name=driver value=driver_id label=driver_name defaultValue="max_verstappen" title="Driver" />
</FilterBar>

```sql driver_dynamic_form
select
    season,
    rating,
    rating_lo,
    rating_hi,
    form_delta,
    n_comparisons
from f1.driver_ratings_v2
where driver_id = '${inputs.driver.value}'
order by season
```

<LineChart
    data={driver_dynamic_form}
    title="Dynamic rating by season (higher = faster)"
    x=season
    y=rating
    yAxisTitle="rating"
/>

<DataTable data={driver_dynamic_form} rows=20>
    <Column id=season fmt='0000' />
    <Column id=rating fmt='0.000' />
    <Column id=rating_lo title="90% low" fmt='0.000' />
    <Column id=rating_hi title="90% high" fmt='0.000' />
    <Column id=form_delta title="YoY change" fmt='+0.000;-0.000' />
    <Column id=n_comparisons title="Head-to-heads" />
</DataTable>

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
