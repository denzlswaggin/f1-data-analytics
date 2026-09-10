---
title: Who Was Fast in Clean Air?
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Race analysis"
    title="Who was fast in clean air?"
    description="Separate representative clean-air laps from traffic-exposed running, with replay coverage and sample confidence attached."
/>

<KeyInsight label="How to read this">
Lower clean-air controlled pace is faster. A positive traffic-associated delta means the driver's matched traffic laps were slower, but it is an observed association—not proof that dirty air caused the difference.
</KeyInsight>

```sql seasons
select distinct season
from f1.traffic_adjusted_pace
where season > 0
order by season desc
```

```sql races
select distinct
    round,
    race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') as race_label
from f1.traffic_adjusted_pace
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose a race" description="Only races with both green-flag lap timing and replay gaps are available.">
    <Dropdown data={seasons} name=season value=season title="Season" />
    <Dropdown data={races} name=race value=round label=race_label order="round asc" title="Race" />
</FilterBar>

```sql coverage
select * from f1.data_coverage
where section = 'traffic_pace'
    and race_label = (
        select cast(season as varchar) || ' ' || race_name
        from f1.traffic_adjusted_pace
        where season = ${inputs.season.value} and round = ${inputs.race.value}
        limit 1
    )
```

<DataTrust data={coverage} sampleLabel="eligible laps" entityLabel="Drivers" method="descriptive clean-air matching" />

```sql race_results
select
    *,
    rank() over (order by traffic_adjusted_pace_delta_sec nulls last) as clean_air_rank
from f1.traffic_adjusted_pace
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by traffic_adjusted_pace_delta_sec nulls last, driver_code
```

```sql clean_air_leader
select driver_code, traffic_adjusted_pace_delta_sec
from ${race_results}
where traffic_adjusted_pace_delta_sec is not null
order by traffic_adjusted_pace_delta_sec
limit 1
```

```sql exposure_leader
select driver_code, traffic_exposure_pct
from ${race_results}
order by traffic_exposure_pct desc nulls last
limit 1
```

```sql association_leader
select driver_code, traffic_associated_delta_sec_per_lap
from ${race_results}
where traffic_associated_delta_sec_per_lap is not null
order by traffic_associated_delta_sec_per_lap desc
limit 1
```

<Grid cols=3>
    <BigValue data={clean_air_leader} value=driver_code title="Fastest clean-air pace" />
    <BigValue data={exposure_leader} value=driver_code title="Highest traffic exposure" />
    <BigValue data={association_leader} value=driver_code title="Largest traffic association" />
</Grid>

## Clean-air pace ranking — {inputs.season.value} {inputs.race.label}

This is the median delta to at least two other drivers on the same lap and
compound, using only clean-air laps. A driver needs five clean laps before a
value is published.

<BarChart
    data={race_results}
    x=driver_code
    y=traffic_adjusted_pace_delta_sec
    yAxisTitle="clean-air controlled pace delta (s) — lower is faster"
    labels=true
>
    <ReferenceLine y=0 label="peer average" />
</BarChart>

## Traffic exposure versus associated pace

Exposure is tick-weighted across all eligible laps. The vertical measure pairs
each traffic lap with clean laps from the same driver and compound within two
laps of tyre age. The interval and confidence show how much evidence sits behind
the median.

```sql association
select *
from ${race_results}
where traffic_associated_delta_sec_per_lap is not null
```

<ScatterPlot
    data={association}
    x=traffic_exposure_pct
    y=traffic_associated_delta_sec_per_lap
    series=driver_code
    xAxisTitle="traffic exposure (% of valid replay ticks)"
    yAxisTitle="traffic-associated delta (s/lap)"
    chartAreaHeight=380
>
    <ReferenceLine y=0 label="no observed association" />
</ScatterPlot>

<DataTable data={race_results} rows=25 search=true download=true>
    <Column id=clean_air_rank title="Rank" />
    <Column id=driver_code title="Driver" />
    <Column id=team title="Team" />
    <Column id=traffic_adjusted_pace_delta_sec title="Clean-air pace (s)" fmt="+0.000;-0.000" />
    <Column id=traffic_exposure_pct title="Traffic (%)" fmt="0.0" />
    <Column id=traffic_associated_delta_sec_per_lap title="Associated Δ (s/lap)" fmt="+0.000;-0.000" />
    <Column id=traffic_associated_p25_sec title="P25 (s)" fmt="+0.000;-0.000" />
    <Column id=traffic_associated_p75_sec title="P75 (s)" fmt="+0.000;-0.000" />
    <Column id=clean_air_laps title="Clean laps" />
    <Column id=matched_traffic_laps title="Matched traffic laps" />
    <Column id=replay_coverage_pct title="Replay coverage (%)" fmt="0.0" />
    <Column id=confidence title="Confidence" />
</DataTable>

```sql drivers
select distinct driver_code
from f1.traffic_adjusted_laps
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by driver_code
```

<FilterBar title="Inspect the lap evidence" description="Mixed laps remain visible but never enter the clean-air headline.">
    <Dropdown data={drivers} name=driver value=driver_code title="Driver" />
</FilterBar>

```sql lap_evidence
select
    lap_number,
    air_state,
    compound,
    tyre_life,
    median_gap_to_ahead_s,
    replay_coverage_pct,
    controlled_pace_delta_sec,
    paired_traffic_delta_sec
from f1.traffic_adjusted_laps
where season = ${inputs.season.value}
    and round = ${inputs.race.value}
    and driver_code = '${inputs.driver.value}'
order by lap_number
```

<LineChart
    data={lap_evidence}
    x=lap_number
    y=controlled_pace_delta_sec
    series=air_state
    yAxisTitle="controlled pace delta (s)"
    chartAreaHeight=340
>
    <ReferenceLine y=0 label="peer average" />
</LineChart>

<ExpandableSection title="See every included lap and the v1 method">
<DataTable data={lap_evidence} rows=80 download=true />

Traffic is at least 50% of valid replay ticks within 1.5 seconds of a car ahead.
Clean air is at least 80% leading or three seconds clear, with no more than 10%
close traffic. Laps need 80% replay coverage; lap one, pit in/out laps, unknown
compounds and tyre life below two are excluded. Gaps are reconstructed from lap
timing and do not capture every lapped-car interaction, so this analysis must not
be read as a causal counterfactual finish result.
</ExpandableSection>

<RelatedAnalysis section="race" current="traffic-adjusted-pace" season={inputs.season.value} race={inputs.race.value} />
