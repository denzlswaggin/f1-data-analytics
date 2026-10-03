# Dashboard audit remediation

This is the September 2026 audit record. Its requirement to preserve 2022–2023
data and its five-season counts have been superseded by the [2024–2026 data
context](data-context.md). The recorded audit results below are retained as
historical evidence.

Baseline: `20260918-current`, main `1643162`, through Madrid 2026 R14.
Branch: `fix/audit-data-and-core-pages`. Sections 1 through 4 complete on the same branch; verification is recorded below.
Approach: correct demonstrated errors, validate existing models, expose uncertainty;
do not introduce new model families or claim independent accuracy from source agreement.

## Commit-sized work

- [x] Record scope and implementation sequence.
- [x] Restore historical pit stops, weather and radio with source provenance; preserve newer partitions and sessions.
- [x] Separate warehouse/serving checks; reject disappearing coverage before installing a snapshot.
- [x] Show input versus usable evidence in DataTrust, with explicit units and availability.
- [x] Use recorded classifications and actual pit visits in tyre/pit strategy; retain stops with missing position windows.
- [x] Separate speed and weather scope; match weather to lap windows; require five races for aggregate weather comparisons.
- [x] Materialise track classifications, version thresholds, gate fit at five races, add deterministic 90% race-bootstrap intervals and fix percentage formatting.
- [x] Deduplicate Saturday/Sunday movers; jointly resample weekends within seasons (1,000 draws, seed 0), publish difference intervals at 90% valid-draw coverage.
- [x] Rerun pit-timing temporal diagnostics; foreground eligibility, boundary minima and component-validation limits.
- [x] Rerun racecraft references; show Wilson intervals/denominators without overstating event accuracy.
- [x] Publish validated snapshot, refresh both applications, verify pages and record results.

## Acceptance

Keep Madrid and all existing 2022–2023 data. Restore available 2024–2026 history;
distinguish missing, successfully empty and unavailable source partitions. Candidate
publication must fail without replacing the previous latest snapshot when validation
fails. Test partition preservation, missing positions, real stop counts, sparse samples,
paired bootstrap and changed contracts. Run relevant dbt/Python checks, all serving SQL,
strict Evidence build, replay build and browser checks for seven affected pages.
Commit completed logical units; do not automatically merge or deploy.

## Active audit sections 3 and 4

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

## Implemented result (18 September 2026)

Snapshot: `20260918-audit-core-pages`, latest event 13 September 2026 (Madrid R14).
SHA256: `570ba59a8846ab413850ae664787c50f29ff1bd5d77203206a8688c20252b6e7`.
No coverage exceptions. Lap history still includes 22/22/24/24/14 races in
2022/2023/2024/2025/2026 respectively.

- Pit visits: 2,201 across all 62 completed 2024-2026 races. The three existing
  published pit partitions were also checked against Jolpica (43/30/25 visits).
- Weather: all 62 races, aligned within each lap on the session clock.
- Radio: 57 available race partitions; five ingestion attempts returned no observations,
  explicitly recorded as `no_observations`, never as proof of zero radio messages.
- Official classification: zero stint/result finish-position mismatches.
- Track fit: 5 of 72 driver/archetype groups reach five races; other groups have
  no published aggregate chart or interval. Snapshot-level thresholds are saved.
- Saturday/Sunday: 15 drivers, 12 valid intervals, seven of those contain zero;
  three drivers do not meet 90% valid-bootstrap coverage. Movers are unique.
- Pit timing (2024 onward): 85/2,197 transitions eligible, 73 edge minima. Temporal
  diagnostic on 871 stints: production-kernel MAE 1.136 s, constant-baseline MAE
  0.652 s. This does **not** validate full counterfactual strategy accuracy.
- Racecraft: 2,939 eligible resolved episodes out of 12,488 observed episodes.
  The 16 frozen reference cases and four additional 2024 pass cases match within
  protocol tolerances. The 36-case control suite passes, including one expected
  unavailable case. Purposive references do not establish population accuracy;
  earlier independent-feed disagreement reports remain unchanged.

