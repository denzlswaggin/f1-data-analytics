# Robust estimates: policies, sensitivity and remaining uncertainty

Package 5 of [the remediation plan](data-trust-remediation-plan.md), after merged
PR #72 (`652fb43`), branch `fix/robust-estimates-uncertainty`.
Baseline snapshot: `20260911-metric-evidence-v3`.
New snapshot: `20260911-robust-estimates-v4`.

## Leave-one-driver-out median

Traffic controlled pace now subtracts the median of **other** drivers on the same
lap and compound. Default minimum is three other drivers: with only two, their
median is still their arithmetic mean and offers no single-outlier protection.
The minimum is configurable for sensitivity checks, not advertised as an
independently validated precision threshold. Peer selection and car differences
remain uncontrolled; a small median does not establish a driver's true pace.

New evidence fields are `peer_lap_median_sec` and `peer_count`. The existing
`peer_lap_avg_sec` keeps its arithmetic-mean meaning as a diagnostic; it is not
silently renamed to a median. Duplicate driver-lap input cannot inflate peers.
Nonfinite lap times are rejected. Traffic is `traffic-v4-robust-peers`;
downstream versions are `pace-consistency-v3-robust-peers` and
`tyre-warmup-v4-robust-peers`. Both downstream marts were fully recomputed.

Singapore 2025, Sainz, lap 61 reproduces the original audit finding:

| Quantity | Old mean baseline | New median baseline |
|---|---:|---:|
| Sainz lap | 94.963 s | 94.963 s |
| Other-driver reference | 103.7086 s | 98.146 s |
| Controlled delta | -8.7456 s | -3.183 s |
| Other drivers | 5 | 5 |

The previously influential 128.668-second Hamilton lap no longer pulls the
reference upward through arithmetic averaging. The remaining negative delta is
still a relative observation, not an isolated causal measure of Sainz's ability.

## Coverage and publication sensitivity

All 1,068 removed traffic rows had exactly two other peers. Traffic rows change
34,204 → 33,136, driver-race summaries 766 → 764. The two disappearing summaries
are Lawson 2025 R20 (one old evidence lap) and Bottas 2026 R3 (five old evidence
laps). The production clean-air/association publication thresholds stay at five
eligible laps. Results change 610 → 600 clean-air and 153 → 145 association.

Recomputed consistency eligibility changes 535 → 523; modelled laps change
12,544 → 12,016. Headline extrema now require medium/high heuristic evidence;
low-evidence values remain in charts/tables. There are 386 headline-eligible
driver-race rows. Point ranks are not claims of statistically different drivers.

All 2,142 tyre candidates remain. Eligible stints change 193 → 175; complete
confirmation histories change 72 → 58. New status counts are 58 complete observed,
17 incomplete observed, 36 right-censored, 64 incomplete, 1,967 unavailable.
The median changes residuals and mature trend fits as well as cohort coverage;
the preceding package's honest censoring/publication rules are preserved.

The following grid holds baseline lap inputs and air-state classification fixed,
recomputes medians/matching and changes only peer/publication minima. It measures
coverage sensitivity, not predictive validity or confidence calibration.

| Minimum other peers | Minimum metric laps | Lap evidence | Clean-air results | Association results |
|---:|---:|---:|---:|---:|
| 2 | 5 | 34,204 | 610 | 153 |
| 2 | 8 | 34,204 | 562 | 85 |
| 2 | 12 | 34,204 | 474 | 33 |
| 3 | 5 | 33,136 | 600 | 145 |
| 3 | 8 | 33,136 | 549 | 81 |
| 3 | 12 | 33,136 | 459 | 33 |
| 5 | 5 | 30,204 | 576 | 113 |
| 5 | 8 | 30,204 | 517 | 63 |
| 5 | 12 | 30,204 | 424 | 25 |

## Pit-timing extrapolation and conditional resampling

`pit-timing-sensitivity-v3` keeps the existing Theil–Sen models and 13-lap
evaluation window, but gates every scenario by the distances of evaluated old
tyre ages and mature new offsets outside their observed reference ranges.
Warmup offsets 1–6 reconstruct observed residuals exactly and do not count as
mature extrapolation. Every scenario includes that six-offset profile once;
its total cancels across shifts, so the model does not demonstrate a timing
benefit caused by changing warmup cost.

Default limits are four old-tyre laps and three mature-new laps beyond reference
ranges. These are operational policies aligned with the short +/-3 experiment,
not measured physical limits: a normal last old reference one lap before pit-in
already puts a +3 shift four tyre-age laps beyond that reference. The actual
shift-zero baseline must pass before any comparison is allowed. Alternatives
are gated separately; all seven rows survive, but unsupported numerical outputs
are null and their distances/reasons remain inspectable.

