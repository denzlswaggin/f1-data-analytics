# Observed persistence correction

The production detector previously accepted an adjacent swap whenever no later
observed pair contradicted it. It did not require observations through the
three-second deadline. A truncated recording, a disappearing driver and even a
multi-second timing gap could therefore produce `persistence=confirmed`.

The corrected detector requires both finite orders through the first observation
at or beyond the deadline. Every intervening pair must retain the direction, and
adjacent observations may be at most one second apart by default. Right-censored
follow-up or missing order cannot confirm persistence. The short pre-swap
transition allowance remains separate: it does not relax post-swap observation
requirements. The one-second limit matches the published replay grid; it is not
a claim of continuous physical observation between samples.

Non-finite or negative completion gaps are rejected. Invalid times and nonpositive
or fractional ranks cannot establish a state. Conflicting driver/tick records
raise an error instead of choosing one arbitrarily. Identical duplicates remain
harmless. Four new regression cases reproduced the old persistence defect before
the fix; a complete window ending exactly at the deadline remains accepted.

## Real-data finding

In snapshot `20260914-recorded-results`, the detector lists PER passing NOR in
Austria 2024 at replay second 4605. Over seconds 4605–4608, PER has four order
observations and NOR has only one. The event therefore lacks the required
three-second follow-up. Removing it from the accepted detector output does not
prove that no physical pass occurred; it removes an unsupported confirmation.

The full 59-race rebuild removes exactly this one accepted event: 2,446 becomes
2,445, with no added events. All 9,117 Racecraft episodes and 1,163 driver/race
summaries are unchanged by value. The removed event was not an eligible battle
conversion. `validation/overtake-persistence-v2.json` records the baseline hash,
original event and its five available pair observations across four clock ticks
spanning three seconds. The new snapshot is `20260914-observed-persistence`.

All 59 replay races are rebuilt with unchanged pressure and release thresholds.
The processing receipt version becomes `racecraft-inputs-v2-observed-persistence`,
and records the `max_persistence_gap_s` parameter. Old receipts are rejected until
passes and dependent Racecraft outputs have been rebuilt together. This does not
repair lap-interpolation timing errors or independently validate physical passes.

## Reproduce

```powershell
.venv/Scripts/python.exe -m pytest tests/test_overtakes.py --no-cov
.venv/Scripts/python.exe -m analytics.cli racecraft --all
```

Use an isolated operational warehouse for the rebuild, preserve unrelated
snapshot tables, then publish through the standard immutable snapshot exporter.
The exporter verifies the new receipts against the combined publication inputs.
