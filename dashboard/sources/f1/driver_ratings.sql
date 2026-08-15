select
    rank,
    driver_id,
    driver_name,
    nationality,
    rating,
    pace_deficit,
    n_comparisons,
    n_seasons,
    first_season,
    last_season
from marts.driver_ratings
order by rank
