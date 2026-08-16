select
    season,
    round,
    race_name,
    driver_code,
    driver_name,
    team,
    n_laps,
    top_speed_kph,
    avg_speed_kph
from marts.mart_speed_trap
order by race_name, top_speed_kph desc
