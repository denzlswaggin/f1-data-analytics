---
title: Who Gains on Sunday?
---

<AppNav />

The headline [driver rating](driver-ratings) is built from **qualifying** teammate gaps: one clean
lap, no traffic, no fuel, no tyre management. It says who is fastest on Saturday and
nothing about Sunday.

This page adds the race-pace counterpart. Teammates are compared on the **same lap
number** — identical fuel load — over green-flag laps on the **same compound** at a
similar tyre age, and those gaps are chained into a second rating with the same
least-squares solver. Setting the two side by side gives one number per driver:

<div class="text-center text-lg my-4">

**delta = race rating − qualifying rating**

</div>

Positive means a driver gains ground on the field once the race starts. Negative means
they flatter to deceive on Saturday. Both ratings are fitted over the **same seasons**,
so the comparison is like-for-like — and both are relative to the field, so a delta of
zero means "improves on Sunday exactly as much as the average driver does", not "no
improvement".

<KeyInsight label="How to read delta">
Positive means stronger relative race pace; negative means stronger relative qualifying pace. Zero is the field average, not “no improvement”.
</KeyInsight>

```sql profile_coverage
select * from f1.data_coverage where section = 'pace_profile'
```

<DataTrust data={profile_coverage} sampleLabel="directed race comparisons" entityLabel="Drivers" method="matched-season point estimates; interval pending" />

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
    seriesColors={{'Racer': '#4a97d6', 'Qualifying specialist': '#cf7a33'}}
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
select *
from (
    select *, 'top' as end_of_list from ${pace} order by delta desc limit 10
)
union all
select *
from (
    select *, 'bottom' as end_of_list from ${pace} order by delta asc limit 10
)
order by delta desc
```

Bars point right for drivers who gain on Sunday and left for those who lose. The zero
line is the field average, not "no change".

<BarChart
    data={movers}
    x=driver_name
    y=delta
    series=profile
    seriesColors={{'Racer': '#4a97d6', 'Qualifying specialist': '#cf7a33'}}
    swapXY=true
    sort=false
    xAxisTitle="delta (race rating − qualifying rating)"
>
    <ReferenceLine y=0 label="field average" />
</BarChart>

## Full table

<ExpandableSection title="View the full driver table">
<DataTable data={pace} rows=20 search=true>
    <Column id=delta_rank title="#" />
    <Column id=driver_name title="Driver" />
    <Column id=delta title="Delta" fmt='+0.000' contentType=colorscale colorScale={['#cf7a33', '#f5f5f5', '#4a97d6']} />
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
