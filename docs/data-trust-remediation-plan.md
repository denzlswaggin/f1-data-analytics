# Data-trust remediation

Baseline: audit of merged PRs #62–#68 at `96fc7a2`, recorded in
[the audit](data-trust-audit-2026-09-10.md). These are remediation packages,
not replacements for the original seven analytical features.

Each package gets its own branch and PR, incremental commits, regression tests,
and a rebuilt snapshot whenever its calculations change. Merge a prerequisite
package before starting the next dependent package. Passing CI is not independent
validation of the analytical claims.

## Stage 1: correctness and honest presentation

1. **Shared pit context** — `fix/shared-pit-event-context`.
   Preserve FastF1 pit-in/out timestamps; union observed pit laps with stint
   boundaries, including visits without a tyre change. Apply the context to
   traffic, consistency, tyre settling, pit timing/windows and racecraft. Publish
   exclusions and provenance. Reproduce Monaco 2025 / Russell before and after.
2. **Race-control** — `fix/race-control-comparability`; correct the start/finish-line lap-deficit artifact; require
   an adequate comparable cohort for adjusted-gap centering; align recovery
   eligibility with the description of complete green laps.
   Implementation and before/after evidence: [race-control v2 validation](race-control-v2-validation.md).
3. **Racecraft** — `fix/racecraft-continuous-battles`; fix reversal ownership and require continuous release and
   pressure intervals. Add synthetic boundary cases and real-data regressions.
   Implementation and before/after evidence: [racecraft v3 validation](racecraft-v3-validation.md).
4. **Metric semantics and evidence** — `fix/metric-evidence-semantics`; label pit-lane duration correctly; separate
   confidence for individual traffic metrics; represent incomplete/censored tyre
   settling honestly; show racecraft denominators and interrupted outcomes.
   Implementation and before/after evidence: [metric evidence validation](metric-evidence-validation.md).

## Stage 2: methodological robustness

5. **Robust estimates and uncertainty** — `fix/robust-estimates-uncertainty`; test robust peer baselines, sample
   thresholds and bootstrap/sensitivity behavior. Do not read model-fit confidence
   as a calibrated probability or causal claim.
   Implementation, policy grids and before/after evidence: [robust estimates validation](robust-estimates-validation.md).
6. **Independent validation** — assemble annotated reference races and held-out
   checks for detected events and model outputs; report coverage, false positives,
   uncertainty and failures before strengthening product claims.

## Package 1 behavior and limitations

- `marts.pit_lap_context` stores one row per loaded race lap, with entry/exit flags,
  evidence source, status and exclusion reason. It is computed from unfiltered
  staging, not only from representative laps.
- FastF1 timestamps identify their own lap. A recorded Jolpica pit lap and its
  following lap are conservatively excluded. Stint boundaries remain a fallback;
  they are not relabeled as directly observed pit visits.
- Missing records or nullable timestamp columns do not establish complete source
  coverage. `no_pit_observed` is not `confirmed_no_pit`. Boundary provenance is
  `unavailable` on non-boundary rows; it does not describe race-wide availability.
- Historical raw partitions remain compatible and are not destructively replaced
  to add the new fields. Historical FastF1 timestamps are not backfilled by this
  package; available Jolpica records and stint evidence are used instead.
- Whole-warehouse and round refreshes use the same context. Standalone builders
  recompute it from staging, so they do not silently reuse an old context mart.
- Intended pit entry/exit laps stay in pit-window/timing evaluation windows;
  additional pit activity invalidates those comparisons. They are excluded from
  representative pace references.
- Snapshot consumers fail clearly if the new provenance table is missing.
  To upgrade an existing warehouse, rebuild `stg_laps`, run `pit-context --all`,
  then `traffic-pace`, `pace-consistency`, `tyre-warmup`, `pit-windows`, `pit-timing`
  and `racecraft`, each with `--all`, before exporting the dashboard snapshot.
  These are subcommands of `python -m analytics.cli`.
- This package does **not** fix the remaining race-control/racecraft logic,
  censoring, confidence or statistical-model findings. The product remains
  exploratory analytics, not validated driver/strategy ground truth.
