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
Every point comes from the fastest telemetry-backed race lap available for both teammates, on the same dry compound, under green track status and within three laps and three tyre-life laps. The result describes this fast-race-lap sample; it does not separate the driver from setup, traffic history, fuel, tyre state or car behaviour.
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
    <QueryDropdown data={seasons} name=from_season value=season title="From season" defaultValue={2025} />
    <QueryDropdown data={seasons} name=to_season value=season title="To season" defaultValue={2026} />
    <QueryDropdown data={drivers} name=driver_a value=driver_code label=driver_name title="Driver A" defaultValue="VER" />
    <QueryDropdown data={drivers} name=driver_b value=driver_code label=driver_name title="Driver B" defaultValue="NOR" />
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

## What defines Driver A?

These diagnostics turn the five-axis profile into testable statements. A stable
signature must point away from zero, repeat across races and survive both split-sample
and leave-one-race-out checks. Context-dependent traits have a directional aggregate
but fail at least one repeatability check; inconclusive traits overlap zero.

```sql selected_insight_profile
select *
from ${selected_profiles}
where driver_code = '${inputs.driver_a.value}'
```

```sql selected_stability
select *
from f1.driver_dna_stability
where driver_code = '${inputs.driver_a.value}'
    and from_season = least(${inputs.from_season.value}, ${inputs.to_season.value})
    and to_season = greatest(${inputs.from_season.value}, ${inputs.to_season.value})
```

```sql profile_traits
select driver_code, driver_name, 'full_throttle_share' as metric,
       'Full throttle distance' as metric_label, full_throttle_share as estimate,
       full_throttle_share_lo as lo, full_throttle_share_hi as hi
from ${selected_insight_profile}
union all
select driver_code, driver_name, 'coasting_share', 'Coasting distance',
       coasting_share, coasting_share_lo, coasting_share_hi from ${selected_insight_profile}
union all
select driver_code, driver_name, 'braking_share', 'Braking distance',
       braking_share, braking_share_lo, braking_share_hi from ${selected_insight_profile}
union all
select driver_code, driver_name, 'brake_onset_speed_kph', 'Brake-onset speed',
       brake_onset_speed_kph, brake_onset_speed_kph_lo, brake_onset_speed_kph_hi from ${selected_insight_profile}
union all
select driver_code, driver_name, 'low_speed_kph', 'Low-speed corner speed',
       low_speed_kph, low_speed_kph_lo, low_speed_kph_hi from ${selected_insight_profile}
```

```sql driver_traits
select
    traits.*,
    stability.n_races,
    stability.sign_agreement_pct,
    stability.split_delta,
    stability.leave_one_out_max_delta,
    case
        when stability.stable and (traits.lo > 0 or traits.hi < 0) then 'Stable signature'
        when traits.lo > 0 or traits.hi < 0 then 'Context-dependent'
        else 'Inconclusive'
    end as status,
    case
        when traits.metric = 'full_throttle_share' and traits.estimate >= 0 then 'More full-throttle distance'
        when traits.metric = 'full_throttle_share' then 'Less full-throttle distance'
        when traits.metric = 'coasting_share' and traits.estimate >= 0 then 'More coasting distance'
        when traits.metric = 'coasting_share' then 'Less coasting distance'
        when traits.metric = 'braking_share' and traits.estimate >= 0 then 'More braking distance'
        when traits.metric = 'braking_share' then 'Less braking distance'
        when traits.metric = 'brake_onset_speed_kph' and traits.estimate >= 0 then 'Higher speed at brake onset'
        when traits.metric = 'brake_onset_speed_kph' then 'Lower speed at brake onset'
        when traits.estimate >= 0 then 'Higher low-speed corner speed'
        else 'Lower low-speed corner speed'
    end as direction_text
from ${profile_traits} as traits
left join ${selected_stability} as stability using (driver_code, driver_name, metric)
order by
    case status when 'Stable signature' then 1 when 'Context-dependent' then 2 else 3 end,
    abs(estimate) desc,
    metric_label
```

