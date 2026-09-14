# Model pass events conflicting with observed pit intervals

The `20260914-recovered-pit-times` snapshot accepted 2,445 model pass events.
Forty-seven completion timestamps fall inside a fully observed pit entry/exit
interval for at least one participant (56 participant overlaps). The detector's
coordinate-proximity test had accepted these events despite the pit evidence.
This contradicts treating them as confirmed on-track passes at those timestamps.
It does not adjudicate whether a physical pass occurred at some other time.

`validation/overtake-pit-intervals-v1.json` records every overlap, the original
event evidence and the baseline snapshot hash. The regression reconstructs each
interval from the frozen recovered lap files. Complete pairing yields 2,143
intervals, with 74 unpaired entries and 66 unpaired exits. No simultaneous or
nonalternating boundary sequence occurs in this capture.

The [FastF1 source](https://github.com/theOehrly/Fast-F1/blob/v3.8.3/fastf1/core.py)
distinguishes pit entry/exit observations and in/out laps. The application stores
their session-relative seconds. `analytics.pit_intervals` subtracts the same
full-field minimum lap start used by `analytics.replay`; it does not derive the
clock from only the two participating drivers or clamp a timestamp to a lap end.

The production detector excludes an event if its completion timestamp is inside
either participant's complete observed interval, including either endpoint.
Both standalone pass refreshes and the atomic Racecraft rebuild supply the full
race lap scope. Missing initial entries and final exits remain unpaired. Repeated
boundary kinds, simultaneous boundaries, mixed race scopes and invalid clocks
reject processing rather than inventing an interval.

The `racecraft-inputs-v3-observed-pit-intervals` receipt requires a fresh rebuild
with the current method. The publication checker separately reconstructs paired
intervals in SQL and rejects overlapping accepted events even if their receipts
match. This guards the semantic rule as well as input/output integrity.

Run the publication check against a rebuilt snapshot:

```powershell
python scripts/check_racecraft_battles.py data/dashboard/latest.duckdb
```

Remaining events explicitly carry `pit_interval_check=no_observed_overlap`.
This means only that there is no overlap with the available complete intervals.
It is not proof of complete pit coverage, accurate order interpolation, correct
physical pass timing or an independently reviewed on-track overtake. In
particular, pit-cycle effects can extend beyond the recorded pit interval in
lap-based order reconstruction. Heuristic confidence remains uncalibrated.
