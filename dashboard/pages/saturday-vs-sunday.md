---
title: Who Gains on Sunday?
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Driver intelligence"
    title="Who gains on Sunday?"
    description="Compare fitted qualifying and race ratings, with paired intervals showing which differences remain uncertain."
    accent="drivers"
/>

Teammates are compared on the **same lap number**, compound and similar tyre age.
Those gaps are chained into a second rating with the same solver used for qualifying:

<div class="text-center text-lg my-4">

**delta = race rating − qualifying rating**

</div>

Both ratings are fitted over the **same seasons**. Eligible weekends and laps can
still differ, and the fitted scales do not isolate a causal driver effect.

<KeyInsight label="How to read delta">
Positive means a higher fitted race rating; negative means a higher fitted
qualifying rating. Zero means equal fitted ratings on these model scales. A
point estimate alone does not establish a supported difference.
</KeyInsight>

```sql profile_coverage
select * from f1.data_coverage where section = 'pace_profile'
```

<DataTrust data={profile_coverage} sampleLabel="directed race comparisons" entityLabel="Drivers" method="joint weekend bootstrap; 90% intervals" />

```sql min_races_options
select 5 as n union all select 10 union all select 20 union all select 30
```

<FilterBar title="Set evidence threshold" description="Higher thresholds trade coverage for stability.">
    <QueryDropdown data={min_races_options} name=minraces value=n defaultValue={10} title="Min. race comparisons" />
</FilterBar>

```sql pace
select *
from f1.driver_pace_profile
where n_race_comparisons >= ${inputs.minraces.value}
order by delta_rank
```

```sql diagonal
select
    min(least(quali_rating, race_rating)) as x1,
    min(least(quali_rating, race_rating)) as y1,
    max(greatest(quali_rating, race_rating)) as x2,
    max(greatest(quali_rating, race_rating)) as y2
from f1.driver_pace_profile
where n_race_comparisons >= ${inputs.minraces.value}
```

```sql difference_intervals
select driver_name, delta as rating,
    case when profile <> 'Interval unavailable' then delta_lo end as rating_lo,
    case when profile <> 'Interval unavailable' then delta_hi end as rating_hi,
    n_race_comparisons as n_comparisons
from ${pace}
order by delta desc, driver_id
```

```sql difference_evidence
select count(*) as drivers,
    count(*) filter (where profile='Positive difference') as positive,
    count(*) filter (where profile='Negative difference') as negative,
    count(*) filter (where profile='Inconclusive') as inconclusive,
    count(*) filter (where profile='Interval unavailable') as unavailable
from ${pace}
```

## Differences and paired uncertainty

<Grid cols=4>
    <BigValue data={difference_evidence} value=positive title="90% interval above zero" />
    <BigValue data={difference_evidence} value=negative title="90% interval below zero" />
    <BigValue data={difference_evidence} value=inconclusive title="Interval includes zero" />
    <BigValue data={difference_evidence} value=unavailable title="Interval unavailable" />
</Grid>

<RatingIntervals data={difference_intervals} valueLabel="race-minus-qualifying difference"
    title="Race minus qualifying: estimates and paired 90% intervals"
    note="Points are fitted differences; lines are paired 90% weekend-bootstrap intervals. * Interval unavailable. Counts are directed race comparisons." />

The intervals use the same resampled weekends within each season (1,000 draws,
seed 0) and require at least 900 valid paired solves. Missing intervals are not
zero-width certainty. Intervals touching or crossing zero are inconclusive about
the direction, even if the point estimate is large.

These are individual exploratory intervals, **not adjusted for screening multiple
drivers**. Some will exclude zero by chance; this is not a family-wide significance
claim or proof of a durable “Sunday specialist”. A barely positive lower endpoint
provides less separation from zero than a wider margin. Results are conditional
on the model and sample, not evidence of causal improvement.

<ExpandableSection title="Inspect the fitted qualifying and race ratings">
The diagonal marks equal fitted ratings, not equal real-world driver ability.
<ScatterPlot data={pace} x=quali_rating y=race_rating series=profile pointSize=30
    xAxisTitle="Qualifying rating" yAxisTitle="Race rating" tooltipTitle=driver_name>
    <ReferenceLine data={diagonal} x=x1 y=y1 x2=x2 y2=y2 label="equal fitted ratings" />
</ScatterPlot>
</ExpandableSection>

## Full table

<ExpandableSection title="View the full driver table">
<DataTable data={pace} rows=20 search=true>
    <Column id=delta_rank title="#" />
    <Column id=driver_name title="Driver" />
    <Column id=delta title="Delta" fmt='+0.000' contentType=colorscale colorScale={['#f7c948', '#26303d', '#32d3f4']} />
    <Column id=delta_lo title="90% lower" fmt="0.000" />
    <Column id=delta_hi title="90% upper" fmt="0.000" />
    <Column id=profile title="Evidence" />
    <Column id=bootstrap_valid_samples title="Valid draws / 1000" />
    <Column id=quali_rating title="Quali" fmt='0.000' />
    <Column id=race_rating title="Race" fmt='0.000' />
    <Column id=quali_rank title="Quali #" />
    <Column id=race_rank title="Race #" />
    <Column id=n_race_comparisons title="Directed race comparisons" />
    <Column id=first_season title="From" fmt='0000' />
    <Column id=last_season title="To" fmt='0000' />
</DataTable>
</ExpandableSection>

<ExpandableSection title="Read the limitations">
- **Race pace is noisier than qualifying.** A lap can be ruined by traffic, dirty air or
  a slow stop, none of which is driver pace. The comparability filters (same lap, same
  compound, tyre age within a few laps, outliers trimmed) remove most of that, but not
  all — and they also throw away a lot of laps. The race-comparison count is the eligible directed comparison count.
- **Only drivers with both ratings appear.** A rating needs a chain of teammate
  comparisons; drivers outside the largest connected component of either graph are
  excluded rather than guessed at.
- **This measures margin over a teammate**, not championship results. A driver in a
  weak car can rate highly, and a great driver paired with another great driver will
  rate lower than their reputation.
</ExpandableSection>

---

_Race pace from FastF1 per-lap timing; qualifying from Jolpica-F1. Gaps built in dbt,
both ratings solved in Python. See the [repo README](https://github.com/denzlswaggin/f1-data-analytics) for methodology._

<RelatedAnalysis section="drivers" current="saturday-vs-sunday" />
