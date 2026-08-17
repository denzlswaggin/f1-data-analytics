-- One clean, typed row per official race-control message (FastF1), on the shared
-- session clock (session_time_sec). Flags, safety car, penalties, incidents, DRS.
-- Non-driver messages (e.g. sector flags) have a null driver_code. The F1 feed can
-- emit a message twice at the same instant, so exact duplicates are dropped.
{% set msg_cols = [
    'season', 'round', 'session', 'session_time_sec', 'category', 'flag',
    'scope', 'sector', 'message', 'driver_number', 'lap'
] %}

with source as (
    select * from {{ source('raw', 'race_control') }}
),

deduped as (
    select
        *,
        row_number() over (
            partition by {{ msg_cols | join(', ') }}
            order by session_time_sec
        ) as _rn
    from source
),

renamed as (
    select
        {{ dbt_utils.generate_surrogate_key(msg_cols) }}    as message_key,
        cast(season as integer)                             as season,
        cast(round as integer)                              as round,
        session,
        cast(session_time_sec as double precision)          as session_time_sec,
        category,
        flag,
        scope,
        cast(sector as integer)                             as sector,
        message,
        driver_number,
        driver_code,
        cast(lap as integer)                                as lap
    from deduped
    where _rn = 1
)

select * from renamed
