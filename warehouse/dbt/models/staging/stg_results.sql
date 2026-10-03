-- One clean row per driver per race: typed fields, surrogate keys, and a
-- classification flag. Race finishing data (used for context, not the pace
-- rating, which is qualifying-based).
with source as (
    select * from {{ source('raw', 'results') }}
    where {{ season_in_context('season') }}
),

renamed as (
    select
        {{ dbt_utils.generate_surrogate_key(['season', 'round', 'driver_id']) }} as result_key,
        {{ dbt_utils.generate_surrogate_key(['season', 'round']) }}              as race_key,
        cast(season as integer)                                                  as season,
        cast(round as integer)                                                   as round,
        driver_id,
        driver_code,
        trim(driver_given_name || ' ' || driver_family_name)                     as driver_name,
        driver_nationality,
        constructor_id,
        cast(grid as integer)                                                    as grid_position,
        cast(position as integer)                                                as finish_position,
        position_text,
        cast(points as double precision)                                         as points,
        cast(laps as integer)                                                    as laps,
        status,
        cast(time_millis as bigint)                                              as time_millis,
        -- Jolpica positionText carries classification independently of status.
        -- Classified drivers can retire; missing/unrecognised evidence stays unknown.
        case
            when cast(position as integer) > 0
                and trim(position_text) = cast(cast(position as integer) as varchar) then true
            when trim(position_text) in ('R', 'D', 'W', 'F') then false
        end                                                                      as is_classified
    from source
)

select * from renamed
