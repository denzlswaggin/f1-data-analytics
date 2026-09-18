---
title: Who Gains on Sunday?
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Driver intelligence"
    title="Who gains on Sunday?"
    description="Compare teammate-normalised qualifying and controlled race pace over the same seasons to reveal racers and Saturday specialists."
    accent="drivers"
/>

Teammates are compared on the **same lap number**, compound and similar tyre age.
Those gaps are chained into a second rating with the same solver used for qualifying:

<div class="text-center text-lg my-4">

**delta = race rating − qualifying rating**

</div>

Both ratings are fitted over the **same seasons**, so the comparison is like-for-like.

<KeyInsight label="How to read delta">
Positive means stronger relative race pace; negative means stronger relative qualifying pace. Zero is the field average, not “no improvement”.
</KeyInsight>

```sql profile_coverage
select * from f1.data_coverage where section = 'pace_profile'
```

<DataTrust data={profile_coverage} sampleLabel="directed race comparisons" entityLabel="Drivers" method="joint weekend bootstrap; 90% intervals" />

```sql min_races_options
select 5 as n union all select 10 union all select 20 union all select 30
```

<FilterBar title="Set evidence threshold" description="Higher thresholds trade coverage for stability.">
    <Dropdown data={min_races_options} name=minraces value=n defaultValue={10} title="Min. race comparisons" />
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

## Where every driver sits

Each dot is a driver. The diagonal is "equally good on both days" — above it means the
driver is better in the race than in qualifying, below it the reverse. Distance from
the diagonal *is* the delta.

<ScatterPlot
    data={pace}
    x=quali_rating
    y=race_rating
    series=profile
    seriesColors={{'Racer': '#32d3f4', 'Qualifying specialist': '#f7c948'}}
    pointSize=30
    xAxisTitle="Qualifying rating (higher = faster)"
    yAxisTitle="Race rating (higher = faster)"
    tooltipTitle=driver_name
>
    <ReferenceLine
        data={diagonal}
        x=x1
        y=y1
        x2=x2
        y2=y2
        label="equal on both days"
        labelPosition=belowEnd
    />
</ScatterPlot>

## Biggest movers

```sql movers
select * from (
    select *, row_number() over (order by delta desc, driver_id) as top_rank,
        row_number() over (order by delta asc, driver_id) as bottom_rank
    from ${pace}
)
where top_rank <= 10 or bottom_rank <= 10
order by delta desc
```

Bars point right for drivers who gain on Sunday and left for those who lose. The zero
line is the field average, not "no change".

<BarChart
    data={movers}
    x=driver_name
    y=delta
    series=profile
    seriesColors={{'Racer': '#32d3f4', 'Qualifying specialist': '#f7c948'}}
    swapXY=true
    sort=false
    xAxisTitle="delta (race rating − qualifying rating)"
>
    <ReferenceLine y=0 label="field average" />
</BarChart>

Labels require the **90% difference interval** to exclude zero; otherwise the
result is inconclusive. Both ratings use the same resampled weekends within each
season (1,000 draws, seed 0). Intervals require at least 900 valid paired solves.
These intervals describe sampling variation, not causal improvement.

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
    <Column id=n_race_comparisons title="Races" />
    <Column id=first_season title="From" fmt='0000' />
    <Column id=last_season title="To" fmt='0000' />
</DataTable>
</ExpandableSection>

<ExpandableSection title="Read the limitations">
- **Race pace is noisier than qualifying.** A lap can be ruined by traffic, dirty air or
  a slow stop, none of which is driver pace. The comparability filters (same lap, same
  compound, tyre age within a few laps, outliers trimmed) remove most of that, but not
  all — and they also throw away a lot of laps. `Races` is the count that survived.
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
