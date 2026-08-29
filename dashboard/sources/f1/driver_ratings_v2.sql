select
    season,
    rank,
    driver_id,
    driver_name,
    nationality,
    rating,
    rating_lo,
    rating_hi,
    n_boot,
    pace_deficit,
    form_delta,
    n_comparisons
from marts.driver_ratings_v2
order by season, rank
