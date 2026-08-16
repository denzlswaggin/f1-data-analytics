-- Telemetry for each driver's fastest race lap only — a compact, representative
-- subset (the full mart_lap_telemetry is far too large to load into the browser).
with fastest as (
    select
        season,
        round,
        driver_code,
        arg_min(lap_number, lap_time_sec) as lap_number
    from marts.mart_lap_times
    group by season, round, driver_code
)

select
    t.season,
    t.round,
    t.race_name,
    t.driver_code,
    t.driver_name,
    t.lap_number,
    t.compound,
    t.distance_m,
    t.speed_kph,
    t.throttle,
    t.brake,
    t.drs,
    t.gear,
    t.x,
    t.y
from marts.mart_lap_telemetry t
join fastest f
    on f.season = t.season
    and f.round = t.round
    and f.driver_code = t.driver_code
    and f.lap_number = t.lap_number
order by t.race_name, t.driver_code, t.distance_m
