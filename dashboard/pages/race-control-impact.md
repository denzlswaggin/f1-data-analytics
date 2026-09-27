---
title: Race-Control Impact
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Race intelligence"
    title="How did race control reshape a driver's race?"
    description="Inspect the recorded intervention timeline, pit opportunity, position, gaps, tyres and recovery separately—with facts kept distinct from counterfactual estimates."
    accent="race"
/>

<KeyInsight label="Evidence first">
Positions marked **Recorded** come from a coherent full-field OpenF1 order aligned to the FastF1 race clock. Values marked **Estimated** use complete lap-progress timing and carry an approximation sign. A VSC pit saving is a same-race green-stop estimate with a 90% uncertainty interval, never a claim that race control caused the final result. If a component fails its own evidence rules, its number is withheld.
</KeyInsight>

```sql seasons
select distinct season
from f1.race_control_races
where season between 2024 and 2026
order by season desc
```

```sql races
select distinct season, round, race_name,
    'R' || lpad(cast(cast(round as integer) as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') as race_label
from f1.race_control_races
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose a race" description="Completed races remain selectable even when no intervention or publishable estimate is available.">
    <QueryDropdown data={seasons} name=season value=season title="Season" defaultValue={2026} />
    <DependentDropdown data={races} name=race value=round label=race_label order="round asc" title="Race" season={inputs.season.value} latest={true} preserveInitial={true} />
</FilterBar>

```sql selected_race
select * from f1.race_control_races
where season = ${inputs.season.value} and round = ${inputs.race.value}
```

```sql coverage
select message_count as sample_rows, event_count as entity_count,
    1 as race_count, season as first_season, season as last_season,
    race_date as latest_event_date,
    'race-control messages' as sample_unit,
    (select count(*) from f1.race_control_effects
     where season = ${inputs.season.value} and round = ${inputs.race.value}
       and eligible) as usable_samples,
    'eligible driver-effect observations' as usable_unit
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
    case
        when position_eligible and position_evidence_class = 'recorded'
            then 'P' || cast(position_before as varchar) || ' · Recorded'
        when position_eligible and position_evidence_class = 'estimated'
            then '≈P' || cast(position_before as varchar) || ' · Estimated'
        else 'Deployment position unavailable'
    end as position_before_display,
    case
        when position_eligible and position_evidence_class = 'recorded'
            then 'P' || cast(position_after as varchar) || ' · Recorded'
        when position_eligible and position_evidence_class = 'estimated'
            then '≈P' || cast(position_after as varchar) || ' · Estimated'
        else 'Recovery position unavailable'
    end as position_after_display,
    case
        when pit_duration_sec is not null then printf('%.3f s', pit_duration_sec)
        when pit_timing_class = 'unresolved' then 'Exact pit timing unavailable'
        else 'No stop in event window'
    end as pit_duration_display,
    driver_code || ' · ' || driver_name || ' · '
        || case story_status
            when 'material_impact' then '1/1 · Material ' || story_direction
            when 'context_only' then '0/1 · Context only'
            else '0/1 · No material effect'
        end as driver_label
from f1.race_control_impact
where event_id = '${inputs.event.value}'
    and season = ${inputs.season.value} and round = ${inputs.race.value}
order by focus_rank, position_before
```

<Grid cols=4>
    <BigValue data={selected_event} value=event_type comparison=duration_s comparisonFmt='0" s"' title="Intervention" />
    <BigValue data={selected_event} value=pit_status title="Pit opportunity" />
    <BigValue data={selected_event} value=gap_status title="Gap evidence" />
    <BigValue data={selected_event} value=restart_status title="Recovery evidence" />
</Grid>

{#if driver_evidence.length > 0}

<FilterBar title="Driver story" description="The model opens the strongest substantiated intervention story; every driver remains selectable. Material effects clear explicit position/time thresholds or a one-sided pit uncertainty interval. Context-only means an action or evidence limitation remains relevant; no-material-effect means at least one component was genuinely evaluated below threshold.">
    <DependentDropdown data={driver_evidence} name=driver value=driver_code label=driver_label order="focus_rank asc" title="Driver" season={inputs.season.value} round={inputs.race.value} scopeKey={inputs.event.value} defaultValue={selected_event[0]?.focus_driver_code} />
</FilterBar>

```sql focus_driver
select * from ${driver_evidence}
where driver_code = '${inputs.driver.value}'
```

```sql focus_effects
select * exclude (value, lower_bound, upper_bound),
    case when eligible then value end as value,
    case when eligible then lower_bound end as lower_bound,
    case when eligible then upper_bound end as upper_bound
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

