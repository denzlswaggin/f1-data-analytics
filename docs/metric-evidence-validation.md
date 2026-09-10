# Metric evidence: publication semantics and validation

Package 4 of [the remediation plan](data-trust-remediation-plan.md), after merged
PR #71 (`4d21f54`), branch `fix/metric-evidence-semantics`.
Baseline snapshot: `20260910-racecraft-v3`.
New snapshot: `20260911-metric-evidence-v3` (11 September, Europe/Prague).

## Pit-lane duration, not mechanic service time

The pit-window and pit-strategy pages now label the source duration as the full
pit-lane visit. [Jolpica's field definition](https://github.com/jolpica/jolpica-f1/blob/main/docs/endpoints/pitstops.md)
includes entry/exit and potentially red-flag time. It cannot isolate mechanic
performance. No duration calculation or observed pairwise swing was changed.

For compatibility, `stop_duration_delta_sec` remains early minus late duration;
positive means the earlier stopper spent longer in pit lane. The legacy
`on_track_gain_sec` field is still `net_time_gain_sec + stop_duration_delta_sec`.
Its UI label is now residual swing after pit-lane-duration adjustment, not an
isolated on-track effect. Tyres, traffic and driver pace remain entangled.

The pit-strategy comparison uses the race **median**, not the previously labelled
average. Its race-control label describes message proximity, not a proven effect
on the stop. The underlying +/-2 lap-number matching rule is unchanged.

## Traffic evidence is metric-specific

Version `traffic-v3-metric-evidence` adds separate eligibility and sample-strength
fields for clean-air pace and traffic association. Clean-air eligibility needs
five clean laps; association additionally needs five matched traffic laps.
Low/medium/high labels use 5/8/12 sample thresholds; clean strength uses the clean
count, association uses the smaller clean/matched count. These are descriptive
heuristics, not calibrated probabilities. The legacy `confidence` column remains
an association-only alias. The observed P25/P75 spread is not a confidence interval.

Headline and chart filters use the relevant eligibility flag. Empty summaries
have explicit column types, tested by materialising the real empty output and
executing the Evidence source, not just by inspecting SQL text.

All 766 driver-race summaries and all 34,204 traffic lap rows were compared with
the baseline. There are zero changed clean-air or association estimates and no
changed lap-evidence rows. All 610 published clean-air estimates remain published;
457 have insufficient association evidence, now clearly separate from their
clean-air sample strength. There are 153 published association estimates.

## Tyre confirmation: observed evidence versus complete history

Version `tyre-warmup-v3-observation` separates:

- `first_observed_confirmation_laps`: confirming offset of the first observed
  consecutive stable pair, even if earlier eligible observations are missing.
- `confirmation_history_complete`: all eligible offsets from 1 through that
  confirming pair are present. Missing later offsets do not invalidate it.
- `time_to_pace_laps`: published only with that complete earlier history. This
  remains a discrete model-relative confirmation, not exact physical warm-up time.
- `observation_complete`: all six evaluation offsets are eligible and present.
  Without a stable pair this supports only a right-censored **>6** confirmation
  bound. An incomplete window with no pair is unknown, not a bound or a failure.

The legacy `crossover_eligible` flag now covers complete-history confirmations
and right-censored bounds only. It is not a ranking flag: exact-value charts
explicitly require complete history and a non-null time. Incomplete observed
pairs remain in the evidence table. No compound-crossover or temperature claim
is made, and heuristic evidence labels are not statistical confidence intervals.

| State | Stints | Exact confirmation published |
|---|---:|---|
| Observed pair, complete history | 72 | Yes |
| Observed pair, earlier missing/excluded offsets | 13 | No; observed confirmation retained separately |
| Complete window, no pair (right-censored) | 38 | No; >6 bound |
| Incomplete window, no pair | 70 | No; unknown |
| Insufficient baseline/context | 1,949 | No |

All 2,142 candidates remain, including the same 193 warmup-eligible stints.
Previously all 85 observed stable pairs had a numeric `time_to_pace_laps`; now
only 72 do. Bahrain 2025 Piastri stint 2 and Bahrain 2026 Albon stint 2 both keep
an observed confirmation at offset 6 but have null exact confirmation and status
`observed_incomplete`. Their earlier missing offsets are not silently treated as
evidence against earlier settling. First-flying losses and first-two-lap costs
match the baseline exactly; lap residual mathematics is unchanged.

## Racecraft selection and denominators

The existing 1,819 eligible resolved episodes (1,046 conversions, 773 defences)
are not all close approaches. The page now displays counts of interrupted,
unresolved and other excluded resolved episodes next to the denominator. These
categories partition all 6,136 observed episodes. Driver tables expose role
denominators, interrupted/unresolved counts and role-specific evidence labels.
Wilson endpoints are labelled 90% lower/upper limits. Those limits do not include
detection errors, repeated-episode dependence or censoring/selection uncertainty.
No racecraft calculations were changed in this package.

## Reproduction, rollout and checks

New columns require a full rebuild before incremental updates to an existing
warehouse. Deploy updated code, marts and snapshot together:

```powershell
.\.venv\Scripts\python.exe -m analytics.cli traffic-pace --all
.\.venv\Scripts\python.exe -m analytics.cli tyre-warmup --all
.\.venv\Scripts\python.exe scripts/check_metric_evidence.py data/warehouse/f1.duckdb
.\.venv\Scripts\python.exe scripts/dashboard_snapshot.py build --version YOUR_UNIQUE_VERSION
.\.venv\Scripts\python.exe scripts/check_metric_evidence.py data/dashboard/latest.duckdb
```

The read-only default-threshold checker reconciles eligibility, strength labels,
publication and status with underlying eligible lap histories and the first
observed stable pair. Warehouse and snapshot report zero violations. Mutation
tests reject incorrect labels, missing eligible laps, changed stable-pair evidence
and accidental exact publication of incomplete histories. Regressions also cover
missing offsets before versus after confirmation, final pair at offsets 5/6,
complete/incomplete no-pair windows, threshold boundaries and typed SQL sentinels.

No new races were ingested. Replay coverage remains 39 races; tyre candidates
span 60 loaded races, including races without usable replay context. Latest
represented race date remains 2026-08-23, not the snapshot-generation date.
Packages 5–6 (robust estimates, uncertainty and independent validation) remain
open: this package improves internal consistency and presentation, not proof
of causal effects, model accuracy or independently verified driver performance.
