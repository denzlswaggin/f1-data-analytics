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
