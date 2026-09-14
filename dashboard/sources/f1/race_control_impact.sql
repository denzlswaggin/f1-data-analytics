select
    season,
    round,
    race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') as race_label,
    event_id,
    event_number,
    event_type,
    driver_code,
    driver_name,
    team,
    finish_position,
    result_status,
    position_before,
    position_after,
    positions_gained,
    gap_to_leader_before_s,
    gap_to_leader_after_s,
    raw_gap_gain_s,
    field_adjusted_gap_gain_s,
    lap_before,
    lap_after,
    lap_deficit_before,
    lap_deficit_after,
    lap_deficit_changed,
    stint_before,
    stint_after,
    compound_before,
    compound_after,
    tyre_life_before,
    tyre_life_after,
    pitted_during_intervention,
    pitted_during_recovery,
    pit_timing_class,
    pit_in_t_s,
    pit_out_t_s,
    pit_duration_sec,
    stop_count,
    tyre_changed_during_suspension,
    active_after,
    position_eligible,
    gap_eligible,
    pit_eligible,
    restart_eligible,
    tyre_eligible,
    focus_rank,
    eligible,
    time_comparable_driver_count,
    time_eligible,
    time_exclusion_reason,
    exclusion_reason,
    confidence,
    outcome_label,
    timing_before_offset_s,
    timing_after_offset_s,
    methodology_version
from (
    select impact.*, results.finish_position, results.status as result_status
    from marts.race_control_impact as impact
    left join staging.stg_results as results
        on results.season = impact.season
        and results.round = impact.round
        and results.driver_code = impact.driver_code
) as detail

union all
select
    0, 0, '__NO_DATA__', 'R00 · No data', '__NO_DATA__', 0, 'No event',
    '__NO_DATA__', 'No driver', 'No team', cast(null as integer), 'No data',
    cast(null as integer), cast(null as integer), cast(null as integer),
    cast(null as double), cast(null as double), cast(null as double), cast(null as double),
    cast(null as integer), cast(null as integer), cast(null as integer), cast(null as integer),
    false,
    cast(null as integer), cast(null as integer), '', '',
    cast(null as integer), cast(null as integer),
    false, false, 'no_stop_observed', cast(null as double), cast(null as double),
    cast(null as double), 0, false, false,
    false, false, false, false, false, cast(null as integer), false,
    0, false, 'No data',
    'No data', 'Low', 'Excluded',
    cast(null as double), cast(null as double), 'race-control-impact-v3'
where not exists (select 1 from marts.race_control_impact)
order by season, round, event_number, position_before
