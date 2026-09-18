-- Compact lap pool: fastest available green timing laps plus eligible DNA pairs.
-- Joint selection happens after choosing the two drivers, never independently.
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
),
selected as (
    select * from fastest
    union
    select season, round, driver_code, driver_lap_number as lap_number
    from marts.driver_dna_evidence
    where eligible
)

select
    t.season,
    t.round,
    t.race_name,
    cast(t.season as varchar) || ' ' || t.race_name as race_label,
    t.driver_code,
    t.driver_name,
    t.lap_number,
    t.compound,
    context.tyre_life,
    context.track_status,
    context.lap_time_sec,
    context.pit_in_time_sec,
    context.pit_out_time_sec,
    (t.lap_number = fastest.lap_number) as is_fastest_available,
    t.distance_m,
    t.speed_kph,
    t.throttle,
    t.brake,
    t.drs,
    t.gear,
    t.x,
    t.y
from marts.mart_lap_telemetry t
join selected f
    on f.season = t.season
    and f.round = t.round
    and f.driver_code = t.driver_code
    and f.lap_number = t.lap_number
join staging.stg_laps context
    on context.season = t.season and context.round = t.round
    and context.driver_code = t.driver_code and context.lap_number = t.lap_number
    and context.session = 'R'
left join fastest
    on fastest.season = t.season and fastest.round = t.round
    and fastest.driver_code = t.driver_code
order by t.season, t.round, t.driver_code, t.lap_number, t.distance_m
