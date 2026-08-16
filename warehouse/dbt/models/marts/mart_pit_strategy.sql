-- Undercut/overcut outcome per pit stop.
--
-- For each stop, compare the driver's track position the lap *before* the stop
-- with their position two laps *after* it — the window over which an under/
-- overcut plays out. `positions_gained` > 0 means places gained across the
-- cycle. Ergast-sourced: per-lap positions (~1996+) joined to pit-stop timing
-- (~2011+). Null positions (e.g. a stop on lap 1) leave the delta null.
with stops as (
    select * from {{ ref('stg_pitstops') }}
),

positions as (
    select season, round, driver_id, lap_number, position
    from {{ ref('stg_ergast_laps') }}
),

races as (
    select season, round, race_name from {{ ref('stg_races') }}
),

drivers as (
    select driver_id, driver_name from {{ ref('stg_drivers') }}
),

joined as (
    select
        stops.season,
        stops.round,
        stops.driver_id,
        stops.stop_number,
        stops.pit_lap,
        stops.duration_sec,
        before_pos.position                                 as position_before,
        after_pos.position                                  as position_after
    from stops
    left join positions as before_pos
        on before_pos.season = stops.season
        and before_pos.round = stops.round
        and before_pos.driver_id = stops.driver_id
        and before_pos.lap_number = stops.pit_lap - 1
    left join positions as after_pos
        on after_pos.season = stops.season
        and after_pos.round = stops.round
        and after_pos.driver_id = stops.driver_id
        and after_pos.lap_number = stops.pit_lap + 2
)

select
    joined.season,
    joined.round,
    races.race_name,
    joined.driver_id,
    drivers.driver_name,
    joined.stop_number,
    joined.pit_lap,
    joined.duration_sec,
    joined.position_before,
    joined.position_after,
    joined.position_before - joined.position_after          as positions_gained
from joined
left join races
    on races.season = joined.season
    and races.round = joined.round
left join drivers
    on drivers.driver_id = joined.driver_id
