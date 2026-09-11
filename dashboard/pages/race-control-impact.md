---
title: Race-Control Impact
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Race intelligence"
    title="Who gained when the race was neutralised?"
    description="Follow every Safety Car, VSC and red flag from deployment through two complete recovery laps, with position, pit-stop and relative-gap evidence."
    accent="race"
/>

<KeyInsight label="Observed impact, not causality">
Position comparison starts at the official deployment message and ends after two complete green reference-leader laps, between the first and third crossings following the end signal. Incidents, field compression, pit timing, restarts and retirements can all shape the result, so this page describes what happened across the window rather than what race control caused.
</KeyInsight>

```sql seasons
select distinct season
from f1.race_control_races
where season between 2024 and 2026
order by season desc
```

```sql races
select distinct
    season,
    round,
    race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') as race_label
from f1.race_control_races
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose a race" description="All loaded races from 2024–2026, including races without a recorded neutralisation. Only official, exactly paired intervention messages are analysed.">
    <Dropdown data={seasons} name=season value=season title="Season" />
    <DependentDropdown data={races} name=race value=round label=race_label order="round asc" title="Race" season={inputs.season.value} latest={true} preserveInitial={true} />
</FilterBar>

```sql selected_race
select * from f1.race_control_races
where season = ${inputs.season.value} and round = ${inputs.race.value}
```

```sql coverage
select message_count as sample_rows, event_count as entity_count,
    1 as race_count, season as first_season, season as last_season,
    race_date as latest_event_date
from ${selected_race}
```

<DataTrust data={coverage} sampleLabel="race-control messages" entityLabel="Neutralisations" method="exact message pairs; two-lap recovery" />

```sql race_events
select
    *,
    '#' || cast(event_number as varchar) || ' · ' || event_type
        || ' · lap ' || cast(deployment_lap as varchar) as event_label
from f1.race_control_events
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by event_number
```

{#if race_events.length > 0}

<FilterBar title="Choose an intervention" description="Incomplete events remain selectable so the missing evidence stays visible.">
    <RaceEventDropdown data={race_events} season={inputs.season.value} round={inputs.race.value} />
</FilterBar>

```sql selected_event
select * from ${race_events}
where event_id = '${inputs.event.value}'
    and season = ${inputs.season.value} and round = ${inputs.race.value}
```

```sql event_driver_total
select eligible_driver_count as drivers
from ${selected_event}
```

```sql event_stops
select intervention_stop_count as stops
from ${selected_event}
```

```sql event_gainers
select position_gainer_count as gainers
from ${selected_event}
```

<Grid cols=4>
    <BigValue data={selected_event} value=event_type comparison=duration_s comparisonFmt="0 s" title="Intervention" />
    <BigValue data={event_driver_total} value=drivers title="Position-comparable drivers" />
    <BigValue data={event_stops} value=stops title="Stops under intervention" />
    <BigValue data={event_gainers} value=gainers title="Position gainers" />
</Grid>

```sql driver_evidence
select
    *,
    case
        when pitted_during_intervention then 'Stopped under intervention'
        when pitted_during_recovery then 'Stopped during recovery'
        when tyre_changed_during_suspension then 'Changed tyres under red flag'
        else 'Stayed out'
    end as pit_context
from f1.race_control_impact
where event_id = '${inputs.event.value}'
    and season = ${inputs.season.value} and round = ${inputs.race.value}
