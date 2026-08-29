select
    season,
    round,
    race_name,
    cast(season as varchar) || ' ' || race_name as race_label,
    driver_code,
    driver_name,
    team,
    n_laps,
    top_speed_kph,
    avg_speed_kph
from marts.mart_speed_trap
order by race_name, top_speed_kph desc
