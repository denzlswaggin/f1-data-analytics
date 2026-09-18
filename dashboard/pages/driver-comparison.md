---
title: Compare Drivers Honestly
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Driver intelligence"
    title="Compare drivers honestly."
    description="Compare season model estimates, their resampling ranges and the observations supporting each driver."
    accent="drivers"
/>

<KeyInsight label="How to read the comparison">
The difference describes two fitted ratings in shared seasons. Individual resampling ranges do not establish the uncertainty of their difference or the probability that one driver is faster.
</KeyInsight>

```sql drivers
select distinct driver_id, driver_name
from f1.driver_ratings_v2
order by driver_name
```

<FilterBar title="Choose drivers" description="Ratings use seasons shared by both drivers.">
    <Dropdown data={drivers} name=driver_a value=driver_id label=driver_name defaultValue="max_verstappen" title="Driver A" />
    <Dropdown data={drivers} name=driver_b value=driver_id label=driver_name defaultValue="hamilton" title="Driver B" />
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
    and season in (
        select season from f1.driver_ratings_v2 where driver_id = '${inputs.driver_a.value}'
        intersect
        select season from f1.driver_ratings_v2 where driver_id = '${inputs.driver_b.value}'
    )
order by season, driver_name
```

<RatingComparison data={comparison} title="Season-by-season teammate-normalised form" />

```sql shared_comparison
select
    a.season,
    a.driver_name as driver_a,
    b.driver_name as driver_b,
    a.rating - b.rating as rating_delta,
    a.rating_lo as a_lo, a.rating_hi as a_hi,
    b.rating_lo as b_lo, b.rating_hi as b_hi,
    a.n_comparisons as a_comparisons,
    b.n_comparisons as b_comparisons
from f1.driver_ratings_v2 a
inner join f1.driver_ratings_v2 b using (season)
where a.driver_id = '${inputs.driver_a.value}'
    and b.driver_id = '${inputs.driver_b.value}'
order by a.season
```

```sql latest_comparison
select * from ${shared_comparison} order by season desc limit 1
```

```sql pair_scope
select count(*) as shared_seasons, min(season) as first_season,
    max(season) as last_season
from ${shared_comparison}
```

<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={pair_scope}>
    <Column id=shared_seasons title="Shared seasons" />
</div>
    <Column id=first_season title="First" fmt="0000" />
    <Column id=last_season title="Last" fmt="0000" />
</DataTable>

Shared seasons align the displayed years, not the set of race weekends or
teammates. These drivers need not have raced in the same car, and the fitted
network links can be indirect. Sample counts below belong to each driver's
own observations; they are not a count of direct A-versus-B contests.

## Latest shared-season model comparison

{#if latest_comparison.length > 0}
<p>Season: <Value data={latest_comparison} column=season fmt="0000" /></p>
<div class="metric-grid">
<BigValue data={latest_comparison} value=rating_delta title="Model rating difference (A minus B)" fmt="+0.000;-0.000" />
</div>
{:else}
No shared season ratings are available for these drivers.
{/if}

Positive means Driver A has the higher fitted rating. The scale is the model's
relative rating scale, not an observed head-to-head lap-time difference.
The ranges below describe each driver's own bootstrap resamples. Joint resamples
and their correlation are not included in the published summaries, so this page
does not calculate a probability of either driver being faster or an interval for
the difference. Overlapping or separated individual ranges are not a paired test.

<ExpandableSection title="View shared-season estimates and sample counts">
<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={shared_comparison} rows=30>
    <Column id=season fmt="0000" />
</div>
    <Column id=rating_delta title="Model A minus B" fmt="+0.000;-0.000" />
    <Column id=a_lo title="A: 90% lower" fmt="0.000" />
    <Column id=a_hi title="A: 90% upper" fmt="0.000" />
    <Column id=b_lo title="B: 90% lower" fmt="0.000" />
    <Column id=b_hi title="B: 90% upper" fmt="0.000" />
    <Column id=a_comparisons title="A comparisons" />
    <Column id=b_comparisons title="B comparisons" />
</DataTable>
</ExpandableSection>

<ExpandableSection title="View and download season ratings">
<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={comparison} rows=40 download=true>
    <Column id=season fmt="0000" />
</div>
    <Column id=driver_name title="Driver" />
    <Column id=rating fmt="0.000" />
    <Column id=rating_lo title="90% resampling lower" fmt="0.000" />
    <Column id=rating_hi title="90% resampling upper" fmt="0.000" />
    <Column id=form_delta title="YoY change" fmt="+0.000;-0.000" />
    <Column id=n_comparisons title="Model comparisons" />
</DataTable>
</ExpandableSection>

## Career model benchmark

Career estimates pool each driver's full observed history, which can differ in
years and sample size. They are a separate context from the shared-season comparison.

```sql career
select driver_name, rank, rating, rating_lo, rating_hi, n_comparisons, first_season, last_season
from f1.driver_ratings
where driver_id in ('${inputs.driver_a.value}', '${inputs.driver_b.value}')
order by rating desc
```

<ExpandableSection title="View career benchmark">
<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={career} rows=2 download=true />
</div>
</ExpandableSection>

<RelatedAnalysis section="drivers" current="driver-comparison" />
