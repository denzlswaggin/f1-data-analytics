-- Race-lap telemetry with driver + tyre context, ready for speed traces and
-- track maps. One row per driver per lap per distance point (race sessions).
-- Built from stg_telemetry, enriched with compound/stint (stg_laps), race name
-- (stg_races) and the Ergast driver_id/name (stg_driver_codes).
with tel as (
    select * from {{ ref('stg_telemetry') }}
    where session = 'R'
),

laps as (
    select
        season, round, session, driver_code, lap_number, compound, stint
    from {{ ref('stg_laps') }}
),

races as (
    select season, round, race_name from {{ ref('stg_races') }}
),

driver_codes as (
    select season, driver_code, driver_id, driver_name from {{ ref('stg_driver_codes') }}
)

select
    tel.season,
    tel.round,
    races.race_name,
    tel.driver_code,
    driver_codes.driver_id,
    driver_codes.driver_name,
    tel.lap_number,
    laps.compound,
    laps.stint,
    tel.distance_m,
    tel.speed_kph,
    tel.throttle,
    tel.brake,
    tel.drs,
    tel.gear,
    tel.rpm,
    tel.x,
    tel.y
from tel
left join laps
    on laps.season = tel.season
    and laps.round = tel.round
    and laps.session = tel.session
    and laps.driver_code = tel.driver_code
    and laps.lap_number = tel.lap_number
left join races
    on races.season = tel.season
    and races.round = tel.round
left join driver_codes
    on driver_codes.season = tel.season
    and driver_codes.driver_code = tel.driver_code
