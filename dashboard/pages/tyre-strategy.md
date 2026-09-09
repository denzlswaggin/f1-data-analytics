---
title: Which Tyres Faded?
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Strategy analysis"
    title="Which tyres faded?"
    description="See every compound choice and pit window on a true lap axis, then separate raw fall-off from fuel- and track-adjusted degradation."
    accent="strategy"
/>

<KeyInsight label="How to read the strategy chart">
Blocks show compound and stint length. Darkening indicates observed fall-off, while the adjusted chart below removes much of the shared fuel and track trend.
</KeyInsight>

```sql seasons
select distinct season
from f1.stint_strategy
order by season desc
```

```sql races
select distinct
    round,
    race_name,
    'R' || cast(round as varchar) || ' · ' || replace(race_name, ' Grand Prix', '') as race_label
from f1.stint_strategy
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose a race" description="Compare stint timing, compound choice and fall-off.">
    <Dropdown data={seasons} name=season value=season title="Season" />
    <Dropdown data={races} name=race value=round label=race_label title="Race" />
</FilterBar>

```sql tyre_coverage
select * from f1.data_coverage
where section = 'tyre_strategy'
    and race_label = (
        select race_label
        from f1.stint_strategy
        where season = ${inputs.season.value} and round = ${inputs.race.value}
        limit 1
    )
```

<DataTrust data={tyre_coverage} sampleLabel="stints" entityLabel="Drivers" method="descriptive, unadjusted slope" />

```sql race_stints
select *
from f1.stint_strategy
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by finish_position, stint
```

<StintChart data={race_stints} title={`${inputs.season.value} ${inputs.race.label}`} />

## Fuel- and track-adjusted fall-off

Each lap is compared with other cars on the **same race lap and compound** before
the tyre-age slope is fitted. This removes much of the shared fuel-burn and track-
evolution trend that makes raw lap times look like tyre degradation.

```sql adjusted_deg
select *
from f1.adjusted_stint_degradation
where season = ${inputs.season.value} and round = ${inputs.race.value}
```

<ScatterPlot
    data={adjusted_deg}
    x=stint_length
    y=adjusted_deg_sec_per_lap
    series=compound
    xAxisTitle="comparable stint span (laps)"
    yAxisTitle="adjusted fall-off (s/lap)"
    tooltipTitle=driver_name
    pointSize=24
>
    <ReferenceLine y=0 label="stable residual pace" />
</ScatterPlot>

```sql cliff_stints
select *
from ${adjusted_deg}
where cliff_signal
order by late_stint_loss_sec desc
```

<ExpandableSection title="View stint degradation data">
<DataTable data={adjusted_deg} rows=40 search=true>
    <Column id=driver_code title="Driver" />
    <Column id=stint />
    <Column id=compound />
    <Column id=stint_length title="Span" />
    <Column id=adjusted_deg_sec_per_lap title="Adjusted s/lap" fmt="+0.000;-0.000" />
    <Column id=raw_deg_sec_per_lap title="Raw s/lap" fmt="+0.000;-0.000" />
    <Column id=late_stint_loss_sec title="Late loss (s)" fmt="+0.00;-0.00" />
    <Column id=cliff_signal title="Cliff" />
</DataTable>
</ExpandableSection>

The cliff flag requires at least 0.8 seconds of residual loss between the first
and final three comparable laps. It is a review signal, not a tyre-failure forecast.

## Strategy summary — {inputs.season.value} {inputs.race.label}

Number of stops and the compound sequence each driver ran, in finishing order.

```sql strategies
select
    min(finish_position) as pos,
    driver_code,
    driver_name,
    count(*) - 1 as stops,
    string_agg(compound, ' → ' order by stint) as strategy
from f1.stint_strategy
where season = ${inputs.season.value} and round = ${inputs.race.value}
group by driver_code, driver_name
order by pos
```

<ExpandableSection title="View strategy summary">
<DataTable data={strategies} rows=20>
    <Column id=pos title="Pos" align=center />
    <Column id=driver_code title="Driver" />
    <Column id=stops title="Stops" align=center />
    <Column id=strategy title="Compound sequence" />
</DataTable>
</ExpandableSection>

<RelatedAnalysis section="race" current="tyre-strategy" season={inputs.season.value} race={inputs.race.value} />
