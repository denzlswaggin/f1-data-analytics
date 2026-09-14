---
title: Race-Control Impact
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Race intelligence"
    title="How did race control reshape a driver's race?"
    description="Inspect the exact intervention timeline, pit opportunity, position, gaps, tyres and recovery separately—with facts kept distinct from counterfactual estimates."
    accent="race"
/>

<KeyInsight label="Evidence first">
Observed timing and positions are facts from the loaded feeds. A VSC pit saving is a same-race green-stop estimate with a 90% uncertainty interval, never a claim that race control caused the final result. If a component fails its own evidence rules, its number is withheld while the remaining facts stay visible.
</KeyInsight>

```sql seasons
select distinct season
from f1.race_control_races
where season between 2024 and 2026
order by season desc
```

```sql races
select distinct season, round, race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') as race_label
from f1.race_control_races
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose a race" description="Completed races remain selectable even when no intervention or publishable estimate is available.">
    <Dropdown data={seasons} name=season value=season title="Season" defaultValue={2026} />
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

<DataTrust data={coverage} sampleLabel="race-control messages" entityLabel="Neutralisations" method="component-level facts and same-race pit counterfactual" />

```sql race_events
select *,
    '#' || cast(event_number as varchar) || ' · ' || event_type
        || ' · lap ' || cast(deployment_lap as varchar) as event_label
from f1.race_control_events
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by event_number
```

{#if race_events.length > 0}

<FilterBar title="Choose an intervention" description="Each impact component has independent availability; an unavailable gap model no longer hides valid pit evidence.">
    <RaceEventDropdown data={race_events} season={inputs.season.value} round={inputs.race.value} />
</FilterBar>

```sql selected_event
select * from ${race_events}
where event_id = '${inputs.event.value}'
    and season = ${inputs.season.value} and round = ${inputs.race.value}
```

```sql driver_evidence
select *,
    case pit_timing_class
        when 'during_neutralisation' then 'Stopped during neutralisation'
        when 'after_end' then 'Stopped after the end signal'
        when 'unresolved' then 'Stop inferred; exact timing unavailable'
        else 'No stop observed in the event window'
    end as pit_context,
    driver_code || ' · ' || driver_name as driver_label
from f1.race_control_impact
where event_id = '${inputs.event.value}'
    and season = ${inputs.season.value} and round = ${inputs.race.value}
order by focus_rank, position_before
```

<Grid cols=4>
    <BigValue data={selected_event} value=event_type comparison=duration_s comparisonFmt="0 s" title="Intervention" />
    <BigValue data={selected_event} value=pit_status title="Pit opportunity" />
    <BigValue data={selected_event} value=gap_status title="Gap evidence" />
    <BigValue data={selected_event} value=restart_status title="Recovery evidence" />
</Grid>

<FilterBar title="Driver story" description="The model opens the strongest substantiated intervention story; every driver remains selectable.">
    <DependentDropdown data={driver_evidence} name=driver value=driver_code label=driver_label order="focus_rank asc" title="Driver" season={inputs.season.value} round={inputs.race.value} scopeKey={inputs.event.value} defaultValue={selected_event[0]?.focus_driver_code} />
</FilterBar>

```sql focus_driver
select * from ${driver_evidence}
where driver_code = '${inputs.driver.value}'
```

```sql focus_effects
select *
from f1.race_control_effects
where event_id = '${inputs.event.value}' and driver_code = '${inputs.driver.value}'
    and season = ${inputs.season.value} and round = ${inputs.race.value}
order by effect_scope, effect_type
```

```sql pit_saving
select value, lower_bound, upper_bound, confidence, sample_size
from ${focus_effects}
where effect_type in ('estimated_vsc_pit_saving', 'estimated_safety_car_pit_saving')
    and eligible
```

```sql pit_unavailable
select exclusion_reason
from ${focus_effects}
where effect_type in ('estimated_vsc_pit_saving', 'estimated_safety_car_pit_saving')
    and not eligible
```

## {inputs.driver.value}'s intervention story

<Grid cols=4>
    <BigValue data={focus_driver} value=position_before title="Position at deployment" />
    <BigValue data={focus_driver} value=pit_context title="Pit timing" />
    <BigValue data={focus_driver} value=pit_duration_sec fmt="0.000" title="Recorded pit-lane duration (s)" />
    <BigValue data={pit_saving} value=value fmt="0.00" title="Estimated neutralised pit saving (s)" />
</Grid>

<KeyInsight label="Final result is context only">
{inputs.driver.value} finished P<Value data={focus_driver} column=finish_position />. This is shown to complete the race story, but no finishing position is attributed to the intervention: everything after the measured checkpoints remains residual and unmodelled.
</KeyInsight>

{#if inputs.season.value == 2026 && inputs.race.value == 14}
<ExpandableSection title="Official validation context — Madrid 2026">
The timing model is calculated independently of article prose. The frozen golden-case annotations are checked against Formula 1's [race report](https://www.formula1.com/en/latest/article/antonelli-clinches-victory-over-verstappen-and-norris-in-spanish-gp.644ZZfPzRPEaUh2JBHcB9) and [official pit-stop summary](https://www.formula1.com/en/results/2026/races/1294/spain/pit-stop-summary), which validate the VSC sequence and recorded pit laps/durations.
</ExpandableSection>
{/if}

{#if pit_saving.length > 0}
<KeyInsight label="Estimated pit opportunity—not race-result causality">
Against supported clean green-flag stops from this race, the stop saved an estimated <Value data={pit_saving} column=value fmt="0.00" /> s. The 90% interval is <Value data={pit_saving} column=lower_bound fmt="0.00" /> to <Value data={pit_saving} column=upper_bound fmt="0.00" /> s and includes a one-second timing-resolution allowance. Later racing remains unattributed.
</KeyInsight>
{:else}
<DataTable data={pit_unavailable} rows=3>
    <Column id=exclusion_reason title="Why no pit-saving estimate is published" />
</DataTable>
{/if}

```sql focus_checkpoints
select *,
    case checkpoint_type
        when 'pre_deploy' then 'Deployment'
        when 'pit_in' then 'Pit entry'
        when 'pit_out' then 'Pit exit'
        when 'control_end' then 'End signal'
        when 'green_lap_1' then 'After 1 green lap'
        when 'green_lap_3' then 'After 3 leader crossings'
        else checkpoint_type
    end as checkpoint_label
