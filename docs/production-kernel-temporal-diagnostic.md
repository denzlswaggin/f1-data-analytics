# Temporal diagnostic of the production fitting kernel

This audit does not validate the complete pit-timing model or an unobserved
alternative strategy. It tests the actual `analytics.pit_timing._fit` Theil-Sen
kernel on the same chronological split as the existing OLS diagnostic.

The protocol is unchanged: first eight eligible clean-air stint laps for fitting,
at least three later eligible laps for evaluation, at least four distinct training
tyre ages spanning four laps, and 80–100% replay coverage. Both estimators use
identical rows. The constant comparator is the median training target.
No holdout target enters either fit. Targets remain contemporaneous relative
pace estimates, not independent measurements of driver skill.

Snapshot `20260914-source-classification`, SHA-256
`bd21e91a4785072c6efb0a5a41f8712180fcc3b6bba98ab15c846e4a5e62d8c9`:

| Estimator | Evaluated stints | Later laps | Mean absolute error |
| --- | ---: | ---: | ---: |
| OLS diagnostic | 825 | 8,578 | 1.198294 s |
| Production Theil-Sen fitting kernel | 825 | 8,578 | 1.145948 s |
| Training-median constant | 825 | 8,578 | 0.653380 s |

The robust kernel improves on OLS in this selected diagnostic but both have
larger errors than the constant comparator. Robustness to isolated training
outliers does not establish reliable extrapolation. These errors are lap-weighted;
longer stints contribute more. There is no calibrated interval or significance
claim, and this previously inspected sample is not an untouched evaluation set.

The production strategy model uses additional eligibility, reference-window,
warmup and scenario rules. This diagnostic deliberately does not claim to test
those rules or certify hypothetical stop timing. Whole-model evaluation on
predeclared untouched races and an explicit argument for causal interpretation
remain open requirements.

The [OLS report](../validation/temporal-ols-20260914.json) and
[robust-kernel report](../validation/temporal-production_theil_sen-20260914.json)
include per-stint training/evaluation lap lists, fitted coefficients, exclusions,
errors, the snapshot hash and normalized implementation hashes.

```powershell
python scripts/report_model_holdout.py --estimator ols
python scripts/report_model_holdout.py --estimator production_theil_sen
```

Regression tests perturb later targets without changing fitted coefficients,
compare identical splits and demonstrate the robust kernel's resistance to an
isolated training outlier. They establish evaluator behavior, not physical accuracy.
