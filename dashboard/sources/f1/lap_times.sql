select
    season,
    round,
    race_name,
    driver_code,
    team,
    lap_number,
    stint,
    compound,
    tyre_life,
    position,
    lap_time_sec
from marts.mart_lap_times
order by race_name, driver_code, lap_number
