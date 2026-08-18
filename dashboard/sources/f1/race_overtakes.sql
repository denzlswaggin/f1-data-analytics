-- On-track overtakes detected from the replay feed (analytics/overtakes.py), on the
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
    o.gap_at_pass_s
from marts.race_overtakes o
left join staging.stg_races rc
    on rc.season = o.season
    and rc.round = o.round
order by rc.race_name, o.t_s