Reports are in [validation/dashboard-audit-20260918](../validation/dashboard-audit-20260918/).
Each diagnostic records the evaluated snapshot hash. Historical reports are retained.

## Reproduction and verification

Recovery was performed in `data/warehouse/audit-remediation/f1.duckdb`, cloned
from the Madrid snapshot, using `scripts/restore_dashboard_history.py --fetch`.
The operational warehouse remains unchanged. The candidate needed the operational
`staging.stg_drivers` lookup for the pace-profile pipeline. Targeted dbt models:
`stg_pitstops stg_weather stg_team_radio mart_pit_strategy mart_stint_degradation
mart_stint_strategy mart_weather_degradation`.

Rebuilt track insights, paired pace profile (2024-2026), traffic, consistency,
warmup, pit-window, pit-timing, racecraft and dependent Race Control marts.
The final export uses `scripts/dashboard_snapshot.py build` and the normal
snapshot validation gate. Source availability and session/race preservation are
validated before the previous latest database or manifest can be replaced.

Verified: 795 Python tests, 31 targeted dbt data tests, 49 serving SQL
sources, 45 serving-data checks, Python lint and type checks, 26 replay tests,
four dependent-filter tests, pit-context/metric/robustness checks and Madrid
golden checks. Traffic reproduction has zero added or removed rows.

The Browser plugin reported no available browser in this session. Automated
repository browser smoke tests provide the browser-runtime checks; no interactive
Browser-plugin visual review is claimed.

Both production builds passed: strict Evidence and the replay app with regenerated
web data (61 replay races, default Madrid 2026 R14). Browser smoke passed all 21
routes at 1440px and 390px widths, including all seven changed pages. The test
used the generated Evidence project's Vite preview server; the generic Python
HTTP server reset module connections on this Windows environment. The final
bundle passes the 275 MB total / 60 MB single-file budget.

Sections 1 and 2 are complete. Sections 3 and 4 are completed below.


## Sections 3 and 4 execution checklist

- [x] Correct directional Pit Window headlines and empty chart states. Four page tests pass, including executed SQL for positive-only, negative-only, zero, null, empty and mixed samples. Strict build and responsive render checks pass.
- [x] Unify Race Pace with the shared robust peer baseline, retaining historical scope. Uses published Traffic lap deltas directly; raw timing remains selectable for older races without replay-backed evidence. Executed query tests verify identical deltas, phase minima and historical availability; strict build and responsive render checks pass.
- [x] Expand Driver DNA matched-lap evidence without relaxing eligibility. Added 633 cached matched laps; 26 unavailable requests are recorded, never fabricated. Candidate has 840 eligible directed comparisons (420 unique teammate/race pairs), up from 144 (72 pairs). Rebuilt profiles, track fits and robustness diagnostics; preserved every original telemetry point with zero duplicate keys. Published in snapshot `20260918-audit-pages34`.
- [x] Match telemetry comparisons jointly and expose lap context. Candidate pool includes fastest available and eligible DNA laps; race-lap/tyre-age gaps are capped at three with green dry non-pit laps only. Five executed SQL cases verify matching and integrated delta; strict build and matched/empty browser interactions pass.
- [x] Clarify Warmup, Traffic and Consistency usable samples and limitations. Separate warmup outcomes and offset sample counts; show metric-specific Traffic eligibility and Consistency exclusion reasons. Guard empty headlines/charts and contain wide tables. Page/query tests pass; strict build passes.
- [x] Rework Ratings and Comparison around supported scopes and uncertainty. Rating interval plots replace bare bars, show per-driver counts and missing intervals; season selector retains all published drivers. Comparison exposes shared-year scope and distinguishes indirect model differences from direct contests. Four relevant tests and component compilation pass; strict build passes.
- [x] Consolidate Cockpit/Latest and improve homepage navigation and coverage. Latest is now a scoped entry to the canonical Cockpit; homepage shows analysis availability instead of an unqualified career leaderboard. Race links retain season/round through the replay redirect and replay initial selection. Eight dashboard tests, 27 replay tests and Svelte checks pass; strict build passes.
- [x] Present replay provenance and polish Race Control evidence. Arrow bundles retain separate order/gap source classes, preserved during interpolation and shown in the timing tower; animation and missing feeds are explained. Race Control exposes component units, eligibility and reference counts. Five Python and 28 replay tests pass; regenerated replay bundle, production build and provenance browser checks pass.
- [x] Restructure Methodology around metric definitions and validation limits. Added evidence types, metric/unit/eligibility table, uncertainty and missing-state guide; retained historical independent-review status and updated the explicitly dated fitting diagnostic. Strict build and mobile visual review pass.
- [x] Refresh affected data; verify builds, tests, coverage and responsive pages. All 21 dashboard routes pass at 1440px and 390px, without console errors or page overflow; final evidence is recorded below.

