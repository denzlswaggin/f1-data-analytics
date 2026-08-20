-- Per-driver tyre-stint sequence for the tyre-strategy gantt. race_label prefixes
-- the season so the picker can disambiguate races that share a name across years
-- (e.g. 2024 vs 2026 "Bahrain Grand Prix").
select
    season,
    round,
    race_name,
    cast(season as varchar) || ' ' || race_name as race_label,
    driver_code,
    driver_name,
    team,
    stint,
    compound,
    start_lap,
    end_lap,
    stint_laps,
    tyre_life_end,
    started_fresh,
    finish_position,
    deg_sec_per_lap
from marts.mart_stint_strategy
order by season desc, race_name, finish_position, stint
