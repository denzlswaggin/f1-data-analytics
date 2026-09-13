---
title: Racecraft Battle Conversion
hide_title: true
max_width: 1600
---

<AppNav />

<PageHeader
    eyebrow="Driver intelligence"
    title="Who converted pressure—and who held position?"
    description="Trace sustained green-flag close running against the car directly ahead, then separate confirmed passes, clean defences and interrupted battles."
    accent="drivers"
/>

<KeyInsight label="Observed racecraft, not a driver-skill score">
An eligible battle needs at least ten seconds of uninterrupted, sample-supported pressure within one second of the car directly ahead. Conversion requires a confirmed order change; an unmatched episode only counts as a defence after an uninterrupted 15-second gap release. Car pace, tyres, fuel, damage, team orders and circuit layout remain part of every result.
</KeyInsight>

```sql seasons
select distinct season
from f1.racecraft_coverage
where season > 0
order by season desc
```

```sql view_modes
select 'season' as view, 'Season' as label
union all select 'race', 'Race'
```

```sql races
select distinct
    season,
    round,
    race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') as race_label
from f1.racecraft_coverage
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose your scope" description="Season combines the covered races. The race selection applies in Race view; drivers with zero eligible battles remain visible.">
    <Dropdown data={view_modes} name=view value=view label=label title="View" defaultValue="season" />
    <Dropdown data={seasons} name=season value=season title="Season" />
    <DependentDropdown data={races} name=race value=round label=race_label order="round asc" title="Race" season={inputs.season.value} latest={true} preserveInitial={true} />
</FilterBar>

```sql coverage_details
select * from f1.racecraft_coverage
where season = ${inputs.season.value}
    and ('${inputs.view.value}' = 'season' or round = ${inputs.race.value})
order by round
```

```sql scope_coverage
select count(*) as available_races,
    count(*) filter (where coverage_status in ('Processed', 'Processed: no observed battles')) as processed_races
from ${coverage_details}
```

<Grid cols=2>
    <BigValue data={scope_coverage} value=processed_races title="Races with battle analysis" />
    <BigValue data={scope_coverage} value=available_races title="Races in available timing data" />
</Grid>

<ExpandableSection title="Race coverage and missing inputs">
<DataTable data={coverage_details} rows=30>
    <Column id=round title="Round" />
    <Column id=race_name title="Race" />
    <Column id=replay_drivers title="Replay drivers" />
    <Column id=drivers_without_running_order title="Without usable running order" />
    <Column id=analysed_drivers title="Analysed drivers" />
    <Column id=observed_battles title="Episodes" />
    <Column id=coverage_status title="Coverage" />
</DataTable>
Drivers whose replay has no usable running order cannot be assigned an opponent.
They are listed in the missing-order count rather than treated as zero-opportunity profiles.
</ExpandableSection>

```sql race_drivers
select *
from f1.racecraft_profiles
where season = ${inputs.season.value}
    and round = case when '${inputs.view.value}' = 'season' then 0 else ${inputs.race.value} end
order by greatest(attacking_opportunities, defensive_opportunities) desc, driver_code
```

```sql race_battles
select *
from f1.racecraft_battles
where season = ${inputs.season.value}
    and ('${inputs.view.value}' = 'season' or round = ${inputs.race.value})
order by round, start_t_s, battle_number
```

```sql race_totals
select
    count(*) as observed_battles,
    count(*) filter (where eligible) as eligible_battles,
    count(*) filter (where eligible and outcome = 'Converted') as conversions,
    count(*) filter (where eligible and outcome = 'Defended') as defences,
    count(*) filter (where outcome = 'Interrupted') as interrupted_battles,
    count(*) filter (where outcome = 'Unresolved') as unresolved_battles,
    count(*) filter (where not eligible and outcome in ('Converted', 'Defended')) as excluded_resolved
