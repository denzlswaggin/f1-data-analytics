select
    season,
    round,
    race_name,
    'R' || lpad(cast(round as varchar), 2, '0') || ' · '
        || replace(race_name, ' Grand Prix', '') as race_label,
    driver_code,
    driver_name,
    team,
    stint,
    compound,
    is_fresh_tyre,
    out_lap,
    stint_start_lap,
    stint_end_lap,
    stint_laps,
    contiguous_stint_transition,
    clean_evaluation_laps,
    traffic_evaluation_laps,
    mature_reference_laps,
    baseline_slope_sec_per_lap,
    baseline_intercept_sec,
    baseline_mad_sec,
    first_flying_warmup_loss_sec,
    second_flying_warmup_loss_sec,
    first_two_lap_warmup_cost_sec,
    stable_band_sec,
    stable_window_start_lap,
    time_to_pace_laps,
    first_observed_confirmation_laps,
    confirmation_history_complete,
    settling_status,
    stable_pace_achieved,
    right_censored,
    observation_complete,
    warmup_eligible,
    crossover_eligible,
    exclusion_reason,
    confidence,
    replay_coverage_pct,
    methodology_version
from marts.tyre_warmup

-- Typed sentinel for Evidence's empty-source Parquet edge case. Season zero is
-- excluded by every visible query.
union all
select
    0, 0, '__NO_DATA__', 'R00 · No data', '__NO_DATA__', '__NO_DATA__',
    '__NO_DATA__', 0, '__NO_DATA__', false, 0, 0, 0, 0, false,
    0, 0, 0,
    cast(null as double), cast(null as double), cast(null as double),
    cast(null as double), cast(null as double), cast(null as double),
    cast(0.5 as double), null, null, cast(null as integer), false, 'unavailable',
    false, false, false, false, false,
    'No data', 'Insufficient', cast(null as double), 'tyre-warmup-v3-observation'
where not exists (select 1 from marts.tyre_warmup)
order by season, round, driver_code, stint
