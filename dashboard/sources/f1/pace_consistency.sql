select
    season,
    round,
    race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') as race_label,
    driver_code,
    driver_name,
    team,
    candidate_laps,
    modelled_laps,
    excluded_laps,
    candidate_stints,
    modelled_stints,
    robust_consistency_sec,
    robust_consistency_pct,
    p90_slow_tail_sec,
    slow_lap_threshold_sec,
    unexplained_slow_laps,
    unexplained_slow_lap_share_pct,
    unexplained_slow_lap_cost_sec,
    slow_lap_cost_per_10_laps_sec,
    worst_residual_sec,
    replay_coverage_pct,
    consistency_eligible,
    exclusion_reason,
    confidence,
    methodology_version
from marts.pace_consistency

-- Typed sentinel for Evidence's empty-source Parquet edge case. Season zero is
-- excluded by every visible query.
union all
select
    0, 0, '__NO_DATA__', 'R00 · No data', '__NO_DATA__', '__NO_DATA__',
    '__NO_DATA__', 0, 0, 0, 0, 0,
    cast(null as double), cast(null as double), cast(null as double),
    cast(null as double), 0, cast(null as double), cast(null as double),
    cast(null as double), cast(null as double), cast(null as double), false,
    'No data', 'insufficient', 'pace-consistency-v2-pit-context'
where not exists (select 1 from marts.pace_consistency)
order by season, round, driver_code
