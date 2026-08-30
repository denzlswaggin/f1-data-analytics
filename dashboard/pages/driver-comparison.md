---
title: Compare Drivers
---

Compare two drivers on the same season scale. Ratings are relative to the
connected teammate graph, not absolute lap-time predictions. Overlapping 90%
intervals are evidence that the ordering is uncertain.

```sql drivers
select distinct driver_id, driver_name
from f1.driver_ratings_v2
order by driver_name
```

<Dropdown data={drivers} name=driver_a value=driver_id label=driver_name defaultValue="max_verstappen" />
<Dropdown data={drivers} name=driver_b value=driver_id label=driver_name defaultValue="lewis_hamilton" />

```sql comparison
select
    season,
    driver_name,
    rating,
    rating_lo,
    rating_hi,
    form_delta,
    n_comparisons
from f1.driver_ratings_v2
where driver_id in ('${inputs.driver_a.value}', '${inputs.driver_b.value}')
order by season, driver_name
```

<LineChart
    data={comparison}
    title="Season-by-season teammate-normalised form"
    x=season
    y=rating
    series=driver_name
    yAxisTitle="rating"
/>

<DataTable data={comparison} rows=40 download=true>
    <Column id=season fmt="0000" />
    <Column id=driver_name title="Driver" />
    <Column id=rating fmt="0.000" />
    <Column id=rating_lo title="90% low" fmt="0.000" />
    <Column id=rating_hi title="90% high" fmt="0.000" />
    <Column id=form_delta title="YoY change" fmt="+0.000;-0.000" />
    <Column id=n_comparisons title="Head-to-heads" />
</DataTable>

## Career benchmark

```sql career
select driver_name, rank, rating, rating_lo, rating_hi, n_comparisons, first_season, last_season
from f1.driver_ratings
where driver_id in ('${inputs.driver_a.value}', '${inputs.driver_b.value}')
order by rating desc
```

<DataTable data={career} rows=2 download=true />
