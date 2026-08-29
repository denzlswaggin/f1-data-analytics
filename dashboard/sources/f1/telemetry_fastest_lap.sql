-- Telemetry for each driver's fastest race lap only — a compact, representative
-- subset (the full mart_lap_telemetry is far too large to load into the browser).
with available_laps as (
    select distinct season, round, driver_code, lap_number
    from marts.mart_lap_telemetry
),

fastest as (
    select
        available_laps.season,
        available_laps.round,
        available_laps.driver_code,
        arg_min(available_laps.lap_number, laps.lap_time_sec) as lap_number
    from available_laps
    join marts.mart_lap_times as laps
        on laps.season = available_laps.season
        and laps.round = available_laps.round
        and laps.driver_code = available_laps.driver_code
        and laps.lap_number = available_laps.lap_number
    group by available_laps.season, available_laps.round, available_laps.driver_code
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
