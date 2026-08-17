-- Animated race-replay positions: one row per car per time tick, on the shared
-- race clock (t_s seconds since the green light). Lean by design — names, teams
-- and colours come from race_replay_meta and are joined client-side in the
-- TrackMap component so this (large) feed stays compact.
select
    r.season,
    r.round,
    cast(r.season as varchar) || ' ' || rc.race_name as race_name,
    r.driver_code,
    r.t_s,
    r.x,
    r.y,
    r.running_order,
    r.gap_to_leader_s,
    r.gap_to_ahead_s
from marts.race_replay r
left join staging.stg_races rc
    on rc.season = r.season
    and rc.round = r.round
order by rc.race_name, r.driver_code, r.t_s
