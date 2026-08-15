-- Tyre-degradation rate per race and compound.
--
-- Fits a linear trend of lap time vs tyre age (regr_slope) across green-flag
-- laps: the slope is the pace lost per lap of tyre life (sec/lap; higher = the
-- compound "falls off" faster). Out-laps (tyre_life < 2) are excluded. This is a
-- pooled, first-order estimate — traffic and fuel burn add noise — but it
-- surfaces the expected soft > medium > hard degradation ordering.
with laps as (
    select * from {{ ref('mart_lap_times') }}
    where tyre_life >= 2 and compound is not null
)

select
    season,
    round,
    race_name,
    compound,
    count(*)                                as n_laps,
    regr_slope(lap_time_sec, tyre_life)     as deg_sec_per_lap,
    min(lap_time_sec)                       as best_lap_sec,
    avg(lap_time_sec)                       as avg_lap_sec
from laps
group by season, round, race_name, compound
having count(*) >= 8
