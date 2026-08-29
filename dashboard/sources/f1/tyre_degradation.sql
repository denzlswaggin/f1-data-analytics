select
    season,
    round,
    race_name,
    cast(season as varchar) || ' ' || race_name as race_label,
    compound,
    n_laps,
    deg_sec_per_lap,
    best_lap_sec,
    avg_lap_sec
from marts.mart_tyre_degradation
order by race_name, deg_sec_per_lap desc
