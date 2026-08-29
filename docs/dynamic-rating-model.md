# Dynamic driver rating (V2)

## Question

The original model estimates one driver value across a whole career. That is a
useful, stable benchmark, but it cannot answer whether a driver improved,
declined, or adapted to a new regulation era. V2 estimates a separate latent
pace deficit for every observed driver-season.

## Model

For teammate comparison `i` versus `j` in season `s`, the observation remains:

```text
deficit(i,s) - deficit(j,s) ≈ log pace gap(i,j,s)
```

The objective adds two regularisers:

- a zero-centred ridge prior to shrink noisy, low-sample seasons;
- a temporal penalty between consecutive observed seasons of one driver,
  weakened when the driver has a multi-year career gap.

Q3 comparisons receive weight 1.0, Q2 0.9, and Q1 0.8. This is a transparent
reliability assumption, not a learned causal effect. The iterative solver uses
the largest connected teammate component and publishes convergence diagnostics.

## Uncertainty

Intervals use a 90% cluster bootstrap. The sampling unit is an entire race
weekend within a season, so both mirrored directions and all constructor pairs
from that weekend stay together. This avoids pretending the directed rows are
independent and preserves the season mix.

## Evaluation

An expanding-window backtest fits on seasons before year `Y` and predicts the
teammate gaps in `Y`. With the current 2006–2025 warehouse and the documented
defaults (`prior_weight=8`, `temporal_weight=48`):

| Model | MAE | Gap-direction accuracy |
| --- | ---: | ---: |
| Career-wide static benchmark | 0.645 | 0.606 |
| Dynamic latest-season rating | 0.643 | 0.609 |

The improvement is marginal. V2 should therefore be used to explore form and
career trajectories, not presented as a decisive predictive breakthrough. The
CLI prints both results from the same temporal splits:

```bash
python -m analytics.cli validate --n-boot 0
python -m analytics.cli ratings-v2 --n-boot 100
```

## Limitations and next experiment

Teammate comparison removes much shared car performance, but not upgrades,
setup choices, reliability, injury, traffic, or changing teammate strength.
The Q-session weights and temporal penalty should eventually be chosen in nested
time-series validation rather than on the headline holdout. A credible V3 would
jointly model qualifying and controlled race pace with partial pooling, then
test calibration on a final untouched block of seasons.
