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
A battle begins after at least ten seconds within one second of the car directly ahead. Conversion requires a confirmed order change; an unmatched episode only counts as a defence after a clean, sustained gap release. Car pace, tyres, fuel, damage, team orders and circuit layout remain part of every result.
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
    count(*) filter (where eligible and outcome = 'Defended') as defences
from ${race_battles}
```

<Grid cols=4>
    <BigValue data={race_totals} value=observed_battles title="Observed battles" />
    <BigValue data={race_totals} value=eligible_battles title="Eligible outcomes" />
    <BigValue data={race_totals} value=conversions title="Confirmed conversions" />
    <BigValue data={race_totals} value=defences title="Clean defences" />
</Grid>

## Attack and defence rates — {inputs.season.value} {inputs.race.label}

Rates appear only after five eligible opportunities in the relevant role. The
90% Wilson interval stays beside each estimate so a small sample cannot look
more decisive than it is.

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
    <Column id=attacking_opportunities title="Attacks" />
    <Column id=converted_opportunities title="Converted" />
    <Column id=attack_conversion_pct title="Attack (%)" fmt="0.0" />
    <Column id=attack_conversion_p05_pct title="Attack P05" fmt="0.0" />
    <Column id=attack_conversion_p95_pct title="Attack P95" fmt="0.0" />
    <Column id=defensive_opportunities title="Defences" />
    <Column id=defences_held title="Held" />
    <Column id=defence_hold_pct title="Defence (%)" fmt="0.0" />
    <Column id=defence_hold_p05_pct title="Defence P05" fmt="0.0" />
    <Column id=defence_hold_p95_pct title="Defence P95" fmt="0.0" />
    <Column id=quick_reversals_made title="Quick reversals" />
    <Column id=confidence title="Evidence" />
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
    <Column id=pressure_seconds title="Within 1.0 s" fmt="0 s" />
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
    outcome,
    terminal_reason,
    exclusion_reason
from ${race_battles}
where not eligible
order by start_t_s
```

<ExpandableSection title="See excluded episodes and the v1 method">
<DataTable data={excluded_battles} rows=80 search=true />

The follower must run directly behind the same car, on a comparable lap deficit,
for at least ten green-flag seconds within 1.0 second. A confirmed directional
pass can arrive up to three seconds after that close-running segment. A defence
requires the original order to remain while the gap exceeds 2.0 seconds for 15
seconds. Pit-boundary laps, neutralisations and a third car entering the pair
interrupt rather than resolve the episode. Feed gaps and race-end boundaries
remain unresolved.

Replay gaps are reconstructed at one-second resolution and are not official DRS
eligibility. Results are descriptive: car and tyre performance, fuel, damage,
track layout, DRS zones, strategy, team orders and opponent quality are not
controlled. Same-team episodes never receive high confidence.
</ExpandableSection>

<RelatedAnalysis section="drivers" current="racecraft-battles" season={inputs.season.value} race={inputs.race.value} />
