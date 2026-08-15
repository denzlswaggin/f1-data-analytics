select
    driver_id,
    driver_name,
    season,
    races_compared,
    teammate_quali_wins,
    teammate_win_pct,
    mean_pace_gap,
    stddev_pace_gap
from marts.mart_driver_season_pace
order by season, mean_pace_gap