from ${race_battles}
```

<Grid cols=4>
    <BigValue data={race_totals} value=observed_battles title="Observed battles" />
    <BigValue data={race_totals} value=eligible_battles title="Resolved denominator" />
    <BigValue data={race_totals} value=conversions title="Confirmed conversions" />
    <BigValue data={race_totals} value=defences title="Clean defences" />
</Grid>

<Grid cols=3>
    <BigValue data={race_totals} value=interrupted_battles title="Interrupted — excluded" />
    <BigValue data={race_totals} value=unresolved_battles title="Unresolved — excluded" />
    <BigValue data={race_totals} value=excluded_resolved title="Other resolved — insufficient evidence" />
</Grid>

The rate denominator contains only eligible **resolved** episodes. Interrupted,
unresolved and insufficient-evidence episodes are excluded, not counted as failed
attacks or successful defences. These counts partition all observed episodes.
Conversion is therefore not the probability of passing after any close approach.

## Attack and defence rates — {inputs.season.value} · {inputs.view.value === 'season' ? 'Season' : inputs.race.label}

Rates appear only after five eligible resolved opportunities in the relevant
role: attack rate is conversions / attack n; defence rate is holds / defence n.
Season rates pool the underlying episodes, not the percentages from each race.
Counts remain visible below five opportunities; a blank percentage means insufficient evidence.
The 90% Wilson interval describes binomial sampling uncertainty within this
selected subset. It does not cover event-detection errors, dependence between
repeated battles, or selection from interrupted and unresolved episodes.

```sql role_rates
select
    driver_code,
    'Attack conversion' as role,
    attack_conversion_pct as rate_pct
from ${race_drivers}
where offense_eligible

union all

select
    driver_code,
    'Defence hold' as role,
    defence_hold_pct as rate_pct
from ${race_drivers}
where defense_eligible
```

{#if role_rates.length > 0}
<BarChart
    data={role_rates}
    x=driver_code
    y=rate_pct
    series=role
    yAxisTitle="eligible battles converted / held (%)"
    labels=true
    sort=false
    chartAreaHeight=390
/>
{:else}
<KeyInsight label="More resolved opportunities needed">
No driver reached five resolved opportunities in either role in this scope.
Observed pressure and episode counts remain available below.
</KeyInsight>
{/if}

```sql two_way_evidence
select * from ${race_drivers}
where offense_eligible and defense_eligible
```

## Two-way battle profile

The chart deliberately keeps attack and defence separate. It does not combine
them into an arbitrary racecraft score, and drivers without five opportunities
on both axes are omitted.

{#if two_way_evidence.length > 0}
<ScatterPlot
    data={two_way_evidence}
    x=attack_conversion_pct
    y=defence_hold_pct
    series=driver_code
    tooltipTitle=driver_code
    xAxisTitle="attack conversion (%)"
    yAxisTitle="defence hold (%)"
    pointSize=30
    chartAreaHeight=390
/>
{:else}
<KeyInsight label="No two-way profile for this scope">
No driver reached five resolved opportunities in both attack and defence. The
role-specific evidence and raw episodes remain available below.
</KeyInsight>
{/if}

<DataTable data={race_drivers} rows=25 search=true download=true>
    <Column id=driver_code title="Driver" />
    <Column id=team title="Team" />
    <Column id=races_covered title="Races" />
    <Column id=attacking_opportunities title="Attack n" />
    <Column id=converted_opportunities title="Converted" />
    <Column id=attack_conversion_pct title="Attack (%)" fmt="0.0" />
    <Column id=attack_conversion_p05_pct title="Attack 90% lower" fmt="0.0" />
    <Column id=attack_conversion_p95_pct title="Attack 90% upper" fmt="0.0" />
    <Column id=defensive_opportunities title="Defence n" />
    <Column id=defences_held title="Held" />
    <Column id=defence_hold_pct title="Defence (%)" fmt="0.0" />
    <Column id=defence_hold_p05_pct title="Defence 90% lower" fmt="0.0" />
    <Column id=defence_hold_p95_pct title="Defence 90% upper" fmt="0.0" />
    <Column id=quick_reversals_made title="Re-passes made" />
    <Column id=quick_reversals_conceded title="Re-passes conceded" />
    <Column id=offense_confidence title="Attack evidence" />
    <Column id=defense_confidence title="Defence evidence" />
</DataTable>

## Observed pressure and opponents

These totals include interrupted, unresolved and short episodes. They describe
sample-supported close running; they do not turn interruptions into successful
defences. Attack and defence are two views of the same episodes and must not be
added together as a count of unique battles.

```sql pressure_roles
select driver_code, 'Applying pressure' as role, observed_attack_pressure_s / 60 as pressure_minutes
from ${race_drivers}
union all
select driver_code, 'Under pressure', observed_defensive_pressure_s / 60
from ${race_drivers}
```

{#if race_drivers.length > 0}
<BarChart data={pressure_roles} x=driver_code y=pressure_minutes series=role yAxisTitle="Observed pressure (minutes)" sort=false />
{/if}

<DataTable data={race_drivers} rows=25 search=true download=true>
    <Column id=driver_code title="Driver" />
    <Column id=races_covered title="Races" />
    <Column id=observed_attacks title="Attack episodes" />
    <Column id=observed_defences title="Defence episodes" />
    <Column id=observed_attack_pressure_s title="Applying pressure" fmt="0 s" />
    <Column id=observed_defensive_pressure_s title="Under pressure" fmt="0 s" />
    <Column id=distinct_defenders title="Defenders faced" />
    <Column id=distinct_attackers title="Attackers faced" />
    <Column id=median_time_to_pass_s title="Median time to eligible pass" fmt="0 s" />
</DataTable>

## Repeated matchups

Each pair appears once with both directions combined. Repeated episodes can be
separate segments of one encounter; they are not independent attempts.

```sql battle_pairs
select b.season,
    case when '${inputs.view.value}' = 'season' then 0 else b.round end as round,
    least(attacker_code, defender_code) || ' / ' || greatest(attacker_code, defender_code) as pair,
    count(*) as episodes,
    count(distinct b.round) as races,
    count(*) filter (where eligible and converted) as confirmed_passes,
    count(*) filter (where eligible and defender_retained) as clean_defences,
    count(*) filter (where outcome = 'Interrupted') as interrupted,
    count(*) filter (where outcome = 'Unresolved') as unresolved,
    count(*) filter (where not eligible and outcome in ('Converted', 'Defended')) as insufficient_resolved,
    sum(pressure_seconds) as pressure_seconds
