-- Straight-line speed per driver per race.
--
-- The speed-trap reading on the longest straight (SpeedST), summarised over
-- green-flag race laps — a proxy for power-unit output and low-drag efficiency.
-- FastF1-sourced (2024-2026); driver_id/name bridged via stg_driver_codes.
with laps as (
    select * from {{ ref('stg_laps') }}
    where session = 'R'
        and track_status = '1'
        and speed_st_kph is not null
),

races as (
    select season, round, race_name from {{ ref('stg_races') }}
),

driver_codes as (
    select season, driver_code, driver_id, driver_name from {{ ref('stg_driver_codes') }}
)

select
    laps.season,
    laps.round,
    races.race_name,
    laps.driver_code,
    driver_codes.driver_id,
    driver_codes.driver_name,
    laps.team,
    count(*)                                                as n_laps,
    max(laps.speed_st_kph)                                  as top_speed_kph,
    avg(laps.speed_st_kph)                                  as avg_speed_kph
from laps
left join races
    on races.season = laps.season
    and races.round = laps.round
left join driver_codes
    on driver_codes.season = laps.season
    and driver_codes.driver_code = laps.driver_code
group by
    laps.season,
    laps.round,
    races.race_name,
    laps.driver_code,
    driver_codes.driver_id,
    driver_codes.driver_name,
    laps.team
