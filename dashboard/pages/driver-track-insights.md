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

```sql canonical_segments
select * from f1.driver_dna_microsectors
where driver_code < teammate_code
```

```sql race_features
select season, round, race_name,
    avg((driver_speed_kph + teammate_speed_kph) / 2) as average_speed_kph,
    avg((driver_brake_share + teammate_brake_share) / 2) * 100 as braking_density_pct,
    avg(case when (driver_throttle + teammate_throttle) / 2 >= 99 then 1 else 0 end) * 100 as full_throttle_pct,
    avg(case when (driver_speed_kph + teammate_speed_kph) / 2 <= 160 then 1 else 0 end) * 100 as low_speed_segment_pct,
    count(*) as segments
from ${canonical_segments}
group by season, round, race_name
```

```sql feature_thresholds
select
    quantile_cont(average_speed_kph, 0.67) as speed_high,
    quantile_cont(braking_density_pct, 0.67) as brake_high,
    quantile_cont(low_speed_segment_pct, 0.67) as low_speed_high
from ${race_features}
```

```sql archetypes
select features.*,
    case
        when average_speed_kph >= thresholds.speed_high
            and braking_density_pct < thresholds.brake_high then 'High-speed flow'
        when braking_density_pct >= thresholds.brake_high then 'Heavy braking'
        when low_speed_segment_pct >= thresholds.low_speed_high then 'Low-speed traction'
        else 'Balanced'
    end as circuit_archetype
from ${race_features} as features
cross join ${feature_thresholds} as thresholds
order by season desc, round desc
```

## Circuit map from the data

<ScatterPlot
    data={archetypes}
    x=average_speed_kph
    y=braking_density_pct
    series=circuit_archetype
    tooltipTitle=race_name
    xAxisTitle="pair-average speed (km/h)"
    yAxisTitle="braking sample density (%)"
    pointSize=30
/>

```sql archetype_counts
select circuit_archetype, count(*) as races
from ${archetypes} group by circuit_archetype order by races desc
```

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
select circuit_archetype, count(*) as races,
    median(teammate_relative_gain_sec) as median_gain_sec,
    avg(teammate_relative_gain_sec) as mean_gain_sec,
    avg(case when teammate_relative_gain_sec > 0 then 1 else 0 end) * 100 as positive_race_pct
from ${driver_race_gain}
group by circuit_archetype order by median_gain_sec desc
```

## Teammate-relative time by circuit archetype

<BarChart data={driver_archetype_fit} x=circuit_archetype y=median_gain_sec swapXY=true sort=false labels=true>
    <ReferenceLine y=0 label="matched teammate lap" />
</BarChart>

```sql technique_by_race
select evidence.season, evidence.round, evidence.race_name, archetypes.circuit_archetype,
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

<BarChart data={technique_by_race} x=race_name y=technique_z series=circuit_archetype sort=false>
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
    <BigValue data={stability_summary} value=direction_agreement_pct title="Direction agreement" fmt="0%" />
</Grid>

The pipeline validation command adds split-season, leave-one-race-out and
shuffled-label diagnostics. See the [Driver DNA validation protocol](https://github.com/denzlswaggin/f1-data-analytics/blob/main/docs/driver-dna-validation.md).

<RelatedAnalysis section="drivers" current="driver-track-insights" />
