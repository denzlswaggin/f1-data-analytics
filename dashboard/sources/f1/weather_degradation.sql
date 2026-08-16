select
    season,
    round,
    race_name,
    compound,
    weather_bucket,
    avg_track_temp,
    avg_air_temp,
    n_laps,
    deg_sec_per_lap,
    avg_lap_sec
from marts.mart_weather_degradation
order by race_name, compound
