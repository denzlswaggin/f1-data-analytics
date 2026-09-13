-- round = 0 denotes the season. Aggregate episodes, never per-race percentages.
with roster as (
    select season, coalesce(round, 0) as round, driver_code,
        max(driver_name) as driver_name,
        string_agg(distinct team, ', ' order by team) as team,
        count(distinct round) as races_covered
    from marts.racecraft_driver_summary
    group by grouping sets ((season, round, driver_code), (season, driver_code))
), roles as (
    select season, round, battle_id, attacker_code as driver_code,
        defender_code as opponent, 'attack' as role, eligible,
        converted as success, confidence, pressure_seconds, outcome, time_to_pass_s,
        false as reversal_made, quick_reversal as reversal_conceded
    from marts.racecraft_battles
    union all
    select season, round, battle_id, defender_code, attacker_code, 'defence', eligible,
        defender_retained, confidence, pressure_seconds, outcome, null,
        quick_reversal, false
    from marts.racecraft_battles
), counts as (
    select season, coalesce(round, 0) as round, driver_code, role,
        count(*) filter (where eligible) as n,
        count(*) filter (where eligible and success) as successes,
        count(*) filter (where eligible and confidence = 'high') as high_n,
        count(*) as observed_episodes,
        sum(pressure_seconds) as observed_pressure_s,
        count(distinct opponent) as distinct_opponents,
        median(time_to_pass_s) filter (where eligible and success) as median_time_to_pass_s,
        count(*) filter (where outcome = 'Interrupted') as interrupted,
        count(*) filter (where outcome = 'Unresolved') as unresolved,
        count(*) filter (where reversal_made) as reversals_made,
        count(*) filter (where reversal_conceded) as reversals_conceded
    from roles
    group by grouping sets ((season, round, driver_code, role), (season, driver_code, role))
), proportions as (
    select *, successes * 1.0 / nullif(n, 0) as p,
        1.6448536269514722 as z
    from counts
), rates as (
    select *,
        case when n >= 5 then 100 * p end as rate_pct,
        case when n >= 5 then 100 *
            ((p + z*z/(2*n)) - z * sqrt(p*(1-p)/n + z*z/(4*n*n))) / (1+z*z/n)
        end as lower_pct,
        case when n >= 5 then 100 *
            ((p + z*z/(2*n)) + z * sqrt(p*(1-p)/n + z*z/(4*n*n))) / (1+z*z/n)
        end as upper_pct,
        case when n = 0 then 'insufficient' when n < 5 then 'low'
            when n >= 10 and high_n * 1.0 / n >= 0.8 then 'high'
            else 'medium' end as evidence
    from proportions
)
select r.*,
    coalesce(a.n, 0) as attacking_opportunities,
    coalesce(a.successes, 0) as converted_opportunities,
    a.rate_pct as attack_conversion_pct,
    a.lower_pct as attack_conversion_p05_pct,
    a.upper_pct as attack_conversion_p95_pct,
    coalesce(a.n >= 5, false) as offense_eligible,
    coalesce(a.evidence, 'insufficient') as offense_confidence,
    coalesce(d.n, 0) as defensive_opportunities,
    coalesce(d.successes, 0) as defences_held,
    d.rate_pct as defence_hold_pct,
    d.lower_pct as defence_hold_p05_pct,
    d.upper_pct as defence_hold_p95_pct,
    coalesce(d.n >= 5, false) as defense_eligible,
    coalesce(d.evidence, 'insufficient') as defense_confidence,
    coalesce(a.observed_episodes, 0) as observed_attacks,
    coalesce(d.observed_episodes, 0) as observed_defences,
    coalesce(a.observed_pressure_s, 0) as observed_attack_pressure_s,
    coalesce(d.observed_pressure_s, 0) as observed_defensive_pressure_s,
    coalesce(a.distinct_opponents, 0) as distinct_defenders,
    coalesce(d.distinct_opponents, 0) as distinct_attackers,
    a.median_time_to_pass_s,
    coalesce(a.interrupted, 0) as interrupted_attacks,
    coalesce(d.interrupted, 0) as interrupted_defences,
    coalesce(a.unresolved, 0) as unresolved_attacks,
    coalesce(d.unresolved, 0) as unresolved_defences,
    coalesce(d.reversals_made, 0) as quick_reversals_made,
    coalesce(a.reversals_conceded, 0) as quick_reversals_conceded
from roster r
left join rates a on a.season = r.season and a.round = r.round
    and a.driver_code = r.driver_code and a.role = 'attack'
left join rates d on d.season = r.season and d.round = r.round
    and d.driver_code = r.driver_code and d.role = 'defence'
order by r.season, r.round, r.driver_code
