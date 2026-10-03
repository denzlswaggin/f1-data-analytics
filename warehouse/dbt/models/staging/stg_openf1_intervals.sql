with source as (
    select * from {{ source('raw', 'openf1_intervals') }}
    where {{ season_in_context('season') }}
)

select
    {{ dbt_utils.generate_surrogate_key(
        ['season', 'round', 'session', 'driver_number', 'session_time_sec']
    ) }} as openf1_interval_key,
    cast(season as integer) as season,
    cast(round as integer) as round,
    session,
    cast(session_key as bigint) as session_key,
    cast(meeting_key as bigint) as meeting_key,
    cast(session_time_sec as double precision) as session_time_sec,
    source_utc,
    driver_number,
    driver_code,
    gap_to_leader_raw,
    gap_to_ahead_raw,
    cast(gap_to_leader_s as double precision) as gap_to_leader_s,
    cast(gap_to_ahead_s as double precision) as gap_to_ahead_s,
    cast(leader_lap_deficit as integer) as leader_lap_deficit,
    cast(ahead_lap_deficit as integer) as ahead_lap_deficit,
    source_sha256
from source
where driver_code is not null
