---
title: Compare Drivers Honestly
---

<AppNav />

Compare two drivers on the same season scale. Ratings are relative to the
connected teammate graph, not absolute lap-time predictions. Overlapping 90%
intervals are evidence that the ordering is uncertain.

```sql drivers
select distinct driver_id, driver_name
from f1.driver_ratings_v2
order by driver_name
```

<FilterBar title="Choose drivers" description="Ratings use seasons shared by both drivers.">
    <Dropdown data={drivers} name=driver_a value=driver_id label=driver_name defaultValue="max_verstappen" title="Driver A" />
    <Dropdown data={drivers} name=driver_b value=driver_id label=driver_name defaultValue="lewis_hamilton" title="Driver B" />
</FilterBar>

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

<RatingComparison data={comparison} title="Season-by-season teammate-normalised form" />

```sql comparison_probability
with driver_a as (
    select *, (rating_hi - rating_lo) / 3.2897 as rating_se
    from f1.driver_ratings_v2
    where driver_id = '${inputs.driver_a.value}'
),
driver_b as (
    select *, (rating_hi - rating_lo) / 3.2897 as rating_se
    from f1.driver_ratings_v2
    where driver_id = '${inputs.driver_b.value}'
)
select
    driver_a.season,
    driver_a.driver_name as driver_a,
    driver_b.driver_name as driver_b,
    driver_a.rating - driver_b.rating as rating_delta,
    case
        when driver_a.rating_se + driver_b.rating_se = 0 then
            case when driver_a.rating > driver_b.rating then 1.0 else 0.5 end
        else 1 / (1 + exp(
            -1.702 * (driver_a.rating - driver_b.rating)
            / sqrt(power(driver_a.rating_se, 2) + power(driver_b.rating_se, 2))
        ))
    end as probability_a_faster,
    case
        when driver_a.rating_lo <= driver_b.rating_hi
            and driver_b.rating_lo <= driver_a.rating_hi then 'Intervals overlap'
        else 'Intervals separated'
    end as evidence_status
from driver_a
inner join driver_b using (season)
order by season
```

```sql latest_probability
select * from ${comparison_probability} order by season desc limit 1
```

## Latest shared-season evidence

<BigValue data={latest_probability} value=probability_a_faster title="Approx. probability Driver A is faster" fmt="0.0%" />

The probability uses a logistic approximation to a normal distribution, derived
from each 90% bootstrap interval. It is an interpretation aid, not a new fitted model: shared smoothing
and correlation between the two ratings are not available from the published
summary table.

<DataTable data={comparison_probability} rows=30>
    <Column id=season fmt="0000" />
    <Column id=rating_delta title="A − B" fmt="+0.000;-0.000" />
    <Column id=probability_a_faster title="P(A faster)" fmt="0.0%" />
    <Column id=evidence_status title="Evidence" />
</DataTable>

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
