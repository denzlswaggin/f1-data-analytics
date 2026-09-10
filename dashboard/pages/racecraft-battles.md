---
title: Racecraft Battle Conversion
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
from f1.racecraft_driver_summary
where season > 0
order by season desc
```

```sql races
select distinct
    round,
    race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') as race_label
from f1.racecraft_driver_summary
where season = ${inputs.season.value}
order by round
```

<FilterBar title="Choose a race" description="Races are ordered by championship round; every replay-covered driver remains in the summary even with zero eligible battles.">
    <Dropdown data={seasons} name=season value=season title="Season" />
    <Dropdown data={races} name=race value=round label=race_label order="round asc" title="Race" />
</FilterBar>

```sql coverage
select * from f1.data_coverage
where section = 'racecraft'
    and race_label = (
        select cast(season as varchar) || ' ' || race_name
        from f1.racecraft_driver_summary
        where season = ${inputs.season.value} and round = ${inputs.race.value}
        limit 1
    )
```

<DataTrust data={coverage} sampleLabel="observed battle episodes" entityLabel="Attackers" method="direct-ahead replay gaps; confirmed overtake matching" />

```sql race_drivers
select *
from f1.racecraft_driver_summary
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by greatest(attacking_opportunities, defensive_opportunities) desc, driver_code
```

```sql race_battles
select *
from f1.racecraft_battles
where season = ${inputs.season.value} and round = ${inputs.race.value}
order by start_t_s, battle_number
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

## Attack and defence rates — {inputs.season.value} {inputs.race.label}

Rates appear only after five eligible resolved opportunities in the relevant
role: attack rate is conversions / attack n; defence rate is holds / defence n.
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

```sql two_way_evidence
select * from ${race_drivers}
where offense_eligible and defense_eligible
```

## Two-way battle profile

The chart deliberately keeps attack and defence separate. It does not combine
them into an arbitrary racecraft score, and drivers without five opportunities
on both axes are omitted.

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

<DataTable data={race_drivers} rows=25 search=true download=true>
    <Column id=driver_code title="Driver" />
    <Column id=team title="Team" />
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

```sql drivers
select driver_code
from ${race_drivers}
order by driver_code
```

<FilterBar title="Inspect one driver's battles" description="Both attacking and defending episodes are shown chronologically; interrupted and unresolved evidence remains visible.">
    <Dropdown data={drivers} name=driver value=driver_code title="Driver" />
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
order by start_t_s
```

## Episode evidence — {inputs.driver.value}

<DataTable data={driver_battles} rows=60 search=true download=true>
    <Column id=battle_number title="#" />
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

```sql excluded_battles
select
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
order by start_t_s
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
