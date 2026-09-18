-- Per-driver tyre-stint strategy for a race: one row per stint (season, round,
-- driver, stint) with the compound run and the lap span it covered — the raw
-- material for the classic F1 "strategy chart" (a per-driver gantt of stints
-- coloured by compound, with pit stops sitting at the stint boundaries).
--
-- Built from stg_laps (session='R'), NOT mart_lap_times: the lap-times mart keeps
-- only green-flag, validly-timed laps, which would drop out-laps / SC laps and
-- leave gaps between stints. Here we keep every race lap so the spans are
-- contiguous (end_lap[n] + 1 = start_lap[n+1], i.e. a pit stop). driver_id /
-- driver_name bridge through stg_driver_codes and race_name through stg_races,
-- mirroring mart_lap_times.
with laps as (
    select * from {{ ref('stg_laps') }}
    where session = 'R'
        and stint is not null
),

races as (
    select season, round, race_name from {{ ref('stg_races') }}
),

driver_codes as (
    select season, driver_code, driver_id, driver_name from {{ ref('stg_driver_codes') }}
),

-- Official recorded classification, including classified retirements.
finishing as (
    select season, round, driver_code, finish_position
    from {{ ref('stg_results') }}
),

stints as (
    select
        season,
        round,
        driver_code,
        stint,
        max(team)                             as team,
        -- FastF1 occasionally reports the compound as the string 'None' (or null)
        -- for a whole stint; bucket those as UNKNOWN rather than drop a real
        -- stint. Prefer any known compound seen in the stint over UNKNOWN.
        coalesce(
            max(case when compound is not null and compound <> 'None' then compound end),
            'UNKNOWN'
        )                                     as compound,
        min(lap_number)                       as start_lap,
        max(lap_number)                       as end_lap,
        max(lap_number) - min(lap_number) + 1 as stint_laps,
        max(tyre_life)                        as tyre_life_end,
        bool_or(is_fresh_tyre)                as started_fresh
    from laps
    group by season, round, driver_code, stint
)

select
    stints.season,
    stints.round,
    races.race_name,
    stints.driver_code,
    driver_codes.driver_id,
    driver_codes.driver_name,
    stints.team,
    stints.stint,
    stints.compound,
    stints.start_lap,
    stints.end_lap,
    stints.stint_laps,
    stints.tyre_life_end,
    stints.started_fresh,
    finishing.finish_position,
    deg.deg_sec_per_lap
from stints
left join races
    on stints.season = races.season
    and stints.round = races.round
-- Bridge the FastF1 driver_code to the Ergast driver_id / display name.
left join driver_codes
    on stints.season = driver_codes.season
    and stints.driver_code = driver_codes.driver_code
left join finishing
    on stints.season = finishing.season
    and stints.round = finishing.round
    and stints.driver_code = finishing.driver_code
-- Tyre fall-off (sec/lap) for the stint, reused from mart_stint_degradation
-- (same grain). Null when the stint had too few green laps for a stable fit.
left join {{ ref('mart_stint_degradation') }} as deg
    on stints.season = deg.season
    and stints.round = deg.round
    and stints.driver_code = deg.driver_code
    and stints.stint = deg.stint
