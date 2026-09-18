---
title: Which Tyres Faded?
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Strategy analysis"
    title="Which tyres faded?"
    description="See every compound choice and pit window on a true lap axis, then separate raw fall-off from relative same-lap degradation."
    accent="strategy"
/>

<KeyInsight label="How to read the strategy chart">
Blocks show compound and stint length; ticks mark stint changes, including changes during red flags. Darkening indicates observed fall-off, while the relative chart below compares cars on the same lap and compound.
</KeyInsight>

```sql seasons
select distinct season
from f1.stint_strategy
order by season desc
```

```sql races
select distinct
    season,
    round,
    race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · ' || replace(race_name, ' Grand Prix', '') as race_label
from f1.stint_strategy
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose a race" description="Compare stint timing, compound choice and fall-off.">
    <Dropdown data={seasons} name=season value=season title="Season" />
    <DependentDropdown data={races} name=race value=round label=race_label order="round asc" title="Race" season={inputs.season.value} latest={true} preserveInitial={true} />
</FilterBar>

```sql tyre_coverage
select * from f1.data_coverage
where section = 'tyre_strategy'
    and season = cast(${inputs.season.value} as integer)
    and round = cast(${inputs.race.value} as integer)
```

<DataTrust data={tyre_coverage} sampleLabel="stints" entityLabel="Drivers" method="descriptive, unadjusted slope" />

```sql race_stints
select *
from f1.stint_strategy
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by finish_position, stint
```

<StintChart data={race_stints} title={`${inputs.season.value} ${inputs.race.label}`} />

## Relative fall-off

Each lap is compared with other cars on the **same race lap and compound** before
the tyre-age slope is fitted. This is a descriptive comparison, not an isolated tyre effect: fuel loads, traffic,
driver pace and tyre age can still differ between cars.

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

Recorded pit visits and compound sequences, ordered by official classification.
Stint changes during red flags are not counted as pit visits. A blank stop count means the source is unavailable.

```sql strategies
with stops as (
    select driver_id, count(*) as stops
    from f1.pit_strategy
    where season = ${inputs.season.value} and round = ${inputs.race.value}
    group by driver_id
)
select
    min(finish_position) as pos,
    driver_code,
    driver_name,
    max(case when coverage.status = 'available' then coalesce(stops.stops, 0) end) as stops,
    string_agg(compound, ' → ' order by stint) as strategy
from f1.stint_strategy as stints
left join stops on stops.driver_id = stints.driver_id
left join f1.source_coverage as coverage
    on coverage.resource = 'pitstops' and coverage.season = stints.season and coverage.round = stints.round
where stints.season = ${inputs.season.value} and stints.round = ${inputs.race.value}
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
