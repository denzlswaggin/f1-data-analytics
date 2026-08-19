-- Race-lap telemetry with driver + tyre context, ready for speed traces and
-- track maps. One row per driver per lap per distance point (race sessions).
-- Built from stg_telemetry, enriched with compound/stint (stg_laps), race name
-- (stg_races) and the Ergast driver_id/name (stg_driver_codes).
--
-- Incremental: telemetry is the highest-volume mart (~242k rows per race), so it
-- is built race-by-race rather than fully rebuilt. Each run appends only races
-- (season, round) not already present. `delete+insert` on the row grain keeps a
-- re-ingested race idempotent (its rows are replaced, not duplicated), and works
-- on both DuckDB (dev) and Postgres (prod). A full rebuild: `dbt build
-- --full-refresh --select mart_lap_telemetry`.
{{
    config(
        materialized="incremental",
        unique_key=["season", "round", "driver_code", "lap_number", "distance_m"],
        incremental_strategy="delete+insert",
        on_schema_change="append_new_columns",
    )
}}
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
{% if is_incremental() %}
    -- Append only races not already materialised; existing races are untouched.
    where not exists (
        select 1
        from {{ this }} as existing
        where existing.season = tel.season
            and existing.round = tel.round
    )
{% endif %}