order by position_before
```

```sql eligible_drivers
select * from ${driver_evidence} where eligible
```

## Position change after the two-lap recovery

Positive bars are positions gained between deployment and the shared post-event checkpoint. Drivers without reliable timing remain in the excluded evidence below.

<BarChart
    data={eligible_drivers}
    x=driver_code
    y=positions_gained
    series=pit_context
    yAxisTitle="positions gained (+) / lost (−)"
    labels=true
    sort=false
>
    <ReferenceLine y=0 label="position held" />
</BarChart>

## Relative-time movement against the event median

For Safety Car and VSC periods, the raw gap change is centred on the median of time-comparable drivers. This is a descriptive comparison within the measured cohort, not proof that field-wide compression has been removed. At least five time-comparable drivers are required to publish the centred result; this is a publication rule, not statistical validation. Red flags publish positions only.

<BigValue data={selected_event} value=time_comparable_driver_count title="Time-comparable drivers (minimum 5)" />

```sql time_unavailable
select time_exclusion_reason
from ${selected_event}
where not time_eligible
```

<DataTable data={time_unavailable} rows=5>
    <Column id=time_exclusion_reason title="Why the relative-time chart is unavailable" />
</DataTable>

```sql time_movers
select * from ${eligible_drivers}
where time_eligible and field_adjusted_gap_gain_s is not null
order by abs(field_adjusted_gap_gain_s) desc
limit 18
```

<BarChart
    data={time_movers}
    x=driver_code
    y=field_adjusted_gap_gain_s
    series=pit_context
    yAxisTitle="median-centred relative gap gain (s)"
    swapXY=true
    labels=true
    sort=false
>
    <ReferenceLine y=0 label="event median" />
</BarChart>

## Driver evidence

<DataTable data={eligible_drivers} rows=30 search=true download=true>
    <Column id=driver_code title="Driver" />
    <Column id=team title="Team" />
    <Column id=position_before title="Before" />
    <Column id=position_after title="After" />
    <Column id=positions_gained title="Position Δ" fmt="+0;-0" />
    <Column id=raw_gap_gain_s title="Raw gap gain (s)" fmt="+0.00;-0.00" />
    <Column id=field_adjusted_gap_gain_s title="Median-centred gain (s)" fmt="+0.00;-0.00" />
    <Column id=time_eligible title="Time eligible" />
    <Column id=time_exclusion_reason title="Why time is excluded" />
    <Column id=compound_before title="Tyre before" />
    <Column id=compound_after title="Tyre after" />
    <Column id=pit_context title="Pit context" />
    <Column id=outcome_label title="Observed outcome" />
    <Column id=confidence title="Evidence" />
</DataTable>

## All interventions in this race

<DataTable data={race_events} rows=20>
    <Column id=event_number title="#" />
    <Column id=event_type title="Type" />
    <Column id=deployment_lap title="Deployed" />
    <Column id=end_lap title="End signal" />
    <Column id=post_checkpoint_lap title="Measured after" />
    <Column id=duration_s title="Duration (s)" fmt="0" />
    <Column id=eligible_driver_count title="Drivers" />
    <Column id=time_comparable_driver_count title="Time-comparable drivers" />
    <Column id=time_exclusion_reason title="Time exclusion" />
    <Column id=intervention_stop_count title="Stops" />
    <Column id=event_status title="Status" />
    <Column id=confidence title="Evidence" />
</DataTable>

```sql excluded_drivers
select * from ${driver_evidence} where not eligible
```

```sql excluded_events
select * from ${race_events} where not eligible
```

<ExpandableSection title="See exclusions and the v2 method">
<DataTable data={excluded_events} rows=20>
    <Column id=event_label title="Event" />
    <Column id=event_status title="Status" />
    <Column id=exclusion_reason title="Why excluded" />
</DataTable>

<DataTable data={excluded_drivers} rows=30 search=true>
    <Column id=driver_code title="Driver" />
    <Column id=position_before title="Position before" />
    <Column id=exclusion_reason title="Why excluded" />
</DataTable>

The parser accepts only exact official deployment and end messages. A valid event needs a replay baseline, at least 12 cars and two complete, timed, contiguous green laps by the reference leader between the first and third crossings after the end signal. The same driver must lead at both ends of this fixed window. Another neutralisation interrupts recovery. Driver snapshots must be within three seconds of the shared clock.

Other recorded laps wholly contained in that timestamp interval must have green status; non-green or missing status rejects the recovery. An incomplete lap starting inside the interval with an unknown end also rejects it. Laps straddling a window boundary cannot localise their recorded flags to the recovery interval, so their lap-level status alone does not establish contamination. This check does not prove that the entire field stayed green or that field-wide coverage is complete.

Lap deficit is estimated from continuous lap distance (lap number minus one plus lap progress) at identical timestamps, not from integer lap counters alone. Estimates close to a whole-lap boundary are uncertain and suppress time metrics, as do changed estimated deficits or missing comparable timing. These estimates are not confirmation of physical lapping. Position eligibility is separate from time eligibility, so a driver can retain position evidence while their time comparison is blank. Red flags publish position movement only.
</ExpandableSection>

{:else}

{#if selected_race[0]?.message_count > 0}
<KeyInsight label="No recorded neutralisation">
The loaded race-control messages contain no recognised Safety Car, VSC or red-flag intervention for this race. There is no intervention impact to compare.
</KeyInsight>
{:else}
<KeyInsight label="Race-control data unavailable">
Official race-control messages have not been loaded for this race. Missing messages do not establish that the race had no neutralisation.
</KeyInsight>
{/if}

{/if}

<RelatedAnalysis section="race" current="race-control-impact" season={inputs.season.value} race={inputs.race.value} />
