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
Position changes starts at the official deployment message and ends after two complete racing laps following the end signal. Incidents, field compression, pit timing, restarts and retirements can all shape the result, so this page describes what happened across the window rather than what race control caused.
</KeyInsight>

```sql seasons
select distinct season
from f1.race_control_events
where season > 0
order by season desc
```

```sql races
select distinct
    round,
    race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') as race_label
from f1.race_control_events
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose a race" description="Only official, exactly paired intervention messages are analysed.">
    <Dropdown data={seasons} name=season value=season title="Season" />
    <Dropdown data={races} name=race value=round label=race_label order="round asc" title="Race" />
</FilterBar>

```sql coverage
select * from f1.data_coverage
where section = 'race_control'
    and race_label = (
        select cast(season as varchar) || ' ' || race_name
        from f1.race_control_events
        where season = ${inputs.season.value} and round = ${inputs.race.value}
        limit 1
    )
```

<DataTrust data={coverage} sampleLabel="neutralisations" entityLabel="Events" method="exact message pairs; two-lap recovery" />

```sql race_events
select
    *,
    '#' || cast(event_number as varchar) || ' · ' || event_type
        || ' · lap ' || cast(deployment_lap as varchar) as event_label
from f1.race_control_events
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by event_number
```

<FilterBar title="Choose an intervention" description="Incomplete events remain selectable so the missing evidence stays visible.">
    <Dropdown data={race_events} name=event value=event_id label=event_label order="event_number asc" title="Event" />
</FilterBar>

```sql selected_event
select * from ${race_events}
where event_id = '${inputs.event.value}'
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
    <BigValue data={event_driver_total} value=drivers title="Comparable drivers" />
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

## Relative-time movement beyond field compression

For Safety Car and VSC periods, the raw gap change is centred on the event median. This removes the field-wide compression shared by the measured drivers. Red-flag time changes and drivers whose lap deficit changed are intentionally left blank because their seconds are not comparable.

```sql time_movers
select * from ${eligible_drivers}
where field_adjusted_gap_gain_s is not null
order by abs(field_adjusted_gap_gain_s) desc
limit 18
```

<BarChart
    data={time_movers}
    x=driver_code
    y=field_adjusted_gap_gain_s
    series=pit_context
    yAxisTitle="field-adjusted relative gap gain (s)"
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
    <Column id=field_adjusted_gap_gain_s title="Adjusted gain (s)" fmt="+0.00;-0.00" />
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

<ExpandableSection title="See exclusions and the v1 method">
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

The parser accepts only exact official deployment and end messages. A valid event needs a replay baseline, a completed two-lap recovery uninterrupted by another neutralisation and at least 12 cars. Driver snapshots must be within three seconds of the shared clock. A changed lap deficit suppresses time metrics but not position evidence. Red flags publish position movement only.
</ExpandableSection>

<RelatedAnalysis section="race" current="race-control-impact" season={inputs.season.value} race={inputs.race.value} />
