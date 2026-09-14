-- Modelled pass events detected from the replay feed (analytics/overtakes.py), on the
-- shared race clock (t_s seconds since the green light) so the markers line up with
-- the animation. One row per clean, close, sustained pass — a car directly behind
-- takes the position and holds it, with the two cars physically side-by-side (which
-- is what separates a real pass from a pit-cycle swap).
select
    o.season,
    o.round,
    cast(o.season as varchar) || ' ' || rc.race_name as race_name,
    o.t_s,
    o.for_position,
    o.passer_code,
    o.passed_code,
    o.gap_at_pass_s,
    o.confidence,
    o.evidence,
    o.reason
from marts.race_overtakes o
left join staging.stg_races rc
    on rc.season = o.season
    and rc.round = o.round

-- See race_replay.sql: prevent Evidence from emitting an invalid empty Parquet.
union all
select
    0,
    0,
    '__NO_DATA__',
    cast(0 as double),
    0,
    '__NO_DATA__',
    '__NO_DATA__',
    cast(0 as double),
    cast(0 as double),
    'no replay data',
    'unavailable'
where not exists (select 1 from marts.race_overtakes)
order by race_name, t_s
