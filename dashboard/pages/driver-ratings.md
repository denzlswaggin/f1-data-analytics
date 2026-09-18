---
title: Teammate-Based Qualifying Ratings
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Driver intelligence"
    title="How do teammates compare in qualifying?"
    description="A teammate-normalised view of career pace and current form, with uncertainty kept visible instead of hidden behind a ranking."
    accent="drivers"
>
    <div slot="actions">
        <a href="/f1-data-analytics/driver-comparison/">Compare drivers</a>
        <a href="/f1-data-analytics/saturday-vs-sunday/">Saturday vs Sunday</a>
    </div>
</PageHeader>

<KeyInsight label="How to read the rating">
Higher is faster in the fitted teammate network. The model cannot fully separate driver and car performance. Individual 90% resampling intervals are shown with the estimates; overlapping or separated intervals alone are not a paired significance test.
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

## Career qualifying benchmark

The career fit pools each driver's observed years. Different careers cover
different seasons and teammate networks; this is not a same-era comparison.
The display minimum is 40 directed comparisons, not 40 independent race weekends.
Regularisation stabilises sparse connections but does not prove equal machinery.

<RatingIntervals data={top_drivers} title="Career estimates: at least 40 directed comparisons" />

<ExpandableSection title="View career leaderboard data">
<div style="overflow-x: auto; max-width: 100%;">
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
</div>
</ExpandableSection>

## Season form — dynamic model

Unlike the career-wide benchmark above, this model estimates a separate rating
for every driver-season. Adjacent seasons share information through a temporal
regulariser; whole race weekends are resampled together for the 90% interval.
On the expanding-window holdout it is only marginally better than the static
model, so read it as a form lens rather than a replacement leaderboard.

```sql rating_seasons
select distinct season from f1.driver_ratings_v2 order by season desc
```

<FilterBar title="Season rating" description="The year scopes the displayed driver-season estimates; the model is fitted jointly across years.">
    <QueryDropdown data={rating_seasons} name=rating_season value=season title="Season" />
</FilterBar>

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
where season = ${inputs.rating_season.value}
order by rank
```

<RatingIntervals data={latest_dynamic_ratings} title="Selected-season estimates and 90% weekend-bootstrap intervals" />

All published drivers in this season are shown. Small comparison counts indicate
limited support even when the regularised point estimate appears precise.

<ExpandableSection title="View selected-season rating data">
<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={latest_dynamic_ratings} rows=15>
    <Column id=rank title="#" />
    <Column id=driver_name title="Driver" />
    <Column id=rating fmt='0.000' />
    <Column id=rating_lo title="90% low" fmt='0.000' />
    <Column id=rating_hi title="90% high" fmt='0.000' />
    <Column id=form_delta title="YoY change" fmt='+0.000;-0.000' />
    <Column id=n_comparisons title="Head-to-heads" />
</DataTable>
</div>
</ExpandableSection>

## Explore a driver's season-by-season pace

```sql drivers_list
select distinct driver_id, driver_name
from f1.season_pace
order by driver_name
```

<FilterBar title="Explore one driver" description="Follow season-by-season form and teammate gap.">
    <QueryDropdown data={drivers_list} name=driver value=driver_id label=driver_name defaultValue="max_verstappen" title="Driver" />
</FilterBar>

```sql driver_dynamic_form
select
    season,
    driver_name,
    rating,
    rating_lo,
    rating_hi,
    form_delta,
    n_comparisons
from f1.driver_ratings_v2
where driver_id = '${inputs.driver.value}'
order by season
```

<RatingComparison data={driver_dynamic_form} title="Season rating and individual 90% intervals" />

<ExpandableSection title="View season rating data">
<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={driver_dynamic_form} rows=20>
    <Column id=season fmt='0000' />
    <Column id=rating fmt='0.000' />
    <Column id=rating_lo title="90% low" fmt='0.000' />
    <Column id=rating_hi title="90% high" fmt='0.000' />
    <Column id=form_delta title="YoY change" fmt='+0.000;-0.000' />
    <Column id=n_comparisons title="Head-to-heads" />
</DataTable>
</div>
</ExpandableSection>

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

{#if driver_seasons.length > 0}
<LineChart
    data={driver_seasons}
    title="Mean qualifying gap to teammate by season (negative = faster)"
    x=season
    y=mean_pace_gap
    yAxisTitle="pace gap %"
>
    <ReferenceLine y=0 label="level with teammate" />
</LineChart>
{:else}
No observed teammate-gap history is available for this driver.
{/if}

<ExpandableSection title="View teammate-gap data">
<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={driver_seasons}>
    <Column id=season fmt='0000' />
    <Column id=mean_pace_gap title="Mean gap %" fmt='0.000' />
    <Column id=teammate_win_pct title="Quali win %" fmt='0.0' />
    <Column id=races_compared title="Races" />
</DataTable>
</div>
</ExpandableSection>

---

[Read the rating definitions, resampling units and validation limits](methodology).

<RelatedAnalysis section="drivers" current="driver-ratings" />
