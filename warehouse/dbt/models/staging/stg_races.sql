-- One clean row per race: typed keys, a stable surrogate key, and tidy names.
with source as (
    select * from {{ source('raw', 'races') }}
    where {{ season_in_context('season') }}
),

renamed as (
    select
        {{ dbt_utils.generate_surrogate_key(['season', 'round']) }} as race_key,
        cast(season as integer)                                    as season,
        cast(round as integer)                                     as round,
        race_name,
        cast(date as date)                                         as race_date,
        circuit_id,
        circuit_name,
        country,
        locality,
        cast(lat as double precision)                              as latitude,
        cast(long as double precision)                             as longitude
    from source
)

select * from renamed
