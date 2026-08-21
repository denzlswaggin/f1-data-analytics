select
    delta_rank,
    driver_id,
    driver_name,
    nationality,
    quali_rating,
    race_rating,
    delta,
    quali_rank,
    race_rank,
    n_quali_comparisons,
    n_race_comparisons,
    n_seasons,
    first_season,
    last_season,
    case when delta >= 0 then 'Racer' else 'Qualifying specialist' end as profile
from marts.driver_pace_profile
order by delta_rank