from ${race_battles} b
group by b.season, case when '${inputs.view.value}' = 'season' then 0 else b.round end,
    least(attacker_code, defender_code) || ' / ' || greatest(attacker_code, defender_code)
order by episodes desc, pair
```

<DataTable data={battle_pairs} rows=20 search=true download=true>
    <Column id=pair title="Pair" />
    <Column id=races title="Races" />
    <Column id=episodes title="Episodes" />
    <Column id=confirmed_passes title="Eligible passes" />
    <Column id=clean_defences title="Clean defences" />
    <Column id=interrupted title="Interrupted" />
    <Column id=unresolved title="Unresolved" />
    <Column id=insufficient_resolved title="Insufficient resolved" />
    <Column id=pressure_seconds title="Observed pressure" fmt="0 s" />
</DataTable>

{#if battle_pairs.length > 0}
<DependentDropdown data={battle_pairs} name=pair value=pair title="Inspect a pair" season={inputs.season.value} round={inputs.view.value === 'season' ? 0 : inputs.race.value} />

```sql pair_battles
select * from ${race_battles}
where least(attacker_code, defender_code) || ' / ' || greatest(attacker_code, defender_code) = '${inputs.pair.value}'
order by round, start_t_s
```

<DataTable data={pair_battles} rows=20 search=true download=true>
    <Column id=race_label title="Race" />
    <Column id=attacker_code title="Attacker" />
    <Column id=defender_code title="Defender" />
    <Column id=start_lap title="Start lap" />
    <Column id=pressure_seconds title="Pressure" fmt="0 s" />
    <Column id=outcome title="Outcome" />
    <Column id=eligible title="Eligible result" />
    <Column id=attacker_compound title="Attacker tyre" />
    <Column id=attacker_tyre_age_laps title="Attacker tyre age" />
    <Column id=defender_compound title="Defender tyre" />
    <Column id=defender_tyre_age_laps title="Defender tyre age" />
    <Column id=tyre_age_delta_laps title="Age delta (attacker − defender)" />
</DataTable>

Tyre context is measured at the start of each episode. A positive age delta
means the attacker's tyres were older. Blank values mean unavailable context.
This is descriptive context, not a tyre-adjusted estimate of driver ability.

{:else}
<KeyInsight label="No observed matchups">No battle episodes are available in this scope. Check the coverage table above.</KeyInsight>
{/if}

### Episodes outside the resolved denominator

Counts below retain every interrupted or unresolved episode, including short
approaches. One battle has an attacker and a defender, so do not add role counts
to infer the number of unique race-wide episodes. Resolved episodes excluded for
insufficient evidence remain available in the excluded-episodes table below.

<DataTable data={race_drivers} rows=25 search=true>
    <Column id=driver_code title="Driver" />
    <Column id=interrupted_attacks title="Interrupted attacks" />
    <Column id=unresolved_attacks title="Unresolved attacks" />
    <Column id=interrupted_defences title="Interrupted defences" />
    <Column id=unresolved_defences title="Unresolved defences" />
</DataTable>

{#if race_drivers.length > 0}

```sql drivers
select season, round, driver_code
from ${race_drivers}
order by driver_code
```

<FilterBar title="Inspect one driver's battles" description="Both attacking and defending episodes are shown chronologically; interrupted and unresolved evidence remains visible.">
    <DependentDropdown data={drivers} name=driver value=driver_code title="Driver" season={inputs.season.value} round={inputs.view.value === 'season' ? 0 : inputs.race.value} />
</FilterBar>

```sql driver_battles
select
    *,
    case when attacker_code = '${inputs.driver.value}' then 'Attacking' else 'Defending' end as role,
    case when attacker_code = '${inputs.driver.value}' then defender_code else attacker_code end as opponent,
    case
        when outcome = 'Converted' and attacker_code = '${inputs.driver.value}' then 'Pass completed'
        when outcome = 'Converted' then 'Position lost'
        when outcome = 'Defended' and defender_code = '${inputs.driver.value}' then 'Position held'
        when outcome = 'Defended' then 'Attack ended'
        when outcome = 'Interrupted' then 'Interrupted'
        else 'Unresolved'
    end as driver_outcome
