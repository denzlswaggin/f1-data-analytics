---
title: Driver DNA
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Driver intelligence"
    title="Driver DNA: how fast laps are made."
    description="Compare representative fast-race-lap technique against the only car with the same machinery: the driver's teammate."
    accent="drivers"
/>

<KeyInsight label="Technique evidence—not a universal driving-style score">
Every point comes from the fastest telemetry-backed race lap available for both teammates, on the same dry compound, under green track status and within ten laps and ten tyre-life laps. The result describes this fast-race-lap sample; it does not separate the driver from setup, traffic history, fuel, tyre state or car behaviour.
</KeyInsight>

```sql seasons
select distinct season
from f1.driver_dna_evidence
where season > 0
order by season desc
```

```sql drivers
select distinct driver_code, driver_name
from f1.driver_dna_profile
order by driver_name
```

<FilterBar title="Compare technique profiles" description="The default 2025–2026 window balances recency with enough teammate evidence.">
    <Dropdown data={seasons} name=from_season value=season title="From season" defaultValue={2025} />
    <Dropdown data={seasons} name=to_season value=season title="To season" defaultValue={2026} />
    <Dropdown data={drivers} name=driver_a value=driver_code label=driver_name title="Driver A" defaultValue="VER" />
    <Dropdown data={drivers} name=driver_b value=driver_code label=driver_name title="Driver B" defaultValue="NOR" />
</FilterBar>

```sql selected_profiles
select *
from f1.driver_dna_profile
where driver_code in ('${inputs.driver_a.value}', '${inputs.driver_b.value}')
    and from_season = least(${inputs.from_season.value}, ${inputs.to_season.value})
    and to_season = greatest(${inputs.from_season.value}, ${inputs.to_season.value})
```

```sql profile_axes
select driver_name, 1 as metric_order, 'Full throttle distance' as metric_label,
       full_throttle_share as estimate, full_throttle_share_lo as lo, full_throttle_share_hi as hi
from ${selected_profiles}
union all
select driver_name, 2, 'Coasting distance', coasting_share, coasting_share_lo, coasting_share_hi from ${selected_profiles}
union all
select driver_name, 3, 'Braking distance', braking_share, braking_share_lo, braking_share_hi from ${selected_profiles}
union all
select driver_name, 4, 'Brake-onset speed', brake_onset_speed_kph, brake_onset_speed_kph_lo, brake_onset_speed_kph_hi from ${selected_profiles}
union all
select driver_name, 5, 'Low-speed corner speed', low_speed_kph, low_speed_kph_lo, low_speed_kph_hi from ${selected_profiles}
order by metric_order, driver_name
```

<DriverDNAProfile data={profile_axes} title="Teammate-normalised fast-race-lap technique" />

```sql profile_evidence
select driver_name, n_comparisons, n_teammates, n_seasons,
       cast(first_season as varchar) || '–' || cast(last_season as varchar) as seasons,
       confidence
from ${selected_profiles}
order by driver_name
```

