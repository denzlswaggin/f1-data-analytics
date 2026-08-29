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
        post_hook=(
            "update {{ this }} "
            "set source_loaded_at = cast('1970-01-01 00:00:00' as timestamp) "
            "where source_loaded_at is null"
        ),
    )
}}
{% if is_incremental() %}
    {% set existing_columns = adapter.get_columns_in_relation(this) | map(attribute='name') | list %}
{% endif %}
with raw_tel as (
    select * from {{ ref('stg_telemetry') }}
    where session = 'R'
),

telemetry_loads as (
    select
        partitions.season,
        partitions.round,
        coalesce(
            max(audit.loaded_at),
            cast('1970-01-01 00:00:00' as timestamp)
        ) as source_loaded_at
    from (select distinct season, round from raw_tel) as partitions
    left join {{ source('raw', 'ingestion_partitions') }} as audit
        on audit.resource = 'telemetry'
        and audit.season = partitions.season
        and audit.round = partitions.round
    group by partitions.season, partitions.round
),

{% if is_incremental() %}
existing_loads as (
    {% if 'source_loaded_at' in existing_columns %}
    select season, round, max(source_loaded_at) as source_loaded_at
    from {{ this }}
    group by season, round
    {% else %}
    select distinct season, round, cast(null as timestamp) as source_loaded_at
    from {{ this }}
    {% endif %}
),

refresh_partitions as (
    select telemetry_loads.*
    from telemetry_loads
    left join existing_loads
        on existing_loads.season = telemetry_loads.season
        and existing_loads.round = telemetry_loads.round
    where existing_loads.season is null
        or coalesce(
            existing_loads.source_loaded_at,
            cast('1970-01-01 00:00:00' as timestamp)
        ) < telemetry_loads.source_loaded_at
),
{% endif %}

tel as (
    select raw_tel.*
    from raw_tel
    {% if is_incremental() %}
    inner join refresh_partitions
        on refresh_partitions.season = raw_tel.season
        and refresh_partitions.round = raw_tel.round
    {% endif %}
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
