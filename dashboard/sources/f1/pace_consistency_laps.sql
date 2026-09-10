select
    season,
    round,
    race_name,
    driver_code,
    driver_name,
    team,
    lap_number,
    stint,
    compound,
    tyre_life,
    lap_time_sec,
    air_state,
    replay_coverage_pct,
    controlled_pace_delta_sec,
    expected_controlled_pace_delta_sec,
    pace_residual_sec,
    absolute_residual_sec,
    slow_lap_threshold_sec,
    unexplained_slow_excess_sec,
    is_unexplained_slow_lap,
    lap_eligible,
    lap_exclusion_reason,
    stint_clean_laps,
    stint_slope_sec_per_tyre_lap,
    stint_intercept_sec,
    methodology_version
from marts.pace_consistency_laps

union all
select
    0, 0, '__NO_DATA__', '__NO_DATA__', '__NO_DATA__', '__NO_DATA__',
    0, 0, '__NO_DATA__', cast(null as double), cast(null as double),
    'unavailable', cast(null as double), cast(null as double), cast(null as double),
    cast(null as double), cast(null as double), cast(null as double), cast(null as double),
    false, false, 'No data', 0, cast(null as double), cast(null as double),
    'pace-consistency-v3-robust-peers'
where not exists (select 1 from marts.pace_consistency_laps)
order by season, round, driver_code, stint, lap_number
