# Racecraft v3: continuity, ownership and limits

Package 3 of [the remediation plan](data-trust-remediation-plan.md), on
`fix/racecraft-continuous-battles`, after merged PR #70 (`adf25bb`).
Baseline snapshot: `20260910-race-control-v2`.
New snapshot: `20260910-racecraft-v3`.

## Changed rules

- An eligible resolved episode requires a **longest uninterrupted pressure run**
  of at least 10 seconds within a positive gap of at most 1 second. Total pressure
  remains a diagnostic, not the eligibility threshold. High confidence requires
  at least 20 seconds in one run, plus the existing coverage and evidence checks.
- Pressure duration keeps the sample-supported convention: ten consecutive 1 Hz
  samples count as 10 seconds, although their timestamps span 9 seconds. It is
  not a claim of continuously observed telemetry. Missing expected samples,
  invalid gaps, incomparable lap deficits and gaps above 1 second reset the run.
- A defended outcome requires a gap strictly above 2 seconds for at least 15
  **elapsed** seconds. At 1 Hz this needs 16 samples. A gap of exactly 2 seconds,
  including a return through the 1.5–2 second neutral band, resets the timer.
  Missing/invalid gaps, a missed expected sample or a lap mismatch also reset it.
  An episode may survive a feed gap of up to 3 seconds, but its continuous runs
  cannot bridge a missing nominal tick.
- A confirmed re-pass within 60 seconds belongs to the **original defender** as
  a reversal made and to the **original attacker** as a reversal conceded. It
  does not erase the initial conversion. These counts continue to cover all
  detected reversal episodes, not just the eligible rate denominator.
- The dashboard exposes total pressure, longest pressure run and terminal
  uninterrupted release duration separately, including in excluded evidence.

## Reproduced real-data changes

For 2025 Bahrain (round 4), battle `2025-R04-B0192`, Hamilton passed Norris at
replay time 3799 seconds; Norris re-passed at 3847 seconds. The previous summary
incorrectly credited Hamilton with a reversal made. V3 credits Norris with one
made and Hamilton with one conceded. All 10 detected reversals are checked
against their per-driver summary ownership, not merely conserved global totals.

Three eligible defended episodes were previously confirmed before their final
uninterrupted release interval had elapsed:

| Episode / attacker → defender | Old confirmation | New confirmation | Release run |
|---|---:|---:|---:|
| 2025 R5, HUL → ALB, start 2883 s | 2989 s | 3004 s | 15 s |
| 2025 R5, DOO → ALO, start 2884 s | 2992 s | 3007 s | 15 s |
| 2026 R12, TSU → GAS, start 6363 s | 6485 s | 6500 s | 15 s |

At the second before each old confirmation, the gap was exactly 2 seconds.
All three eventually satisfy the corrected rule, so their outcomes remain
Defended. Three ineligible episodes also receive later release timestamps.

## Whole-snapshot comparison

Across all 39 replay races, all 6,136 episodes still match on race, pair and
start time. Six end timestamps change. Eligible counts remain 1,819: 1,046
Converted and 773 Defended. This is an observed result, not an expectation
that stronger continuity checks can never change denominators.

338 episodes have fragmented pressure, including 66 eligible episodes whose
longest individual run is nevertheless sufficient. Two already-ineligible
episodes change evidence confidence from low to insufficient:
`2025-R09-B0085` (13 seconds total, longest run 7 seconds) and
`2026-R12-B0080` (13 seconds total, longest run 8 seconds).

No new races were ingested. Unrelated marts were not recomputed; replay coverage
remains 4,129,511 rows across 39 races, latest represented date 2026-08-23.

## Reproduction and rollout

Run a **full rebuild before incremental refreshes** when upgrading an existing
warehouse: v3 adds two battle columns and partition replacement is not a schema
migration. Both marts and the dashboard snapshot must be deployed together.

```powershell
.\.venv\Scripts\python.exe -m analytics.cli racecraft --all
.\.venv\Scripts\python.exe scripts/check_racecraft_battles.py data/warehouse/f1.duckdb
.\.venv\Scripts\python.exe scripts/dashboard_snapshot.py build --version YOUR_UNIQUE_VERSION
.\.venv\Scripts\python.exe scripts/check_racecraft_battles.py data/dashboard/latest.duckdb
```

The read-only checker targets published default thresholds. It checks pressure
durations, minimum release, high-confidence eligibility, resolved outcomes and
per-driver reversal and opportunity rollups. It reports zero violations on the
rebuilt warehouse and snapshot. Mutation tests verify that inconsistent evidence,
missing driver summaries and incorrect rollups fail the checker.

Synthetic regressions cover neutral/invalid gaps, missing expected samples,
lap mismatches, nullable flag status, fragmented pressure, 1 Hz and 2-second
cadences, exactly 10 sample-supported pressure seconds, 15 elapsed release
seconds, reversal ownership, and full/incremental output parity. Snapshot tests
execute both SQL sources with empty sentinels and populated rows.

## Remaining limitations

Gaps and order-change events are reconstructed; these tests establish internal
consistency, not independent event-detection accuracy. A missed upstream pass
can still affect the assigned outcome. Same-lap comparison remains approximate.
Pressure and release durations depend on feed cadence and configured thresholds.
Car/tyre advantage, DRS, team orders and selection effects remain uncontrolled.
Confidence labels are evidence heuristics, not calibrated probabilities or
driver-skill scores. Packages 4–6 still cover metric semantics, uncertainty,
robustness and independent validation.
