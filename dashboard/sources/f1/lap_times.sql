select
    season,
    round,
    race_name,
    cast(season as varchar) || ' ' || race_name as race_label,
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
