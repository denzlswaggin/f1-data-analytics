-- Compact lap-level replay context retained for coverage and diagnostics. The
-- full positional feed is served by the dedicated SvelteKit replay as per-race
-- Arrow bundles; do not duplicate it as a monolithic Evidence source.
with race_window as (
    select season, round, min(lap_start_sec) as race_start_sec
    from staging.stg_laps
    where session = 'R'
    group by season, round
)

select
    laps.season,
    laps.round,
    laps.driver_code,
    laps.lap_number,
    round(laps.lap_start_sec - win.race_start_sec, 3) as lap_start_t_s,
    laps.lap_time_sec,
    laps.stint,
    laps.compound,
    laps.tyre_life
from staging.stg_laps laps
join race_window win
    on win.season = laps.season
    and win.round = laps.round
where laps.session = 'R'
    and exists (
        select 1
        from marts.race_replay replay
        where replay.season = laps.season
            and replay.round = laps.round
            and replay.driver_code = laps.driver_code
    )
order by laps.season desc, laps.round, laps.driver_code, laps.lap_number
