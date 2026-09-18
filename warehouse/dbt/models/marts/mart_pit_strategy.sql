-- Undercut/overcut outcome per pit stop.
--
-- For each stop, compare the driver's track position the lap *before* the stop
-- with their position two laps *after* it — the window over which an under/
-- overcut plays out. `positions_gained` > 0 means places gained across the
-- cycle. Jolpica pit-stop timing (~2011+) is joined to the FastF1 race laps
-- already loaded for the rest of the dashboard, avoiding a duplicate lap-data
-- backfill. Null positions (e.g. a stop on lap 1) leave the delta null.
with stops as (
    select * from {{ ref('stg_pitstops') }}
),

positions as (
    select
        laps.season,
        laps.round,
        codes.driver_id,
        laps.lap_number,
        laps.position
    from {{ ref('stg_laps') }} as laps
    inner join {{ ref('stg_driver_codes') }} as codes
        on codes.season = laps.season
        and codes.driver_code = laps.driver_code
    where laps.session = 'R'
        and laps.position is not null
),

races as (
    select season, round, race_name from {{ ref('stg_races') }}
),

drivers as (
    select distinct driver_id, driver_name from {{ ref('stg_driver_codes') }}
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
where exists (
    select 1 from {{ ref('stg_laps') }} as scope
    where scope.season = joined.season and scope.round = joined.round and scope.session = 'R'
)
