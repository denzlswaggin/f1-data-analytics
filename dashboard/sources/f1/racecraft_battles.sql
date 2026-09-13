with episodes as (
select
    season,
    round,
    race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') as race_label,
    battle_id,
    battle_number,
    attacker_code,
    attacker_name,
    attacker_team,
    defender_code,
    defender_name,
    defender_team,
    same_team,
    start_t_s,
    end_t_s,
    duration_s,
    pressure_seconds,
    longest_pressure_run_s,
    release_run_s,
    contact_seconds,
    start_lap,
    end_lap,
    laps_spanned,
    position_contested,
    valid_samples,
    pressure_samples,
    coverage_pct,
    same_lap_deficit_share_pct,
    min_gap_s,
    median_gap_s,
    outcome,
    terminal_reason,
    converted,
    defender_retained,
    pass_t_s,
    pass_lap,
    time_to_pass_s,
    overtake_confidence,
    overtake_reason,
    quick_reversal,
    reversal_t_s,
    eligible,
    exclusion_reason,
    confidence,
    methodology_version
from marts.racecraft_battles

union all
select
    0, 0, '__NO_DATA__', 'R00 · No data', '__NO_DATA__', 0,
    '__NO_DATA__', '__NO_DATA__', '__NO_DATA__', '__NO_DATA__',
    '__NO_DATA__', '__NO_DATA__', false,
    cast(null as double), cast(null as double), cast(null as double),
    cast(null as double), cast(null as double),
    cast(null as double), cast(null as double), cast(null as integer),
    cast(null as integer), cast(null as integer), cast(null as integer),
    cast(null as integer), cast(null as integer), cast(null as double),
    cast(null as double), cast(null as double), cast(null as double),
    'Unavailable', 'no_data', false, false, cast(null as double),
    cast(null as integer), cast(null as double), cast(null as double),
    'No data', false, cast(null as double), false, 'No data',
    'insufficient', 'racecraft-v3-continuity'
where not exists (select 1 from marts.racecraft_battles)
), lap_context as (
    -- Ambiguous lap keys must not duplicate episodes or invent tyre context.
    select season, round, driver_code, lap_number,
        case when count(*) = 1 then max(compound) end as compound,
        case when count(*) = 1 then max(try_cast(tyre_life as double)) end as tyre_life
    from staging.stg_laps
    where session = 'R'
    group by season, round, driver_code, lap_number
), start_context as (
    select e.battle_id, e.season, e.round,
        max(case when r.driver_code = e.defender_code then r.lap_number end) as defender_start_lap
    from episodes e
    left join marts.race_replay r on r.season = e.season and r.round = e.round
        and r.t_s = e.start_t_s and r.driver_code = e.defender_code
    group by e.battle_id, e.season, e.round
)
select e.*,
    a.compound as attacker_compound,
    a.tyre_life as attacker_tyre_age_laps,
    d.compound as defender_compound,
    d.tyre_life as defender_tyre_age_laps,
    a.tyre_life - d.tyre_life as tyre_age_delta_laps
from episodes e
left join start_context c using (battle_id, season, round)
left join lap_context a on a.season = e.season and a.round = e.round
    and a.driver_code = e.attacker_code and a.lap_number = e.start_lap
left join lap_context d on d.season = e.season and d.round = e.round
    and d.driver_code = e.defender_code and d.lap_number = c.defender_start_lap
order by e.season, e.round, e.battle_number