Commit each verified logical unit on `fix/audit-data-and-core-pages`.
Preserve Madrid 2026 and existing historical partitions; do not merge or deploy.


### Sections 3/4 data reproduction

`python scripts/expand_dna_telemetry.py --database data/warehouse/audit-remediation/f1.duckdb --report data/dna-expansion-report.json`
reads only local FastF1 cache and adds previously missing jointly selected laps.
It never replaces original telemetry. Then run `build_driver_dna(2024, 2026)`,
`build_driver_track_insights()` and `build_driver_dna_validation(2024, 2026)`
with settings pointing to that candidate (1,000 bootstrap draws, 200 permutations,
seed 0). The matching limits remain three race laps / three tyre-age laps;
physical-channel cleaning and 95% common-coverage checks remain unchanged.


### Sections 3/4 implemented result (18 September 2026)

Snapshot: `20260918-audit-pages34`, latest event Madrid 2026 R14 (13 September).
SHA256: `6b320289160b54308d126d40ddc0b9f4878e60a7fa64162c8c61a2d082e57f30`.
The database, snapshot manifest and regenerated replay export match. No coverage
exceptions; the 106 timing races and all restored historical partitions remain.
Telemetry now contains 754,175 points across 3,851 laps and 60 races. DNA has
840 eligible directed rows (420 unique teammate/race pairs across 59 races).
The 26 unavailable cache requests are recorded in the expansion report; expansion
does not imply complete telemetry coverage or independent model validation.

Additional integration fixes preserve URL-selected seasons/races/drivers after
asynchronous query loading, format round numbers consistently, prevent transient
empty telemetry charts, and distinguish missing Cockpit source coverage from zero.
Latest Race links to the canonical Cockpit with the correct event context.

Verification: 807 Python tests, Ruff, Mypy (135 files), 49 serving SQL sources,
45 serving-data checks, six dependent-dropdown tests and 28 replay tests passed.
Replay typecheck reports zero errors/warnings; lint and both production builds pass.
All 21 dashboard routes passed at 1440px and 390px without console errors or page overflow.
Targeted browser interactions also passed at both widths with no console errors:
historical unavailable baseline, identical-driver exclusion, matched VER/PER laps,
scoped Cockpit navigation, rating intervals and methodology anchors. Replay browser
checks cover provenance, explicit event selection and unsupported event handling.
Mobile screenshots of telemetry, ratings and methodology were visually reviewed,
along with desktop ratings and mobile replay provenance.

The clean generated Evidence bundle has 711 files, 105.2 MB total and a 37.5 MB
largest file (limits 275/60 MB). Repeated Evidence builds had accumulated obsolete
hashed assets in the copied root output; that output was archived and replaced
with the current generated template build before the final budget check.

Reports: [validation/dashboard-audit-sections34-20260918](../validation/dashboard-audit-sections34-20260918/).
Historical sections 1/2 diagnostics above remain tied to their original snapshot.
