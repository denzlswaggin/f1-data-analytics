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
    comparable_laps,
    stint_length,
    adjusted_deg_sec_per_lap,
    raw_deg_sec_per_lap,
    adjustment_delta,
    late_stint_loss_sec,
    cliff_signal
from marts.mart_adjusted_stint_degradation
order by season desc, round desc, driver_code, stint
