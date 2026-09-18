---
title: Which Pit Cycles Changed the Race?
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Strategy analysis"
    title="Which pit cycles changed the race?"
    description="Connect recorded pit-lane duration with the position swing around every stop and find the pit cycles worth investigating."
    accent="strategy"
/>

<KeyInsight label="What this can tell you">
Use the page to spot pit cycles worth investigating. Position swing is observed context, not proof of an undercut or strategic causality.
</KeyInsight>

```sql seasons
select distinct season
from f1.pit_strategy
order by season desc
```

```sql races
select distinct
    season,
    round,
    race_name,
    'R' || lpad(cast(cast(round as integer) as varchar), 2, '0') || ' · ' || replace(race_name, ' Grand Prix', '') as race_label
from f1.pit_strategy
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose a race" description="Inspect every pit cycle in the selected Grand Prix.">
    <QueryDropdown data={seasons} name=season value=season title="Season" />
    <DependentDropdown data={races} name=race value=round label=race_label order="round asc" title="Race" season={inputs.season.value} latest={true} preserveInitial={true} />
</FilterBar>

```sql pit_coverage
select * from f1.data_coverage
where section = 'pit_cycle'
    and season = ${inputs.season.value} and round = ${inputs.race.value}
```

<DataTrust data={pit_coverage} sampleLabel="recorded pit visits" entityLabel="Drivers" method="descriptive window; not counterfactual" />

```sql race_stops
select
    driver_name,
    stop_number,
    pit_lap,
    duration_sec,
    position_before,
    position_after,
    positions_gained
from f1.pit_strategy
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by pit_lap
```

```sql impact
select *
from f1.strategy_impact
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by pit_lap
```

## Position swing across each stop — {inputs.season.value} {inputs.race.label}

```sql driver_net
select
    driver_name,
    sum(positions_gained) as net_positions,
    count(*) as stops,
    round(avg(duration_sec), 2) as avg_stop_sec
from f1.pit_strategy
where season = ${inputs.season.value} and round = ${inputs.race.value}
    and positions_gained is not null
group by driver_name
order by net_positions desc
```

<BarChart
    data={driver_net}
    x=driver_name
    y=net_positions
    yAxisTitle="observed net position swing"
    swapXY=true
    labels=true
    sort=false
>
    <ReferenceLine y=0 label="no net position change" />
</BarChart>

## Pit-lane duration versus cycle outcome

This separates two facts that the previous net-position number mixed together:
how long the full pit-lane visit was relative to the race median, and what happened
to track position across the cycle. Stops within two lap numbers of a race-control
message mentioning a safety car, VSC or red flag are labelled separately. Message
proximity does not establish that an intervention affected that stop.

Jolpica duration includes pit entry and exit and can include red-flag time. It
does not isolate stationary service time or mechanic performance.
[Source definition](https://github.com/jolpica/jolpica-f1/blob/main/docs/endpoints/pitstops.md).

<ScatterPlot
    data={impact}
    x=stop_delta_sec
    y=positions_gained
    series=impact_label
    xAxisTitle="pit-lane duration versus race median (s)"
    yAxisTitle="observed positions gained"
    tooltipTitle=driver_name
    pointSize=24
>
    <ReferenceLine x=0 label="race-median pit-lane duration" />
    <ReferenceLine y=0 label="position held" />
</ScatterPlot>

<PitWindowLink season={inputs.season.value} race={inputs.race.value} />

## Every stop

The position window runs from one lap before to two laps after the visit.
Stops without both positions remain listed; their swing is unknown.

<ExpandableSection title="View every stop">
<DataTable data={race_stops} rows=20>
    <Column id=driver_name title="Driver" />
    <Column id=stop_number title="Stop" />
    <Column id=pit_lap title="Lap" />
    <Column id=duration_sec title="Pit-lane duration (s)" fmt='0.00' />
    <Column id=position_before title="Pos before" />
    <Column id=position_after title="Pos after" />
    <Column id=positions_gained title="Gained" />
</DataTable>
</ExpandableSection>

## Evidence by stop

<ExpandableSection title="View stop-level evidence">
<DataTable data={impact} rows=30 search=true>
    <Column id=driver_name title="Driver" />
    <Column id=stop_number title="Stop" />
    <Column id=pit_lap title="Lap" />
    <Column id=duration_sec title="Pit-lane duration (s)" fmt='0.00' />
    <Column id=stop_delta_sec title="vs race median" fmt='+0.00;-0.00' />
    <Column id=positions_gained title="Positions" fmt='+0;-0' />
    <Column id=impact_label title="Context" />
</DataTable>
</ExpandableSection>

Even a clean positive cycle is not automatically an undercut: rival stops,
traffic, tyre warm-up and retirements can still explain the movement. The chart
is designed to identify candidates for replay inspection, not award causal credit.

<RelatedAnalysis section="race" current="pit-strategy" season={inputs.season.value} race={inputs.race.value} />
