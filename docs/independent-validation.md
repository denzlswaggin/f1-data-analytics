# Independent validation: first reference panel

Package 6, initial delivery. This is **not** a certification of the dashboard,
an exhaustive event audit, or completion of independent production-model validation.
Production calculations and the published snapshot are unchanged.

## Frozen inputs and independence

- Snapshot: `20260911-robust-estimates-v4`.
- Snapshot SHA-256: `af90ff3bbfab995d8aaf42d8dd18a6c055a3b0c06bf2b4a8c6f276191de2fded`.
- Reference annotations: `validation/reference-events-v1.json`, frozen in commit
  `f1a0795` before querying the selected detector outputs.
- Reference SHA-256: `c97ee86d5fd4d172bfc25a3ad4cd7c441ec6798d49f9f306daf58119c193b245`.
  Reference hashing normalizes line endings to LF for Windows/Linux parity.
- Reports were read and annotations transcribed by the coding assistant on
  2026-09-11. They have **not** been reviewed by a second human or adjudicated.
- The two races were selected deliberately for wet/dry conditions and team-order
  ambiguity, not sampled randomly. These previously inspected races are not
  pristine race-level holdouts. Independence here means external event labels
  and evaluator code that does not import the production detection functions.
- F1 reporting is a separate reference artifact, but may share underlying timing
  information with the app's providers. It is not a fully independent sensor.

Primary sources: [F1 Belgian GP report, 27 July 2025](https://www.formula1.com/en/latest/article/piastri-wins-wet-dry-belgian-gp-after-late-pressure-from-title-rival-and.7QmPcUP90MvR5iX0w3j91)
and [F1 Italian GP report, 7 September 2025](https://www.formula1.com/en/latest/article/verstappen-charges-to-italian-gp-win-over-norris-and-piastri.6J7R9E9tzOI9Asy6HBmoVf.6J7R9E9tzOI9Asy6HBmoVf).
The compact annotations paraphrase only specific observable events, not articles.

## Event checks and failures

The panel contains eight positive passes, six positive pit-entry laps and two
negative windows: Verstappen did not pass Leclerc during Spa's green running;
the late Norris/Piastri Monza team-order exchange must not be an eligible
competitive racecraft conversion. Unmentioned events remain **unknown**, never
automatically negative.

| Measure | Result |
|---|---:|
| Annotated cases with driver-lap source coverage | 16 / 16 |
| Positive events matched at the exact lap | 13 / 14 |
| Positive events matched within predeclared +/-1 lap | 14 / 14 |
| Explicit negative windows without a positive detection | 2 / 2 |
| False positives within those two annotated negative windows | 0 |
| Missed positive events with +/-1 lap tolerance | 0 |
| Population precision / false-positive rate | Not estimable |

**Known mismatch:** Piastri's pass on Norris at Spa is assigned to replay lap 4,
whereas the race report explicitly locates the first green racing lap and pass
on counted race lap 5. Matching the driver's nearest replay tick (within two
seconds) therefore requires the predeclared lap tolerance. This is not an exact
timestamp validation, and the mismatch is not suppressed or relabelled.

Coverage only means at least one row for every annotated driver-lap. It does
not establish continuous timing coverage. A missing driver-lap is `uncovered`,
not a successful negative or a detector miss. No event-level timing error is
reported because the articles do not supply second-resolution ground truth.
Sparse, selected negatives cannot establish global specificity or precision;
we intentionally do not attach a population confidence interval to this panel.
Results per case are committed in `validation/reference-results-v1.json`.

## Temporal pace diagnostic

An independently implemented OLS benchmark fits the **first eight** qualifying
laps in a stint and predicts every later qualifying lap, requiring at least
three. The comparator is a constant median of the same eight training targets.
Qualifying inputs are finite clean-air traffic evidence with 80-100% replay
coverage. Age variation must span at least four laps and four distinct ages.
No fitted production residual, slope or intercept is read by this evaluator.

| Measure | Result |
|---|---:|
| Input traffic laps | 33,136 |
| Qualifying laps | 12,847 |
| Candidate stints | 1,792 |
| Evaluated stints | 528 |
| Excluded: fewer than 8 training + 3 held-out laps | 1,264 |
| Training laps | 4,224 |
| Later held-out laps | 5,239 |
| Linear benchmark mean absolute error | 1.113844 s |
| Training-median baseline mean absolute error | 0.625723 s |

The linear benchmark is worse on this selected sample. This warns against
assuming that fitting a tyre-age trend implies useful extrapolation. It does
**not** measure the accuracy of the production robust estimator or prove it
inferior: its fitting/selection policy differs. Errors are lap-weighted and
longer stints contribute more. The CLI prints every train/holdout lap split and
per-stint errors for inspection, not just the aggregate.

This is retrospective temporal separation within already inspected races.
Contemporaneous peer references and eligibility still use observed data, so it
is not a live forecast. The controlled pace target is itself derived, not an
independent measurement of car-free driver skill. There is no calibrated
predictive interval and no test of the unobserved alternative pit-stop outcome.

## Reproduce (read-only)

```powershell
.\.venv\Scripts\python.exe scripts/report_reference_validation.py
.\.venv\Scripts\python.exe scripts/report_model_holdout.py
.\.venv\Scripts\python.exe -m pytest tests/test_reference_validation.py tests/test_model_holdout.py --no-cov
```

Both CLIs accept `--snapshot PATH`. The reference CLI also accepts
`--reference PATH`. Analytical mismatches are report results, not CLI errors;
malformed inputs and missing required tables fail. CI tests the evaluator's
behaviour with positive, negative, missing and corrupted synthetic inputs; it
does not label the historical database trustworthy merely because tests pass.

## Remaining validation gates

Follow-up delivery: [event-window validation](event-window-validation.md) adds
complete listed-stop windows and positive SC/VSC/red-flag probes. It does not
close the broader gates below.

1. Independently review/adjudicate these source annotations, especially lap
   boundaries. Preserve versions; do not overwrite a benchmark to fit outputs.
2. Exhaustively annotate preselected windows on additional races, including
   pit cycles, lapping, SC/VSC/red flags, retirements and reversals. That supplies
   the missing denominator for event precision and meaningful error analysis.
3. Freeze a production-model evaluation protocol and untouched race set before
   tuning. Evaluate observable held-out targets against baselines; cluster
   uncertainty by race rather than treating laps as independent trials.
4. Separately assess race-control effects, censored tyre settling and pit-window
   outputs. A counterfactual strategy's true alternative cannot be observed in
   the same race; an explicit identification argument is needed before causal
   or optimal-strategy claims. Do not turn resampling spread into calibration.

Until these gates are met, product claims remain exploratory and conditional.
