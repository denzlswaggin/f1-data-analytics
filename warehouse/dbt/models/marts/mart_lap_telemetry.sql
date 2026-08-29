-- Race-lap telemetry with driver + tyre context, ready for speed traces and
-- track maps. One row per driver per lap per distance point (race sessions).
-- Built from stg_telemetry, enriched with compound/stint (stg_laps), race name
-- (stg_races) and the Ergast driver_id/name (stg_driver_codes).
--
-- Incremental: telemetry is the highest-volume mart (~242k rows per race), so
-- dbt replaces complete race partitions instead of dropping the whole table.
-- raw.ingestion_partitions is the durable touched-partition manifest. A rerun
-- selects only races whose raw load timestamp is newer than the version already
-- in this mart; `delete+insert` replaces each complete (season, round), applying
-- late corrections and removing stale points on both DuckDB and Postgres.
{{
    config(
        materialized="incremental",
        unique_key=["season", "round"],
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
),

telemetry_loads as (
    select
        season,
        round,
        max(loaded_at) as source_loaded_at
    from {{ source('raw', 'ingestion_partitions') }}
    where resource = 'telemetry'
    group by season, round
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
    tel.y,
    coalesce(
        telemetry_loads.source_loaded_at,
        cast('1970-01-01 00:00:00' as timestamp)
    ) as source_loaded_at
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
left join telemetry_loads
    on telemetry_loads.season = tel.season
    and telemetry_loads.round = tel.round
{% if is_incremental() %}
where not exists (
    select 1
    from {{ this }} as existing
    where existing.season = tel.season
        and existing.round = tel.round
        and existing.source_loaded_at >= coalesce(
            telemetry_loads.source_loaded_at,
            cast('1970-01-01 00:00:00' as timestamp)
        )
)
{% endif %}
