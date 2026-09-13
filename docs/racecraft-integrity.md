# Racecraft input integrity correction — September 14, 2026

The expanded September 13 snapshot had replay and battle summaries for 24 races
in 2024, but upstream detected passes for only four. The builder treated absent
pass partitions as empty event lists. As a result, conversion rates mixed races
with processed passes and races without them. The published summaries were
internally consistent but their comparison across races was misleading.

## Repair and measured impact

Every Racecraft refresh now detects passes directly from that race's replay,
rebuilds pit context, and computes battles and summaries together. It commits
those four marts and a processing receipt in one transaction. Race and season
overtake refreshes preserve unrelated partitions; orchestration processes all
replay seasons rather than only the configured current season.

| Measure | Previous snapshot | Corrected snapshot |
| --- | ---: | ---: |
| Replay races / processing receipts | 59 / unavailable | 59 / 59 |
| 2024 races with detected passes | 4 | 24 |
| 2024 detected passes | 130 | 972 |
| All detected passes | 1,604 | 2,446 |
| Observed battle episodes | 9,117 | 9,117 |
| Eligible resolved episodes | 2,273 | 2,820 |
| Eligible conversions | 1,046 | 1,593 |
| Eligible held positions | 1,227 | 1,227 |

All 547 additional eligible conversions belong to 2024. Battle outcomes and
summary counts for 2025 and 2026 are unchanged. No timing samples, hypothetical
battles or driver observations were generated. Detection thresholds were not
loosened. Resolved rates remain conditional on eligible episodes, not all attacks.

Each `marts.racecraft_processing` row records the method, overtake parameters,
UTC processing time, row counts and SHA-256 fingerprints of race replay,
race laps, resolved pit context, passes, battles and summaries. Publication
rejects missing/duplicate race receipts, extra output partitions and changed
input/output values. A processed race with zero detections has its own receipt.
Hash normalization ignores row order and numeric storage differences.

These receipts establish consistency with the recorded inputs, not authenticity
of the original feed or accuracy against footage. The pit fingerprint covers
the resolved context used by Racecraft, not independent completeness of raw pit
sources. Missing original telemetry and reconstruction errors remain possible.
The dashboard calls outcomes detected conversions and held positions, explains
that evidence labels are heuristic, and shows processing time and upstream pass
counts alongside coverage.

## Independent spot checks

Four positive annotations were recorded before inspecting these detector outputs,
using primary race reports. No detection thresholds or labels were changed to
obtain matches. All four match the exact reported lap:

| Race | Directed pass | Reported and detected lap |
| --- | --- | ---: |
| China 2024 | Perez → Leclerc | 39 |
| Spain 2024 | Norris → Hamilton | 32 |
| Spain 2024 | Norris → Russell | 35 |
| Netherlands 2024 | Norris → Verstappen | 18 |

Sources: [FIA China](https://www.fia.com/news/f1-verstappen-wins-action-packed-chinese-grand-prix-ahead-norris-perez),
[F1 Spain](https://www.formula1.com/en/latest/article/verstappen-holds-of-norris-challenge-to-seal-victory-at-the-spanish-grand.7a5UhXMAtkhbslSDNiPVes),
[FIA Spain](https://api.fia.com/news/f1-verstappen-holds-norris-charge-win-spanish-gp-hamilton-takes-first-podium-year),
[FIA Netherlands](https://www.fia.com/news/f1-norris-takes-dominant-dutch-grand-prix-win-ahead-verstappen-and-leclerc).
Frozen annotations and machine-readable results are in
`validation/racecraft-2024-reference-v1.json` and
`validation/racecraft-2024-results-v1.json`.

The earlier 16-case panel still has 14 positive matches (13 exact, one within its
pre-existing one-lap tolerance) and two negative matches. It mixes pass and pit
events and a competitive-conversion exclusion. Neither panel is exhaustive or
independently adjudicated by a second reviewer. The new four labels establish
passes, not Racecraft's ten-second continuous-pressure requirement. These checks
do not estimate population precision, false-positive rate or calibrated confidence.

The known [Austria 2025 sequence discrepancy](pass-window-validation.md) remains
open: short reported exchanges are absent from reconstructed running order.
This correction does not certify complete event capture or driver-skill rankings.
Exhaustive footage adjudication, including negative windows and missed events,
is still needed before claiming that level of trust.

## Reproduction and publication

```powershell
.venv/Scripts/python.exe -m analytics.cli racecraft --all
.venv/Scripts/python.exe scripts/check_racecraft_battles.py data/warehouse/f1.duckdb
.venv/Scripts/python.exe scripts/report_reference_validation.py --reference validation/racecraft-2024-reference-v1.json
```

Snapshot `20260914-racecraft-integrity` uses the previous published snapshot as
its base, replacing passes, pit context, battles, summaries and adding receipts.
The local operational warehouse lacks six unrelated Driver DNA/track-fit marts;
those published datasets are retained. Receipt validation verifies that the
base replay and race laps match the inputs of the new results before standard
snapshot export. The CI fixture is regenerated from this snapshot.

Regression checks cover missing passes, zero-event races, changed inputs and
outputs, transaction rollback and race/season partition preservation, alongside
the existing continuity, exclusion, denominator and presentation checks.
