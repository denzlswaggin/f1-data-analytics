# Event-window validation: listed stops and neutralisation probes

Second delivery of package 6, following PR #74. This extends the reference
panel without changing production calculations, thresholds or snapshot data.
It does not finish package 6 or certify model accuracy.

## Frozen references

The assistant transcribed references on 2026-09-11 before querying the selected
outputs. Pit windows were frozen in `e2c7cb7`; control probes in `a7f4ed6`.
They remain single-reviewer, not human-adjudicated, purposively selected and
not pristine held-out races. The earlier v1 panel is retained unchanged.

Pit references use the **Lap column** of the official F1
[Bahrain 2025 pit-stop summary](https://www.formula1.com/en/results/2025/races/1257/bahrain/pit-stop-summary)
and [Imola 2025 pit-stop summary](https://www.formula1.com/en/results/2025/races/1260/emilia-romagna/pit-stop-summary).
Each window covers laps 1-50, with every listed stop for that driver in that
range included. Bahrain drivers: PIA, NOR, VER, HAM, RUS, ANT. Imola drivers:
PIA, NOR, VER, HAM, RUS, BEA. Selection includes early stops, later stops under
neutralisation, Antonelli's third stop and Bearman's closely spaced stops.
This is not an exhaustive audit of every driver or every physical pit visit.

The [Imola race report](https://www.formula1.com/en/latest/article/verstappen-storms-to-victory-in-thrilling-emilia-romagna-grand-prix-ahead-of.4YJG3CyQJdFzCI6tiBtqoU)
supplies three positive control probes: VSC deployment lap 29, SC deployment
lap 46, SC withdrawal at the end of lap 53. The
[Sao Paulo 2024 report](https://www.formula1.com/en/latest/article/verstappen-wins-chaotic-sao-paulo-grand-prix-after-stunning-recovery-from.1DIc8pzRmGbC3jHJmvtBi1)
supplies a red-flag deployment probe at lap 32.

## Matching rules fixed before results

- Pit stops match **exactly by driver and lap**, one-to-one. Repeated detections
  cannot receive repeated credit for one reference event. Extra detections
  count as false positives relative to the listed-stop reference; missing
  listed events count as false negatives.
- Every annotated driver-lap needs a context row with a known pit-entry flag.
  Missing laps or unknown flags make the entire window unscored, with explicit
  diagnostics. Such windows do not silently improve either denominator.
- Overlapping windows for the same driver/race, duplicate reference events,
  incomplete annotations and invalid bounds are rejected before evaluation.
- Precision is matched / detected events; recall is matched / listed events,
  **only within scored selected windows**. Empty denominators remain null.
  No lap-level true-negative count or population false-positive rate is invented.
- Control probes report exact and predeclared +/-1 lap agreement separately.
  Their coverage requires the reference driver's replay lap and an available
  race-control source partition. This does not prove continuous feed coverage.
  Only positive probes are supported: article silence is not a negative label.

## Observed results

Snapshot `20260911-robust-estimates-v4`, SHA-256
`af90ff3bbfab995d8aaf42d8dd18a6c055a3b0c06bf2b4a8c6f276191de2fded`.

| Scope | Coverage | Exact agreement | Extra / missed |
|---|---:|---:|---:|
| Selected pit windows | 12/12 windows, 600 driver-laps | 25/25 listed stops | 0 / 0 |
| Positive control probes | 4/4 | 4/4 | Not a precision panel |

Within the selected pit windows, precision and recall are both 25/25.
**This is source agreement, not independent sensor validation.** Jolpica pit
records and official tables may share timing provenance, and pit context uses
official records as inputs. Therefore perfect agreement can establish faithful
publication without establishing independent event-detection accuracy. An extra
context entry elsewhere may represent a physical visit absent from the table;
it needs adjudication before being called a real-world false alarm.

### Source convention discrepancy preserved

The Imola prose report describes Piastri's first stop on lap 14 and Norris's on
lap 29; its pit-stop table lists laps 13 and 28. We selected the table convention
before evaluation, not a tolerance tuned after seeing outputs. The app agrees
with that table. This does not resolve all lap-boundary semantics or justify
silently shifting every source. The earlier Spa pass mismatch remains open.

## Reproduce

```powershell
.\.venv\Scripts\python.exe scripts/report_event_windows.py
.\.venv\Scripts\python.exe scripts/report_reference_validation.py --reference validation/race-control-probes-v1.json
.\.venv\Scripts\python.exe -m pytest tests/test_event_windows.py tests/test_reference_validation.py --no-cov
```

Both CLIs accept `--snapshot` and `--reference` and are read-only. Reports bind
snapshot metadata to LF-normalized UTF-8 reference SHA-256 hashes:

- `validation/pit-windows-v1.json`:
  `48644278ccddb0025fc026530409af326d77334d560cae2df9615c50de984645`.
- `validation/race-control-probes-v1.json`:
  `2a9c666385198a19fe8512d3cc328032545550a884ae5a729f61074afdec2c88`.

Full per-window/probe results are committed alongside the references. Synthetic
tests exercise failures, duplicate detections, missing coverage and denominator
rules; passing CI does not certify the historical claims.

## Still open

Second-reviewer adjudication; exhaustively annotated **on-track pass** windows
including reversals, lapping and retirements; independent timing evidence;
untouched-race production-model evaluation; race-clustered uncertainty and
calibration; causal or optimal-pit-strategy validation. Four positive control
probes validate neither effect estimates nor the absence of spurious cautions.
No stronger product claims follow from this delivery.