from f1.race_control_checkpoints
where event_id = '${inputs.event.value}' and driver_code = '${inputs.driver.value}'
    and season = ${inputs.season.value} and round = ${inputs.race.value}
order by checkpoint_order
```

### Audit timeline

<DataTable data={focus_checkpoints} rows=12>
    <Column id=checkpoint_label title="Checkpoint" />
    <Column id=checkpoint_t_s title="Race clock (s)" fmt="0.000" />
    <Column id=running_order title="Position" />
    <Column id=gap_to_leader_s title="Gap to leader (s)" fmt="0.00" />
    <Column id=lap_number title="Lap" />
    <Column id=compound title="Tyre" />
    <Column id=tyre_life title="Tyre age" />
    <Column id=capture_offset_s title="Timing resolution (s)" fmt="0.000" />
    <Column id=source title="Source" />
    <Column id=exclusion_reason title="Evidence gap" />
</DataTable>

### Component verdicts

<DataTable data={focus_effects} rows=30 download=true>
    <Column id=effect_type title="Effect" />
    <Column id=effect_scope title="Window" />
    <Column id=value title="Value" fmt="0.00" />
    <Column id=lower_bound title="90% low" fmt="0.00" />
    <Column id=upper_bound title="90% high" fmt="0.00" />
    <Column id=unit title="Unit" />
    <Column id=evidence_class title="Evidence class" />
    <Column id=confidence title="Confidence" />
    <Column id=sample_size title="Sample" />
    <Column id=exclusion_reason title="Why unavailable" />
</DataTable>

```sql position_drivers
select * from ${driver_evidence} where position_eligible
```

## Field context

<BarChart data={position_drivers} x=driver_code y=positions_gained series=pit_context yAxisTitle="positions gained (+) / lost (−)" labels=true sort=false>
    <ReferenceLine y=0 label="position held" />
</BarChart>

```sql time_movers
select * from ${driver_evidence}
where gap_eligible and field_adjusted_gap_gain_s is not null
order by abs(field_adjusted_gap_gain_s) desc
```

<BarChart data={time_movers} x=driver_code y=field_adjusted_gap_gain_s series=pit_context yAxisTitle="median-centred relative gap gain (s)" swapXY=true labels=true sort=false>
    <ReferenceLine y=0 label="event median" />
</BarChart>

<ExpandableSection title="All drivers and unavailable components">
<DataTable data={driver_evidence} rows=30 search=true download=true>
    <Column id=driver_code title="Driver" />
    <Column id=position_before title="Before" />
    <Column id=position_after title="After" />
    <Column id=positions_gained title="Position Δ" fmt="+0;-0" />
    <Column id=field_adjusted_gap_gain_s title="Field-adjusted gap Δ" fmt="+0.00;-0.00" />
    <Column id=pit_context title="Pit context" />
    <Column id=pit_duration_sec title="Pit lane (s)" fmt="0.000" />
    <Column id=finish_position title="Finish" />
    <Column id=result_status title="Result status" />
    <Column id=compound_before title="Tyre before" />
    <Column id=compound_after title="Tyre after" />
    <Column id=time_exclusion_reason title="Gap evidence gap" />
    <Column id=exclusion_reason title="Legacy window exclusion" />
</DataTable>

`race-control-impact-v3` pairs exact official intervention messages and evaluates position, gap, pit, tyre and recovery evidence independently. Gap publication still requires at least five comparable drivers and verified green recovery. Pit estimates instead require exact pit timestamps, at least one stable non-pitting peer, five clean same-race green stops from at least four drivers, and a stable reference distribution. Red flags suppress gap estimates across the suspension.
</ExpandableSection>

{:else}

{#if selected_race[0]?.message_count > 0}
<KeyInsight label="No recorded neutralisation">The loaded messages contain no recognised, exactly paired Safety Car, VSC or red-flag intervention.</KeyInsight>
{:else}
<KeyInsight label="Race-control data unavailable">Missing messages do not establish that the race had no neutralisation.</KeyInsight>
{/if}

{/if}

<RelatedAnalysis section="race" current="race-control-impact" season={inputs.season.value} race={inputs.race.value} />
