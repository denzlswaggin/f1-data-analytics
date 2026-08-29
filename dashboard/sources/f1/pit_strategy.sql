select
    season,
    round,
    race_name,
    cast(season as varchar) || ' ' || race_name as race_label,
    driver_id,
    driver_name,
    stop_number,
    pit_lap,
    duration_sec,
    position_before,
    position_after,
    positions_gained
from marts.mart_pit_strategy
order by race_name, driver_name, stop_number