{#if selected_profiles.length < 2}
<div class="dna-empty"><strong>Limited selection:</strong> one or both selected drivers do not have the five eligible races required for a published aggregate. Race-level evidence remains visible below when available.</div>
{/if}

<DataTable data={profile_evidence} rows=2>
    <Column id=driver_name title="Driver" />
    <Column id=n_comparisons title="Eligible races" />
    <Column id=n_teammates title="Teammates" />
    <Column id=n_seasons title="Seasons" />
    <Column id=seasons title="Evidence span" />
    <Column id=confidence title="Confidence" />
</DataTable>

## Race-by-race signature

Choose one technique axis. Each cell is a robust standard deviation from that race's actual teammate: teal means more, red means less. This is the evidence beneath the multi-race median, not a combined score.

```sql techniques
select * from (values
    ('full_throttle_share_z', 'Full throttle distance'),
    ('coasting_share_z', 'Coasting distance'),
    ('braking_share_z', 'Braking distance'),
    ('brake_onset_speed_kph_z', 'Brake-onset speed'),
    ('low_speed_kph_z', 'Low-speed corner speed')
) as techniques(metric, label)
```

<FilterBar title="Choose one technique" description="Keeping axes separate avoids hiding contradictory behaviours in a composite score.">
    <Dropdown data={techniques} name=technique value=metric label=label title="Technique" defaultValue="low_speed_kph_z" />
</FilterBar>

```sql race_heatmap
select
    cast(cast(season as integer) as varchar) || ' R'
        || lpad(cast(cast(round as integer) as varchar), 2, '0') as race_label,
    driver_name,
    teammate_name,
    case '${inputs.technique.value}'
        when 'full_throttle_share_z' then full_throttle_share_z
        when 'coasting_share_z' then coasting_share_z
        when 'braking_share_z' then braking_share_z
        when 'brake_onset_speed_kph_z' then brake_onset_speed_kph_z
        else low_speed_kph_z
    end as value,
    case '${inputs.technique.value}'
        when 'full_throttle_share_z' then 'Full throttle distance'
        when 'coasting_share_z' then 'Coasting distance'
        when 'braking_share_z' then 'Braking distance'
        when 'brake_onset_speed_kph_z' then 'Brake-onset speed'
        else 'Low-speed corner speed'
    end as metric_label
from f1.driver_dna_evidence
where eligible
    and season between least(${inputs.from_season.value}, ${inputs.to_season.value})
                   and greatest(${inputs.from_season.value}, ${inputs.to_season.value})
    and driver_code in ('${inputs.driver_a.value}', '${inputs.driver_b.value}')
order by season, round, driver_name
```

<DriverDNAHeatmap data={race_heatmap} title="Selected axis across eligible races" />

## Evidence in one lap

Select one of Driver A's eligible races. Their real teammate and representative lap are selected automatically; positive segment delta means Driver A gained time over that 200 m microsector.

```sql dna_races
select distinct
    season,
    round,
    cast(cast(season as integer) as varchar) || '-'
        || cast(cast(round as integer) as varchar) as race_key,
    cast(cast(season as integer) as varchar) || ' R'
        || lpad(cast(cast(round as integer) as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') || ' vs ' || teammate_name as race_label
from f1.driver_dna_evidence
where eligible
    and season between least(${inputs.from_season.value}, ${inputs.to_season.value})
                   and greatest(${inputs.from_season.value}, ${inputs.to_season.value})
    and driver_code = '${inputs.driver_a.value}'
order by season desc, round desc
```

<FilterBar title="Choose a representative lap" description="Only laps passing every same-compound, green-status and telemetry-coverage gate appear.">
    <Dropdown data={dna_races} name=dna_race value=race_key label=race_label title="Race and teammate" />
</FilterBar>

```sql selected_lap
select *
from f1.driver_dna_microsectors
where driver_code = '${inputs.driver_a.value}'
    and cast(cast(season as integer) as varchar) || '-'
        || cast(cast(round as integer) as varchar) = '${inputs.dna_race.value}'
order by segment_number
```

```sql lap_summary
select
    any_value(driver_name) as driver_name,
    any_value(teammate_name) as teammate_name,
    any_value(compound) as compound,
    any_value(driver_lap_number) as driver_lap,
    any_value(teammate_lap_number) as teammate_lap,
    sum(segment_delta_sec) as reconstructed_delta_sec
from ${selected_lap}
```

```sql largest_gain
select 'S' || cast(segment_number as varchar) as segment,
       segment_delta_sec,
       cast(round(start_distance_m) as varchar) || '–' || cast(round(end_distance_m) as varchar) || ' m' as distance
from ${selected_lap}
order by segment_delta_sec desc
limit 1
```

```sql largest_loss
select 'S' || cast(segment_number as varchar) as segment,
       segment_delta_sec,
       cast(round(start_distance_m) as varchar) || '–' || cast(round(end_distance_m) as varchar) || ' m' as distance
from ${selected_lap}
order by segment_delta_sec asc
limit 1
```

<Grid cols=3>
    <BigValue data={lap_summary} value=driver_name comparison=reconstructed_delta_sec comparisonFmt="+0.000;-0.000 s reconstructed" title="Selected driver" />
    <BigValue data={largest_gain} value=segment comparison=segment_delta_sec comparisonFmt="+0.000;-0.000 s" title="Largest 200 m gain" />
    <BigValue data={largest_loss} value=segment comparison=segment_delta_sec comparisonFmt="+0.000;-0.000 s" title="Largest 200 m loss" />
</Grid>

<DriverDNALap data={selected_lap} />

```sql evidence_rows
select season, round, race_name, driver_name, teammate_name, team, compound,
       driver_lap_number, teammate_lap_number, driver_tyre_life, teammate_tyre_life,
       common_points, valid_coverage_pct, throttle_corrections, gear_anomalies,
       confidence
from f1.driver_dna_evidence
left join ${selected_profiles} as profile using (driver_code, driver_name)
where eligible
    and season between least(${inputs.from_season.value}, ${inputs.to_season.value})
                   and greatest(${inputs.from_season.value}, ${inputs.to_season.value})
    and driver_code in ('${inputs.driver_a.value}', '${inputs.driver_b.value}')
order by season desc, round desc, driver_name
```

<ExpandableSection title="View evidence rows and methodology">
<DataTable data={evidence_rows} rows=40 search=true download=true>
    <Column id=season />
    <Column id=round />
    <Column id=race_name title="Race" />
    <Column id=driver_name title="Driver" />
    <Column id=teammate_name title="Teammate" />
    <Column id=compound />
    <Column id=driver_lap_number title="Driver lap" />
    <Column id=teammate_lap_number title="Teammate lap" />
    <Column id=common_points title="Common points" />
    <Column id=valid_coverage_pct title="Valid coverage (%)" fmt="0.0" />
    <Column id=confidence />
</DataTable>

Metrics are distance-weighted. Full throttle is ≥99%; coasting is ≤5% throttle with no brake. A brake onset needs at least 50 m without braking before it and 50 m of braking after it. Low-speed corner speed uses points where the pair-average speed is ≤160 km/h. Small interpolation overshoots in throttle are clamped to 0–100 and counted; gear anomalies are counted but do not affect the five metrics.

Each directed metric delta is scaled by 1.4826 × the global median absolute deviation. The driver estimate is the median across eligible races. Intervals are the 5th and 95th percentiles from 1,000 deterministic race-cluster bootstrap resamples. Confidence is limited for 5–7 comparisons, moderate for 8–11 and strong from 12; fewer than five are not published. No composite score or rank is calculated.
</ExpandableSection>

<RelatedAnalysis section="drivers" current="driver-dna" />
