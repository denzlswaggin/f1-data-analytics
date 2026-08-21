-- The race-pace gap must be antisymmetric: within one race, a team's two
-- teammates must report equal-and-opposite gaps, so their sum is zero.
--
-- This is the correctness gate on int_teammate_race_gaps. The model self-joins
-- laps and applies several filters (same compound, tyre-age window, outlier
-- trim); every one of them has to be symmetric in the two drivers, or the two
-- directions end up averaged over different lap sets and the gap silently stops
-- being a valid comparison. The rating solver assumes antisymmetry, so a break
-- here would corrupt the ratings rather than fail loudly.
--
-- Tolerance is for floating-point summation only, not for real asymmetry.
select
    race_key,
    team,
    sum(pace_gap) as gap_sum
from {{ ref('int_teammate_race_gaps') }}
group by race_key, team
having abs(sum(pace_gap)) > 1e-9