{#if selected_insight_profile.length > 0}
<DriverDNAInsights data={driver_traits} />
{:else}
<div class="dna-empty"><strong>No publishable insight profile:</strong> Driver A needs at least five eligible races in the selected season window.</div>
{/if}

```sql driver_race_profiles
select
    season,
    round,
    any_value(race_name) as race_name,
    cast(cast(season as integer) as varchar) || ' R'
        || lpad(cast(cast(round as integer) as varchar), 2, '0') || ' · '
        || replace(any_value(race_name), ' Grand Prix', '') as race_label,
    string_agg(distinct teammate_name, ', ' order by teammate_name) as teammate_name,
    median(full_throttle_share_z) as full_throttle_share_z,
    median(coasting_share_z) as coasting_share_z,
    median(braking_share_z) as braking_share_z,
    median(brake_onset_speed_kph_z) as brake_onset_speed_kph_z,
    median(low_speed_kph_z) as low_speed_kph_z
from f1.driver_dna_evidence
where eligible
    and driver_code = '${inputs.driver_a.value}'
    and season between least(${inputs.from_season.value}, ${inputs.to_season.value})
                   and greatest(${inputs.from_season.value}, ${inputs.to_season.value})
group by season, round
order by season, round
```

```sql evolution_long
select season, round, race_name, race_label, teammate_name,
       'Full throttle distance' as metric_label, full_throttle_share_z as value
from ${driver_race_profiles}
union all
select season, round, race_name, race_label, teammate_name,
       'Coasting distance', coasting_share_z from ${driver_race_profiles}
union all
select season, round, race_name, race_label, teammate_name,
       'Braking distance', braking_share_z from ${driver_race_profiles}
union all
select season, round, race_name, race_label, teammate_name,
       'Brake-onset speed', brake_onset_speed_kph_z from ${driver_race_profiles}
union all
select season, round, race_name, race_label, teammate_name,
       'Low-speed corner speed', low_speed_kph_z from ${driver_race_profiles}
```

```sql evolution_indexed
select *, dense_rank() over (order by season, round) as race_index
from ${evolution_long}
```

```sql driver_evolution
select *,
    count(value) over technique_window as rolling_samples,
    case when count(value) over technique_window >= 3
         then median(value) over technique_window end as rolling_value
from ${evolution_indexed}
window technique_window as (
    partition by metric_label order by season, round
    rows between 4 preceding and current row
)
order by metric_label, season, round
```

{#if selected_insight_profile.length > 0}
<DriverDNAEvolution data={driver_evolution} />
{/if}

```sql race_distances
with differences as (
    select
        races.*,
        races.full_throttle_share_z - profile.full_throttle_share as d_full_throttle,
        races.coasting_share_z - profile.coasting_share as d_coasting,
        races.braking_share_z - profile.braking_share as d_braking,
        races.brake_onset_speed_kph_z - profile.brake_onset_speed_kph as d_brake_onset,
        races.low_speed_kph_z - profile.low_speed_kph as d_low_speed
    from ${driver_race_profiles} as races
    cross join ${selected_insight_profile} as profile
)
select *,
    sqrt((power(d_full_throttle, 2) + power(d_coasting, 2) + power(d_braking, 2)
        + power(d_brake_onset, 2) + power(d_low_speed, 2)) / 5) as profile_distance_z,
    case greatest(abs(d_full_throttle), abs(d_coasting), abs(d_braking),
                       abs(d_brake_onset), abs(d_low_speed))
        when abs(d_full_throttle) then 'Full throttle distance'
        when abs(d_coasting) then 'Coasting distance'
        when abs(d_braking) then 'Braking distance'
        when abs(d_brake_onset) then 'Brake-onset speed'
        else 'Low-speed corner speed'
    end as dominant_metric,
    case greatest(abs(d_full_throttle), abs(d_coasting), abs(d_braking),
                       abs(d_brake_onset), abs(d_low_speed))
        when abs(d_full_throttle) then d_full_throttle
        when abs(d_coasting) then d_coasting
        when abs(d_braking) then d_braking
        when abs(d_brake_onset) then d_brake_onset
        else d_low_speed
    end as dominant_delta
from differences
```

```sql race_insight_candidates
with leave_one_out as (
    select
        candidate.season,
        candidate.round,
        median(remaining.full_throttle_share_z) as loo_full_throttle,
        median(remaining.coasting_share_z) as loo_coasting,
        median(remaining.braking_share_z) as loo_braking,
        median(remaining.brake_onset_speed_kph_z) as loo_brake_onset,
        median(remaining.low_speed_kph_z) as loo_low_speed
    from ${driver_race_profiles} as candidate
    join ${driver_race_profiles} as remaining
      on candidate.season <> remaining.season or candidate.round <> remaining.round
    group by candidate.season, candidate.round
), influence_differences as (
    select
        distances.*,
        leave_one_out.loo_full_throttle - profile.full_throttle_share as i_full_throttle,
        leave_one_out.loo_coasting - profile.coasting_share as i_coasting,
        leave_one_out.loo_braking - profile.braking_share as i_braking,
        leave_one_out.loo_brake_onset - profile.brake_onset_speed_kph as i_brake_onset,
        leave_one_out.loo_low_speed - profile.low_speed_kph as i_low_speed
    from ${race_distances} as distances
    left join leave_one_out using (season, round)
    cross join ${selected_insight_profile} as profile
)
select *,
    sqrt((power(i_full_throttle, 2) + power(i_coasting, 2) + power(i_braking, 2)
        + power(i_brake_onset, 2) + power(i_low_speed, 2)) / 5) as influence_score_z,
    case greatest(abs(i_full_throttle), abs(i_coasting), abs(i_braking),
                       abs(i_brake_onset), abs(i_low_speed))
        when abs(i_full_throttle) then 'Full throttle distance'
        when abs(i_coasting) then 'Coasting distance'
        when abs(i_braking) then 'Braking distance'
        when abs(i_brake_onset) then 'Brake-onset speed'
        else 'Low-speed corner speed'
    end as influence_metric,
    case greatest(abs(i_full_throttle), abs(i_coasting), abs(i_braking),
                       abs(i_brake_onset), abs(i_low_speed))
        when abs(i_full_throttle) then i_full_throttle
        when abs(i_coasting) then i_coasting
        when abs(i_braking) then i_braking
        when abs(i_brake_onset) then i_brake_onset
        else i_low_speed
    end as influence_delta
from influence_differences
```

```sql race_insights
select * from (
    select 1 as insight_order, 'Most representative' as insight_label,
           race_label, teammate_name, dominant_metric, dominant_delta,
           profile_distance_z as score, 'Profile distance' as score_label
    from ${race_insight_candidates}
    order by profile_distance_z, season desc, round desc
    limit 1
)
union all
select * from (
    select 2, 'Most unusual', race_label, teammate_name, dominant_metric, dominant_delta,
           profile_distance_z, 'Profile distance'
    from ${race_insight_candidates}
    order by profile_distance_z desc, season desc, round desc
    limit 1
)
union all
select * from (
    select 3, 'Most influential', race_label, teammate_name, influence_metric, influence_delta,
           influence_score_z, 'Leave-one-out shift'
    from ${race_insight_candidates}
    where influence_score_z is not null
      and (select count(*) from ${driver_race_profiles}) >= 6
    order by influence_score_z desc, season desc, round desc
    limit 1
)
order by insight_order
```

{#if selected_insight_profile.length > 0}
<div class="dna-insight-section">
<h3>Which races define—or challenge—the profile?</h3>
<DriverDNARaceInsights data={race_insights} />
<p>Profile distance is the root-mean-square difference across all five robust-z axes.
The influential race is the one whose removal moves the five-axis median most; it
appears only when at least five races remain after removal.</p>
</div>
{/if}

## Driver vs. season average

Compare one published season profile with an equally weighted average of every
other driver who reached the five-race publication threshold in that season.
The peer benchmark excludes the selected driver, so it remains an independent
reference rather than partially averaging the driver back into their own comparison.

```sql benchmark_seasons
select from_season as season
from f1.driver_dna_profile
where from_season = to_season
group by from_season
having count(*) >= 2
order by season desc
```

```sql benchmark_drivers
select from_season as season, driver_code, driver_name
from f1.driver_dna_profile
where from_season = to_season
order by season desc, driver_name
```

<FilterBar title="Compare with the season field" description="Only drivers with at least five eligible teammate comparisons enter the equally weighted peer average.">
    <QueryDropdown data={benchmark_seasons} name=benchmark_season value=season title="Season" defaultValue={2025} />
    <DependentDropdown data={benchmark_drivers} name=benchmark_driver value=driver_code label=driver_name title="Driver" season={inputs.benchmark_season.value} defaultValue="VER" />
</FilterBar>

```sql selected_benchmark_profile
select *
from f1.driver_dna_profile
where from_season = ${inputs.benchmark_season.value}
    and to_season = ${inputs.benchmark_season.value}
    and driver_code = '${inputs.benchmark_driver.value}'
```

```sql benchmark_profile_rows
select
    1 as series_order,
    driver_name,
    full_throttle_share,
    full_throttle_share_lo,
    full_throttle_share_hi,
    coasting_share,
    coasting_share_lo,
    coasting_share_hi,
    braking_share,
    braking_share_lo,
    braking_share_hi,
    brake_onset_speed_kph,
    brake_onset_speed_kph_lo,
    brake_onset_speed_kph_hi,
    low_speed_kph,
    low_speed_kph_lo,
    low_speed_kph_hi
from ${selected_benchmark_profile}
union all
select
    2,
    'Season peer average',
    avg(full_throttle_share),
    null::double,
    null::double,
    avg(coasting_share),
    null::double,
    null::double,
    avg(braking_share),
    null::double,
    null::double,
    avg(brake_onset_speed_kph),
    null::double,
    null::double,
    avg(low_speed_kph),
    null::double,
    null::double
from f1.driver_dna_profile
where from_season = ${inputs.benchmark_season.value}
    and to_season = ${inputs.benchmark_season.value}
    and driver_code <> '${inputs.benchmark_driver.value}'
having count(*) > 0
```

```sql benchmark_profile_axes
select series_order, driver_name, 1 as metric_order, 'Full throttle distance' as metric_label,
       full_throttle_share as estimate, full_throttle_share_lo as lo, full_throttle_share_hi as hi
from ${benchmark_profile_rows}
union all
select series_order, driver_name, 2, 'Coasting distance', coasting_share, coasting_share_lo, coasting_share_hi from ${benchmark_profile_rows}
union all
select series_order, driver_name, 3, 'Braking distance', braking_share, braking_share_lo, braking_share_hi from ${benchmark_profile_rows}
union all
select series_order, driver_name, 4, 'Brake-onset speed', brake_onset_speed_kph, brake_onset_speed_kph_lo, brake_onset_speed_kph_hi from ${benchmark_profile_rows}
union all
select series_order, driver_name, 5, 'Low-speed corner speed', low_speed_kph, low_speed_kph_lo, low_speed_kph_hi from ${benchmark_profile_rows}
order by metric_order, series_order
```

<DriverDNAProfile data={benchmark_profile_axes} title="Season technique vs. qualified peer average" />

```sql benchmark_summary
select
    selected.from_season as season,
    selected.driver_name,
    selected.n_comparisons as eligible_races,
    selected.confidence,
    peers.peer_drivers
from ${selected_benchmark_profile} as selected
cross join (
    select count(*) as peer_drivers
    from f1.driver_dna_profile
    where from_season = ${inputs.benchmark_season.value}
        and to_season = ${inputs.benchmark_season.value}
        and driver_code <> '${inputs.benchmark_driver.value}'
) as peers
```

{#if benchmark_summary.length > 0}
<DataTable data={benchmark_summary} rows=1>
    <Column id=season />
    <Column id=driver_name title="Driver" />
    <Column id=eligible_races title="Eligible races" />
    <Column id=confidence title="Confidence" />
    <Column id=peer_drivers title="Drivers in peer average" />
</DataTable>
{:else}
<div class="dna-empty"><strong>No season benchmark:</strong> the selected season and driver do not have enough published teammate evidence.</div>
{/if}

The selected driver's line is their 90% race-cluster bootstrap interval. The peer
average is a point benchmark: individual profile intervals cannot be combined into
a valid interval for their mean from the published summary columns alone. Both
series remain on the teammate-normalised robust-z scale; this is not a field ranking.

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
    <QueryDropdown data={techniques} name=technique value=metric label=label title="Technique" defaultValue="low_speed_kph_z" />
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
    <QueryDropdown data={dna_races} name=dna_race value=race_key label=race_label title="Race and teammate" />
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