from ${race_battles}
where attacker_code = '${inputs.driver.value}' or defender_code = '${inputs.driver.value}'
order by round, start_t_s
```

## Episode evidence — {inputs.driver.value}

<DataTable data={driver_battles} rows=60 search=true download=true>
    <Column id=battle_number title="#" />
    <Column id=race_label title="Race" />
    <Column id=role title="Role" />
    <Column id=opponent title="Opponent" />
    <Column id=start_lap title="Start lap" />
    <Column id=end_lap title="End lap" />
    <Column id=position_contested title="For position" />
    <Column id=pressure_seconds title="Total pressure (sample-supported)" fmt="0 s" />
    <Column id=longest_pressure_run_s title="Longest pressure run" fmt="0 s" />
    <Column id=release_run_s title="Uninterrupted release" fmt="0 s" />
    <Column id=min_gap_s title="Minimum gap" fmt="0.000 s" />
    <Column id=driver_outcome title="Outcome" />
    <Column id=quick_reversal title="Reversed ≤60 s" />
    <Column id=confidence title="Evidence" />
</DataTable>

{:else}
<KeyInsight label="No driver profiles in this scope">
There is no usable Racecraft driver summary for this selection. Choose Season
to inspect covered races, or check the coverage table for the missing inputs.
</KeyInsight>
{/if}

```sql excluded_battles
select
    round,
    race_label,
    battle_number,
    attacker_code,
    defender_code,
    start_lap,
    pressure_seconds,
    longest_pressure_run_s,
    release_run_s,
    outcome,
    terminal_reason,
    exclusion_reason
from ${race_battles}
where not eligible
order by round, start_t_s
```

<ExpandableSection title="See excluded episodes and the v3 continuity method">
<DataTable data={excluded_battles} rows=80 search=true />

The follower must run directly behind the same car, on a comparable lap deficit,
for at least ten uninterrupted green-flag seconds within 1.0 second. Pressure
duration is sample-supported: ten consecutive one-second replay samples count
as ten seconds, not nine seconds between their timestamps. Total pressure may
include separate runs and is diagnostic only; eligibility uses the longest
uninterrupted run. High-confidence episodes need at least 20 seconds in that run,
alongside the other coverage and evidence requirements. A confirmed directional
pass can arrive up to three seconds after that close-running segment. A defence
requires the original order to remain while the gap exceeds 2.0 seconds for 15
measured elapsed seconds. The release timer resets at any gap of 2.0 seconds or
less (including the 1.5–2.0-second neutral band), a missing or invalid gap,
an incomparable lap deficit, or a missed expected replay sample. Pressure runs
also reset on gaps above 1.0 second or missing expected samples.
Pit-boundary laps and neutralisations interrupt rather than resolve the episode.
Without a matching confirmed pass, a third car entering the pair also interrupts
it, while feed gaps and race-end boundaries remain unresolved.

A quick reversal is a confirmed pass back within 60 seconds. The original
defender receives the re-pass made; the original attacker receives the re-pass
conceded. It does not erase the initial confirmed conversion.

Replay gaps are reconstructed at one-second resolution and are not official DRS
eligibility. Results are descriptive: car and tyre performance, fuel, damage,
track layout, DRS zones, strategy, team orders and opponent quality are not
controlled. Same-team episodes never receive high confidence.
</ExpandableSection>

<RelatedAnalysis section="drivers" current="racecraft-battles" season={inputs.season.value} race={inputs.race.value} />
