# Valid observations are required for lap air classification

Traffic classification previously accepted an infinite follower gap as clean
air and a noninteger or infinite rank as a following car. A small number of
usable gaps could determine the state of a whole lap despite mostly unknown
context. Dropping unknown rank rows before estimating the replay cadence could
also make sparse rank observations appear to cover the lap. Conflicting rows at
one driver/tick were resolved by whichever row appeared first.

The classifier now requires finite positive integer ranks and finite positive
follower gaps. Missing rank rows remain in the cadence calculation. Both replay
presence and usable order/gap coverage must reach the configured minimum (80%
by default) before classifying a lap as traffic or clean air. Low-evidence laps
remain in the existing `mixed` category; they are not clean-air reference laps.
Exact duplicate context records are harmless, while conflicting driver/tick
records reject the scope. Nonfinite thresholds, invalid lap/stint/tyre counters
and textual missing compounds cannot enter the calculation as valid evidence.

This is stricter input validation within the robust-peer method, not a new
driver-skill or causal traffic model. Replay-derived gaps still cannot identify
all physical traffic or lapped-car interactions.

The full published snapshot contains no infinite replay clocks, ranks or gaps,
and no affected noninteger lap counters in the existing pace evidence. A complete
recomputation retains exactly 51,052 evidence rows and 1,145 summary rows, with
zero full-row differences. The dataset is not replaced merely to change a version
label. `validation/traffic-input-validity-snapshot.json` records the snapshot and
implementation hashes with the comparison results.

Reproduce this check without changing the snapshot:

```powershell
python scripts/check_traffic_reproduction.py data/dashboard/latest.duckdb `
  --report data/warehouse/new-traffic-reproduction.json
```

Existing report files are refused. Changes to the snapshot or traffic code during
verification invalidate the check. This establishes reproducibility and the
measured impact of the validation change, not independent event accuracy.

The metric publication checker rejects inconsistent context counts, invalid lap
metadata and traffic/clean classifications below usable coverage. CI now runs
shared-pit, robust-estimate, metric-evidence and traffic-reproduction checks on its compact snapshot,
alongside Racecraft integrity and browser checks. Full-data reproduction remains
an explicit audit rather than a claim that the small CI fixture covers every race.

The expected sample interval now comes from the distinct shared replay clock
within each race, before filtering to representative laps. It no longer comes
from each driver's surviving rows. For example, retaining only every tenth
one-second row for a driver now produces about 10% coverage instead of treating
that driver as a complete ten-second feed. Such laps stay mixed and cannot
publish a clean-air estimate. Separate races retain separate clock estimates;
intentional whole-field two-second resampling remains supported.

The [shared-clock audit](../validation/traffic-shared-clock-20260914.json)
recomputes all 51,052 published evidence rows and 1,145 summaries with zero
full-row differences. Regressions separately demonstrate the correction on
missing driver rows and ensure differently sampled races cannot affect each
other's clock. The current snapshot does not require a data replacement.

This is coverage of the reconstructed replay grid. The grid can contain
interpolated values, and its cadence is inferred from surviving field ticks.
Uniformly missing ticks across the entire field cannot be distinguished from
intentional resampling by this check alone. It is not a measurement of raw
sensor coverage or independent evidence that a physical gap is accurate.
