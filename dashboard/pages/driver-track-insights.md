---
title: Driver Track Fit and DNA Stability
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Driver intelligence"
    title="Which technique profiles repeat across circuit types?"
    description="Group races by observed speed, braking and throttle mix, then test where teammate-relative Driver DNA signals persist."
    accent="driver"
/>

<KeyInsight label="Descriptive track fit">
Circuit groups are derived from the loaded representative laps, not from a fixed
FIA taxonomy. Positive time means the driver gained on the selected teammate
lap across the available microsectors. Car, setup and race state remain in the
signal, so this is evidence for investigation rather than a universal rating.
</KeyInsight>

```sql archetypes
select *, cast(season as varchar) || ' R' || cast(round as varchar) || ' ' || race_name as race_label
from f1.driver_track_archetypes
order by season desc, round desc
```

Classifications and their 67th-percentile thresholds are fixed in each published
snapshot under methodology `driver-track-v2-race-bootstrap`; page filters do not recalculate them.

## Circuit map from the data

<ScatterPlot
    data={archetypes}
    x=average_speed_kph
    y=braking_density_pct
    series=circuit_archetype
    tooltipTitle=race_label
    xAxisTitle="pair-average speed (km/h)"
    yAxisTitle="braking sample density (%)"
    pointSize=30
/>

```sql archetype_counts
select circuit_archetype, count(*) as races
from ${archetypes} group by circuit_archetype order by races desc
```

<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={archetypes} rows=20 search=true download=true>
    <Column id=season />
    <Column id=round />
    <Column id=race_name title="Race" />
    <Column id=circuit_archetype title="Archetype" />
    <Column id=average_speed_kph title="Avg speed" fmt="0.0" />
    <Column id=braking_density_pct title="Braking %" fmt="0.0" />
    <Column id=full_throttle_pct title="Full throttle %" fmt="0.0" />
    <Column id=low_speed_segment_pct title="Low-speed %" fmt="0.0" />
    <Column id=segments />
</DataTable>
</div>

```sql drivers
select distinct driver_code, driver_name
from f1.driver_dna_evidence where eligible
order by driver_name
```

```sql metrics
select 'full_throttle_share' as metric, 'Full throttle' as label
union all select 'coasting_share', 'Coasting'
union all select 'braking_share', 'Braking'
union all select 'brake_onset_speed_kph', 'Brake onset speed'
union all select 'low_speed_kph', 'Low-speed corner speed'
```

<FilterBar title="Inspect a driver" description="Compare one technique axis and its microsector time direction across derived circuit groups.">
    <Dropdown data={drivers} name=track_driver value=driver_code label=driver_name title="Driver" />
    <Dropdown data={metrics} name=track_metric value=metric label=label title="Technique axis" />
</FilterBar>

```sql driver_race_gain
select micro.season, micro.round, micro.race_name, archetypes.circuit_archetype,
    sum(micro.segment_delta_sec) as teammate_relative_gain_sec
from f1.driver_dna_microsectors as micro
join ${archetypes} as archetypes using (season, round)
where micro.driver_code = '${inputs.track_driver.value}'
group by micro.season, micro.round, micro.race_name, archetypes.circuit_archetype
```

```sql driver_archetype_fit
select * from f1.driver_track_fit
where driver_code = '${inputs.track_driver.value}' and interval_eligible
order by median_gain_sec desc
```

## Teammate-relative time by circuit archetype

{#if driver_archetype_fit.length > 0}
<BarChart data={driver_archetype_fit} x=circuit_archetype y=median_gain_sec swapXY=true sort=false labels=true>
    <ReferenceLine y=0 label="matched teammate lap" />
</BarChart>
{:else}
<KeyInsight label="More races needed">No circuit group has five comparable races for this driver. Inspect the individual races below.</KeyInsight>
{/if}

Only groups with at least five races appear above. Intervals are descriptive 90%
race-bootstrap intervals (1,000 draws, seed 0), not predictions for another circuit.

{#if driver_archetype_fit.length > 0}
<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={driver_archetype_fit}>
    <Column id=circuit_archetype title="Archetype" />
    <Column id=n_races title="Races" />
    <Column id=median_gain_sec title="Median (s)" fmt="0.000" />
    <Column id=median_gain_lo title="90% lower (s)" fmt="0.000" />
    <Column id=median_gain_hi title="90% upper (s)" fmt="0.000" />
</DataTable>
</div>
{/if}

Individual races, including groups below the threshold:
<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={driver_race_gain} rows=10 />
</div>

```sql technique_by_race
select evidence.season, evidence.round, evidence.race_name, archetypes.circuit_archetype,
    cast(evidence.season as varchar) || ' R' || cast(evidence.round as varchar) || ' ' || evidence.race_name as race_label,
    case '${inputs.track_metric.value}'
        when 'full_throttle_share' then full_throttle_share_z
        when 'coasting_share' then coasting_share_z
        when 'braking_share' then braking_share_z
        when 'brake_onset_speed_kph' then brake_onset_speed_kph_z
        when 'low_speed_kph' then low_speed_kph_z
    end as technique_z
from f1.driver_dna_evidence as evidence
join ${archetypes} as archetypes using (season, round)
where evidence.eligible and evidence.driver_code = '${inputs.track_driver.value}'
order by evidence.season, evidence.round
```

## Stability of the selected technique

<BarChart data={technique_by_race} x=race_label y=technique_z series=circuit_archetype sort=false>
    <ReferenceLine y=0 label="teammate baseline" />
</BarChart>

```sql stability_summary
select count(*) as races,
    median(technique_z) as median_z,
    avg(case when sign(technique_z) = sign((select median(technique_z) from ${technique_by_race})) then 1 else 0 end) * 100 as direction_agreement_pct
from ${technique_by_race}
```

<Grid cols=3>
    <BigValue data={stability_summary} value=races title="Comparable races" />
    <BigValue data={stability_summary} value=median_z title="Median robust-z" fmt="+0.00;-0.00" />
    <BigValue data={stability_summary} value=direction_agreement_pct title="Direction agreement (%)" fmt="0.0" />
</Grid>

The pipeline validation command adds split-season, leave-one-race-out and
shuffled-label diagnostics. See the [Driver DNA validation protocol](https://github.com/denzlswaggin/f1-data-analytics/blob/main/docs/driver-dna-validation.md).

<RelatedAnalysis section="drivers" current="driver-track-insights" />