Only finite bootstrap draws are accepted. Publication requires at least 100
valid draws and at least 90% of the requested budget; default request is 300.
Requested, attempted and valid counts are explicit, including early exclusions.
The seed follows race/driver/stop identity, not row position, preserving full vs
incremental behavior. Tied minima split win credit equally; a deterministic
representative still prefers actual timing when tied. A flat seven-way tie does
not imply a 100% win for actual timing.

P25/P75 is the middle 50% of **conditional independent-row resampling**, not a
calibrated confidence interval. Warmup observations, field references, clean-air
selection and model family are fixed. Serial dependence and selection uncertainty
are not modelled. High evidence still means a heuristic, and is forbidden for
range-edge minima or fewer than 300 valid draws. Edges are evaluated against the
supported range, including ranges trimmed by rejected scenarios.

A gain under the practical 0.30-second threshold is labelled “No meaningful
directional signal,” not “Actual lap within uncertainty”: a small gain can have
an entirely negative resampling interval without clearing the practical threshold.

## Historical pit results and policy sensitivity

Stop candidates remain 2,142 and scenarios 14,994. Eligibility changes 41 → 36;
published scenarios change 287 → 239. Five prior comparisons fail their actual
baseline, all on the old-reference limit:

| Stop | Actual old extrapolation |
|---|---:|
| Norris 2025 R9, stop 1 | 5 laps |
| Stroll 2025 R10, stop 2 | 17 laps |
| Tsunoda 2025 R22, stop 2 | 13 laps |
| Colapinto 2025 R24, stop 2 | 11 laps |
| Leclerc 2026 R8, stop 3 | 12 laps |

The 36 retained stops keep their point-estimate selected shifts. Thirty are
range-edge minima; none receives high evidence (previously 12 stops did).
Every published model has 300 valid draws, with at most 340 attempts.
Colapinto 2025 R9 stop 2 keeps its 15.6625-second modelled difference at -3, but
now says earlier edge favoured / optimum unlocated, medium evidence, five
supported scenarios. Its actual old extrapolation is 3 laps; the -3 scenario's
old extrapolation is 0. The gain is not independently validated.

The grid below varies only extrapolation acceptance using stored fitted-model
distances. Counts include actual plus at least one alternative. It neither
refits nor ranks unsupported costs and does not establish newly publishable
models under a looser bootstrap/quality policy.

| Max old extrapolation | Max new extrapolation | Fitted stops with comparison | Bounded scenarios |
|---:|---:|---:|---:|
| 2 | 0 | 31 | 129 |
| 2 | 3 | 32 | 156 |
| 2 | 6 | 32 | 156 |
| 4 | 0 | 34 | 206 |
| 4 | 3 | 36 | 239 |
| 4 | 6 | 36 | 239 |
| 6 | 0 | 35 | 221 |
| 6 | 3 | 37 | 256 |
| 6 | 6 | 37 | 256 |

## Reproduction and rollout

Full rebuilds are required before incremental writes because traffic and pit
schemas add fields. Deploy the rebuilt downstream marts and snapshot together:

```powershell
.\.venv\Scripts\python.exe -m analytics.cli traffic-pace --all
.\.venv\Scripts\python.exe -m analytics.cli pace-consistency --all
.\.venv\Scripts\python.exe -m analytics.cli tyre-warmup --all
.\.venv\Scripts\python.exe -m analytics.cli pit-timing --all
.\.venv\Scripts\python.exe scripts/check_robust_estimates.py data/warehouse/f1.duckdb
.\.venv\Scripts\python.exe scripts/dashboard_snapshot.py build --version YOUR_UNIQUE_VERSION
.\.venv\Scripts\python.exe scripts/check_robust_estimates.py data/dashboard/latest.duckdb
.\.venv\Scripts\python.exe scripts/report_robustness_sensitivity.py --baseline data/dashboard/f1-dashboard-20260911-metric-evidence-v3.duckdb --current data/dashboard/latest.duckdb
```

The baseline file must contain pre-v4 two-peer cohorts; a post-filtered snapshot
cannot recover discarded cohorts for the looser sensitivity setting. Checks
independently reconstruct peer medians and reconcile scenario counts, unsupported
publication, extrapolation and resampling rules. Mutation tests prove they reject
inconsistency. Synthetic tests cover contamination, small cohorts, ties, zero/short
bootstrap output, finite draws, trimmed ranges, scope invariance and SQL sentinels.
A fixed noisy fixture is also checked at 100/300/600 draws: selected shift -3,
P25 -5.718 s and P75 -5.340 s remain stable. This is a regression case, not evidence
of general bootstrap convergence or predictive calibration.

No new races were ingested. Replay remains 39 races and 4,129,511 rows, latest
represented date 2026-08-23. Pit/tyre candidate tables span 60 loaded races,
including excluded races without sufficient replay evidence. Existing pit-context,
race-control, racecraft and metric-semantics checks also pass on the new snapshot.
Independent annotation, held-out detection accuracy, uncertainty calibration and
causal interpretation remain open in package 6; this package must not be presented
as completing those validations.
