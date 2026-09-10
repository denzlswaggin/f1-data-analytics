select
    season,
    round,
    race_name,
    driver_code,
    driver_name,
    team,
    stop_number,
    actual_pit_lap,
    actual_out_lap,
    shift_laps,
    hypothetical_pit_lap,
    hypothetical_out_lap,
    estimated_cost_index_sec,
    delta_vs_actual_sec,
    estimated_gain_vs_actual_sec,
    delta_p25_sec,
    delta_p75_sec,
    old_tyre_extension_laps,
    supported,
    exclusion_reason,
    methodology_version
from marts.pit_timing_scenarios

union all
select
    0, 0, '__NO_DATA__', '__NO_DATA__', '__NO_DATA__', '__NO_DATA__',
    0, 0, 0, 0, 0, 0, cast(null as double), cast(null as double),
    cast(null as double), cast(null as double), cast(null as double), 0,
    false, 'No data', 'pit-timing-sensitivity-v1'
where not exists (select 1 from marts.pit_timing_scenarios)
order by season, round, driver_code, stop_number, shift_laps
