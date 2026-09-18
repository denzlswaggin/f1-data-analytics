# Dashboard audit remediation

Baseline: `20260918-current`, main `1643162`, through Madrid 2026 R14.
Branch: `fix/audit-data-and-core-pages`. Implement audit sections 1 and 2 only.
Approach: correct demonstrated errors, validate existing models, expose uncertainty;
do not introduce new model families or claim independent accuracy from source agreement.

## Commit-sized work

- [x] Record scope and implementation sequence.
- [ ] Restore historical pit stops, weather and radio with source provenance; preserve newer partitions and sessions.
- [ ] Separate warehouse/serving checks; reject disappearing coverage before installing a snapshot.
- [ ] Show input versus usable evidence in DataTrust, with explicit units and availability.
- [ ] Use recorded classifications and actual pit visits in tyre/pit strategy; retain stops with missing position windows.
- [ ] Separate speed and weather scope; match weather to lap windows; require five races for aggregate weather comparisons.
- [ ] Materialise track classifications, version thresholds, gate fit at five races, add deterministic 90% race-bootstrap intervals and fix percentage formatting.
- [ ] Deduplicate Saturday/Sunday movers; jointly resample weekends within seasons (1,000 draws, seed 0), publish difference intervals at 90% valid-draw coverage.
- [ ] Rerun pit-timing temporal diagnostics; foreground eligibility, boundary minima and component-validation limits.
- [ ] Rerun racecraft references; show Wilson intervals/denominators without overstating event accuracy.
- [ ] Publish validated snapshot, refresh both applications, verify pages and record results.

## Acceptance

Keep Madrid and all existing 2022–2023 data. Restore available 2024–2026 history;
distinguish missing, successfully empty and unavailable source partitions. Candidate
publication must fail without replacing the previous latest snapshot when validation
fails. Test partition preservation, missing positions, real stop counts, sparse samples,
paired bootstrap and changed contracts. Run relevant dbt/Python checks, all serving SQL,
strict Evidence build, replay build and browser checks for seven affected pages.
Commit completed logical units; do not automatically merge or deploy.

## Deferred audit sections 3 and 4

Driver DNA sample expansion; telemetry matching; Race Pace baseline unification;
Tyre Warmup/Traffic/Pace Consistency presentation; Pit Window headline correction;
Driver Ratings; Cockpit/Latest consolidation; homepage; replay provenance presentation;
Race Control polish; Driver Comparison; general Methodology restructuring.
Shared coverage and required downstream data refreshes may affect these pages.

## Baseline findings

Pit, weather and radio partitions cover only Bahrain 2024 and Italy/Spain 2026.
40/44 serving data SQL checks pass; one failure incorrectly requires warehouse-only
qualifying data. Pit timing: 66/2,197 eligible, 55 boundary minima. Track fit median
sample: 1–2 races. Saturday/Sunday default: 14 drivers, overlapping top/bottom lists.
Race Control v3: 62 races, 87 events, no structural audit violations.
