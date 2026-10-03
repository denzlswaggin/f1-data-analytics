select
    cast(season as integer) as season,
    cast(round as integer) as round,
    session,
    cast(session_key as bigint) as session_key,
    cast(meeting_key as bigint) as meeting_key,
    status,
    anchor_source,
    cast(anchor_row_count as integer) as anchor_row_count,
    anchor_sha256,
    cast(anchor_count as integer) as anchor_count,
    cast(inlier_anchor_count as integer) as inlier_anchor_count,
    cast(anchor_driver_count as integer) as anchor_driver_count,
    cast(inlier_ratio as double precision) as inlier_ratio,
    cast(alignment_p95_s as double precision) as alignment_p95_s,
    clock_zero_utc,
    exclusion_reason,
    cast(position_row_count as bigint) as position_row_count,
    cast(interval_row_count as bigint) as interval_row_count,
    cast(control_row_count as bigint) as control_row_count
from {{ source('raw', 'openf1_timing_audit') }}
where {{ season_in_context('season') }}