```sql pit_card
select case
    when effect.eligible then printf('%.2f s', effect.value)
    when driver.pit_timing_class = 'no_stop_observed' then 'No stop in event window'
    when driver.pit_timing_class = 'after_end' then 'Stopped after end; no neutralised saving'
    when coalesce(effect.exclusion_reason, '') <> '' then effect.exclusion_reason
    when not driver.pit_eligible then 'Exact pit timing unavailable'
    else 'No supported same-race counterfactual'
end as pit_saving_display
from ${focus_driver} as driver
left join ${focus_effects} as effect
    on effect.effect_type in ('estimated_vsc_pit_saving', 'estimated_safety_car_pit_saving')
qualify row_number() over (order by effect.eligible desc nulls last) = 1
```

## {inputs.driver.value}'s intervention story

<KeyInsight label="Story verdict">
{focus_driver[0]?.story_reason}. Direction: {focus_driver[0]?.story_direction}. Material components: {focus_driver[0]?.material_effect_count || 0}/{focus_driver[0]?.evaluated_effect_count || 0} evaluated.
</KeyInsight>

<Grid cols=4>
    <BigValue data={focus_driver} value=position_before_display title="Position at deployment" />
    <BigValue data={focus_driver} value=pit_context title="Pit timing" />
    <BigValue data={focus_driver} value=pit_duration_display title="Recorded pit-lane duration" />
    <BigValue data={pit_card} value=pit_saving_display title="Estimated neutralised pit saving" />
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
Against supported clean green-flag stops from this race, the stop saved an estimated <Value data={pit_saving} column=value fmt="0.00" /> s. The 90% interval is <Value data={pit_saving} column=lower_bound fmt="0.00" /> to <Value data={pit_saving} column=upper_bound fmt="0.00" /> s and includes a one-second timing-resolution allowance. The reference sample contains <Value data={pit_saving} column=sample_size /> observations. Later racing remains unattributed.
</KeyInsight>
{:else}
{#if pit_unavailable.length > 0}
<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={pit_unavailable} rows=3>
    <Column id=exclusion_reason title="Why no pit-saving estimate is published" />
</DataTable>
</div>
{:else}
<KeyInsight label="No pit-saving estimate applies">
{pit_card[0]?.pit_saving_display || 'No supported same-race counterfactual'}. A numeric saving is only estimated for a stop observed during the intervention.
</KeyInsight>
{/if}
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
    end as checkpoint_label,
    case
        when eligible and evidence_class = 'recorded'
            then 'P' || cast(running_order as varchar) || ' · Recorded'
        when eligible and evidence_class = 'estimated'
            then '≈P' || cast(running_order as varchar) || ' · Estimated'
        else 'Unavailable'
    end as position_display,
    case running_order_source
        when 'openf1_recorded' then 'OpenF1 full-field order'
        when 'lap_progress_estimate' then 'FastF1 lap-progress estimate'
        else 'Unavailable'
    end as position_source_display
from f1.race_control_checkpoints
where event_id = '${inputs.event.value}' and driver_code = '${inputs.driver.value}'
    and season = ${inputs.season.value} and round = ${inputs.race.value}
order by checkpoint_order
```

### Audit timeline

<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={focus_checkpoints} rows=12>
    <Column id=checkpoint_label title="Checkpoint" />
    <Column id=checkpoint_t_s title="Race clock (s)" fmt="0.000" />
    <Column id=position_display title="Position" />
    <Column id=position_source_display title="Position source" />
    <Column id=running_order_observed_t_s title="Source clock (s)" fmt="0.000" />
    <Column id=gap_to_leader_s title="Gap to leader (s)" fmt="0.00" />
    <Column id=lap_number title="Lap" />
    <Column id=compound title="Tyre" />
    <Column id=tyre_life title="Tyre age" />
    <Column id=capture_offset_s title="Timing resolution (s)" fmt="0.000" />
    <Column id=gap_source title="Gap source" />
    <Column id=gap_observed_t_s title="Gap source clock (s)" fmt="0.000" />
    <Column id=source title="Checkpoint construction" />
    <Column id=exclusion_reason title="Evidence gap" />
</DataTable>
</div>

### Component verdicts

Each row has its own unit, time window and eligibility rule. Do not add position,
gap, tyre and pit effects together: their windows and reference groups can overlap.
Evidence grades are heuristic quality labels; only a displayed numeric interval
quantifies the model's stated resampling uncertainty. Blank values are withheld,
not zero effects.

<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={focus_effects} rows=30 download=true>
    <Column id=effect_type title="Effect" />
    <Column id=effect_scope title="Window" />
    <Column id=value title="Value" fmt="0.00" />
    <Column id=lower_bound title="90% low" fmt="0.00" />
    <Column id=upper_bound title="90% high" fmt="0.00" />
    <Column id=unit title="Unit" />
    <Column id=evidence_class title="Evidence class" />
    <Column id=confidence title="Evidence grade" />
    <Column id=eligible title="Eligible" />
    <Column id=sample_size title="Sample" />
    <Column id=exclusion_reason title="Why unavailable" />
</DataTable>
</div>

```sql position_drivers
select * from ${driver_evidence} where position_eligible
```

## Field context

{#if position_drivers.length > 0}
<BarChart data={position_drivers} x=driver_code y=positions_gained series=pit_context yAxisTitle="positions gained (+) / lost (−)" labels=true sort=false>
    <ReferenceLine y=0 label="position held" />
</BarChart>
{:else}
<KeyInsight label="No publishable position comparison">
No driver has a trustworthy before/after position pair for this intervention. Position evidence is withheld rather than shown as an empty result.
</KeyInsight>
{/if}

```sql time_movers
select * from ${driver_evidence}
where gap_eligible and field_adjusted_gap_gain_s is not null
order by abs(field_adjusted_gap_gain_s) desc
```

{#if time_movers.length > 0}
<BarChart data={time_movers} x=driver_code y=field_adjusted_gap_gain_s series=pit_context yAxisTitle="median-centred relative gap gain (s)" swapXY=true labels=true sort=false>
    <ReferenceLine y=0 label="event median" />
</BarChart>
{:else}
<KeyInsight label="No publishable gap comparison">
No driver passes the comparable-field and verified-recovery rules for this intervention. Gap effects are withheld; this does not mean the intervention had no effect.
</KeyInsight>
{/if}

<ExpandableSection title="All drivers and unavailable components">
<div style="overflow-x: auto; max-width: 100%;">
<DataTable data={driver_evidence} rows=30 search=true download=true>
    <Column id=driver_code title="Driver" />
    <Column id=story_status title="Story status" />
    <Column id=story_direction title="Direction" />
    <Column id=story_reason title="Story reason" />
    <Column id=position_before_display title="Before" />
    <Column id=position_after_display title="After" />
    <Column id=position_evidence_class title="Position evidence" />
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
</div>

`race-control-impact-v3` pairs exact official intervention messages and evaluates position, gap, pit, tyre and recovery evidence independently. Recorded order is only used after the OpenF1-to-FastF1 clock passes an 8-anchor, 4-driver and 90%-inlier gate and the replay sees a coherent full-field ranking. Missing timing never advances an unfinished lap. Gap publication still requires at least five comparable drivers and verified green recovery. Pit estimates require exact pit timestamps, at least one stable non-pitting peer, five clean same-race green stops from at least four drivers, and a stable reference distribution. Red flags suppress gap estimates across the suspension.
</ExpandableSection>

{:else}

<KeyInsight label="Driver evidence unavailable">
The intervention is retained because its deployment is present in the race-control source, but no trustworthy driver-level before/after view can be published. Reason: {selected_event[0]?.exclusion_reason || 'race replay or baseline unavailable'}. This is a source limitation, not evidence that the intervention had no impact.
</KeyInsight>

{/if}

{:else}

{#if selected_race[0]?.message_count > 0}
<KeyInsight label="No recorded neutralisation">The loaded messages contain no recognised, exactly paired Safety Car, VSC or red-flag intervention.</KeyInsight>
{:else}
<KeyInsight label="Race-control data unavailable">Missing messages do not establish that the race had no neutralisation.</KeyInsight>
{/if}

{/if}

<RelatedAnalysis section="race" current="race-control-impact" season={inputs.season.value} race={inputs.race.value} />
