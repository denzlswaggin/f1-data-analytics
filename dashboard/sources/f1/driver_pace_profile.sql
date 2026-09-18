select
    delta_rank,
    driver_id,
    driver_name,
    nationality,
    quali_rating,
    race_rating,
    delta,
    delta_lo,
    delta_hi,
    bootstrap_valid_samples,
    bootstrap_samples,
    interval_eligible,
    quali_rank,
    race_rank,
    n_quali_comparisons,
    n_race_comparisons,
    n_seasons,
    first_season,
    last_season,
    case when not interval_eligible then 'Insufficient bootstrap coverage'
        when delta_lo > 0 then 'Racer'
        when delta_hi < 0 then 'Qualifying specialist'
        else 'Inconclusive' end as profile
from marts.driver_pace_profile
order by delta_rank
