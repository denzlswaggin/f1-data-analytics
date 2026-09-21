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
    case when interval_eligible is not true
            or not coalesce(isfinite(delta_lo) and isfinite(delta_hi), false)
            or delta_lo > delta_hi or bootstrap_samples <= 0
            or bootstrap_valid_samples < 0.9 * bootstrap_samples
            or bootstrap_valid_samples is null or bootstrap_samples is null
            then 'Interval unavailable'
        when delta_lo > 0 then 'Positive difference'
        when delta_hi < 0 then 'Negative difference'
        else 'Inconclusive' end as profile
from marts.driver_pace_profile
order by delta_rank
