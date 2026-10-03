# Joint qualifying and race-pace ratings (V3 experiment)

V3 is a research model, not a replacement for the published V1 three-season rating or
V2 driver-season rating. It asks whether two related signals—qualifying pace and
carefully controlled race pace—predict future teammate gaps better when estimated
together. The pipeline writes V3 to separate marts and records enough evidence to
make a promotion decision; it never switches the dashboard's canonical rating.

## Inputs and controls

Qualifying uses the last knockout session both teammates reached, with the existing
Q1/Q2/Q3 reliability weights. Race observations come from
`int_teammate_race_gaps`: teammates must be on the same lap and compound, at similar
tyre age, under green flags; stint boundary laps, implausible gaps, and samples with
too few comparable laps are removed. The remaining race observations are weighted
by their comparable-lap count, clipped to stop a single weekend dominating.

These controls reduce known fuel, tyre, traffic, and strategy confounding. They do
not make race pace causal: car damage, imperfect traffic detection, setup choice,
team orders, and unobserved race context can remain.

## Model

For each driver `d`, season `s`, and discipline `m`, V3 estimates a pace deficit
`z[d,s,m]`. Every teammate observation contributes:

```text
pace_gap ≈ z[driver, season, discipline] - z[teammate, season, discipline]
```

The least-squares objective adds three transparent quadratic penalties:

- a zero-centred ridge prior for sparse driver-seasons;
- temporal links between the same driver's adjacent observed seasons, weakened
  across career gaps;
- a cross-discipline link between that driver's qualifying and race estimate in
  the same season.

The last link is partial pooling: Saturday and Sunday estimates can disagree when
the data support it, unlike treating all observations as one interchangeable pace
measure. The displayed joint rating is the negative mean deficit across available
disciplines. Separate `quali_rating`, `race_rating`, and `discipline_delta` columns
keep that aggregation inspectable.

## Validation protocol

Run the experiment with:

```bash
python -m analytics.cli ratings-v3 --final-holdout-season 2026 --n-boot 100 --seed 0
```

The default final holdout is season 2026. Parameter selection sees only seasons
before 2026. If 2026 has no usable comparisons yet, the validation artifact records
`status = not_available`; it does not silently substitute an earlier season or
claim final-test performance.

Before the final test, nested expanding-window validation works as follows:

1. each outer season is predicted from earlier seasons only;
2. inside that training prefix, another expanding-window backtest selects ridge,
   temporal, cross-discipline, and race weights by MAE;
3. pre-fold out-of-sample residuals calibrate a symmetric 90% prediction interval;
4. the outer fold reports MAE, RMSE, direction accuracy, interval coverage, and
   mean interval width.

After nested validation, parameters are selected once using all pre-2026 folds and
frozen. Only then is the untouched 2026 season scored. Race-weekend cluster
bootstrap intervals on the fitted driver-season ratings use a fixed seed and keep
both directed teammate rows—and the qualifying/race observations—from a sampled
weekend together.

## Evidence artifacts and promotion rule

The pipeline creates:

| Table | Purpose |
| --- | --- |
| `marts.driver_ratings_v3` | Experimental joint and discipline-specific ratings with bootstrap intervals |
| `marts.driver_ratings_v3_validation` | Nested-validation and final-holdout accuracy/calibration metrics |
| `marts.driver_ratings_v3_ablation` | Static V1, independent V2, no-cross-pooling, no-temporal-pooling, and tuned V3 comparisons |

`recommended_for_promotion` is true only when an actual final holdout exists and
V3 beats both independent baselines on combined MAE without losing direction
accuracy. This is a deliberately strict, simple gate—not proof that the model will
generalise indefinitely. A positive result should still be checked for practical
effect size, modality-specific regressions, interval calibration, and stability
across candidate grids before any downstream migration.

## Reproducibility and limitations

The solver is deterministic (`numpy.linalg.lstsq`), folds are chronological, and
bootstrap randomness is controlled by `--seed`. The candidate grid is intentionally
small to limit multiple-comparison optimism. It should be expanded only with a
pre-declared search space and the final holdout kept sealed.

Sparse race coverage is the main limitation. Partial pooling can reduce variance,
but it can also transfer race-specific bias into qualifying (or the reverse). The
no-cross and no-temporal ablations expose whether either assumption helped on
unseen data. Ratings remain teammate-relative and are not causal estimates of
driver talent.
