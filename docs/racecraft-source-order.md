# Experimental source order and gaps

The `source-pair-audit-v1` adapter in `analytics/source_order.py` uses recorded
position changes and separately recorded intervals. It does not write production
replay or Racecraft marts. Production still uses lap-progress reconstruction;
the Austria miss and Monza timing discrepancies remain unresolved there.

An interval can be assigned only to the trailing member of an adjacent,
unambiguous pair. Any change in either rank invalidates earlier intervals,
including a swap and return between sampled ticks. Missing/tied ranks,
nonadjacent cars, negative/nonfinite gaps, lap-deficit strings and observations
older than four seconds cannot supply a gap. Future observations are never used.
Simultaneous conflicting observations fail the audit. Original observation time
and age remain visible. Every output has `pressure_eligible=false`: holding a
four-second observation on a one-second grid does not create four measurements.

The age cap is a development policy based on OpenF1's documented approximately
four-second interval updates, not calibrated uncertainty.
[OpenF1 documentation](https://openf1.org/docs/#intervals) describes interval
values and missing/lapped states. Even same-source order and gaps can have
different delays; timestamp ordering alone cannot certify physical coherence.
Position changes have no heartbeat, so quiet periods cannot establish complete
order coverage. Pair-only ranks must not overwrite a full-field replay.

## Frozen development results

New schema-v2 captures in `validation/openf1-*-2025-intervals` preserve all eight
raw responses and their SHA-256 digests. Earlier six-response captures remain
unchanged. Reports bind their snapshot and newline-normalized manifest hashes.

| Window | One-second ticks | Usable trailing gap samples | Distinct usable observations |
| --- | ---: | ---: | ---: |
| Austria NOR/PIA lap 11 | 71 | 62 | 20 |
| Monza VER/NOR laps 2–4 | 252 | 221 | 65 |
| Spa VER/LEC laps 5–44 | 4429 | 3932 | 1101 |

These counts describe availability, not accuracy or independent measurements.
Each tick produces two driver rows; the leading member's gap to a third car is
outside this pair audit. Spa also has nonadjacent periods, missing interval
values and intervals invalidated by order changes.

Austria's source order changes NOR/PIA to PIA/NOR and back. At replay second 822,
Norris is second with a newly observed 0.037-second interval behind Piastri;
the observation follows the recorded position change. At second 835 Norris is
first again and has no assigned pair-ahead gap. The frozen regression verifies
these source states, without treating them as physical-event ground truth.
No new production conversion is inferred from either exchange.

## Reproduce

```powershell
.venv/Scripts/python.exe -m scripts.evaluate_source_order --capture validation/openf1-austria-2025-intervals --window austria-2025-mclaren-lap11 --output data/warehouse/austria-source-order-new.json
.venv/Scripts/python.exe -m pytest tests/test_source_order.py tests/test_openf1_reference_capture.py tests/test_openf1_order_comparison.py --no-cov
```

The evaluator refuses to overwrite a report. CI uses frozen responses and no
network credentials. Before production promotion, collect full-field order and
interval streams, evaluate pit/neutralization context and observation-supported
pressure, and compare an untouched frozen race scope. The three existing windows
are development cases. Independent review remains pending; neither source
agreement nor passing software tests establishes total data accuracy.

## Full-field candidate

`field_samples` now audits every entry in a captured session roster together.
At each sampled instant the declared field must have unique ranks spanning 1..N;
missing, duplicate or skipped ranks make all order and opponent assignments
unknown. The ahead driver comes from this same field state, never from pair
overwrites of lap-model ranks. All gaps predating any field order change are
invalidated, including changes between sampled ticks. This deliberately
conservative policy can discard a still-useful gap after an unrelated exchange.
It has not been calibrated for production.

Schema-v3 captures include the original `drivers`, `position`, `intervals`,
`laps`, `sessions` and `overtakes` responses. The loader verifies their hashes,
session scope and roster membership. An empty or duplicate roster, or an
observation for an undeclared driver, fails validation. These are session
entries, including retired or non-starting drivers; the roster does not establish
who was actively racing at each instant.

All three existing development windows have 20-entry full-field captures and
reports in `validation/openf1-{austria,monza,spa}-2025-field`.

| Window | Driver/tick rows | Available gap | Predates order change | Stale | Non-numeric | No pair ahead |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Austria lap 11 | 1,420 | 940 | 257 | 142 | 10 | 71 |
| Monza laps 2–4 | 5,040 | 3,665 | 608 | 491 | 24 | 252 |
| Spa laps 5–44 | 88,580 | 72,416 | 3,541 | 7,641 | 553 | 4,429 |

Each window samples the entire roster on the aligned one-second grid; counts
include held observations and must not be read as independent measurements.
The full-field Austria regression retains both source lead changes and Norris's
new 0.037-second interval behind Piastri. The clock still uses four selected-pair
lap anchors projected from the same full capture; it is not validation of every
driver's clock. Sparse order changes have no heartbeat. Coherent sampled ranks
therefore do not establish complete source coverage or physical event accuracy.
Every output remains `pressure_eligible=false`, and production promotion remains
disabled pending event, pit and continuity validation beyond these known cases.

```powershell
.venv/Scripts/python.exe scripts/capture_openf1_reference.py --session 9955 --full-field --output data/warehouse/austria-full-new
.venv/Scripts/python.exe -m scripts.evaluate_field_order --capture validation/openf1-austria-2025-field --window austria-2025-mclaren-lap11 --output data/warehouse/austria-field-report-new.json
```
