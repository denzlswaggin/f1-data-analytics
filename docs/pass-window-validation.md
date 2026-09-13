# Directed pass-sequence review

Follow-up: [timestamped OpenF1 source order](racecraft-openf1-comparison.md)
contains the Austria exchanges absent from the replay interpolation. This
narrows the disagreement without completing independent footage adjudication.

Package 6 follow-up after PR #75. This adds order-aware matching and paired
replay coverage, but **does not claim exhaustive, adjudicated pass windows**.
Articles cannot establish the absence of every short-lived exchange. No
production calculations, detector thresholds or snapshot were changed.

## Frozen source panel

`validation/pass-windows-v1.json` was frozen in `047e8ba` before querying the
selected pair outputs. It is assistant-transcribed, provisional and not
video-reviewed or human-adjudicated. Races were previously inspected, not
pristine holdouts. The earlier reference panels remain unchanged.

- [Austria 2025 race report](https://www.formula1.com/en/latest/article/norris-fends-off-piastri-for-austrian-gp-victory-in-thrilling-race-long.2CH71wVvRP1FaU8s04Tj7f):
  on lap 11, Piastri takes the lead at Turn 3 and Norris reclaims it on the run
  to Turn 4. The [official video-page description](https://www.formula1.com/en/video/2025-austrian-grand-prix-norris-and-piastri-go-wheel-to-wheel-for-the-lead.1836271216852050108)
  instead describes Norris staying in front. Only the page description was
  inspected, **not the video footage**. Neither text establishes a three-second
  lead duration. The sequence is a semantic challenge case, not settled truth.
- [Monza 2025 report](https://www.formula1.com/en/latest/article/verstappen-charges-to-italian-gp-win-over-norris-and-piastri.6J7R9E9tzOI9Asy6HBmoVf.6J7R9E9tzOI9Asy6HBmoVf):
  Verstappen returns the lead to Norris at the start of lap 2, then passes Norris
  on lap 4. A position return is not evidence of competitive driver skill.
- [Spa 2025 report](https://www.formula1.com/en/latest/article/piastri-wins-wet-dry-belgian-gp-after-late-pressure-from-title-rival-and.7QmPcUP90MvR5iX0w3j91):
  Leclerc holds off Verstappen throughout green running. Their laps 5-44 form a
  report-derived negative pair window, not exhaustive footage annotation.

## Protocol

Each window fixes both drivers and an anchor driver whose **replay lap** defines
the time interval. This avoids changing lap conventions when pass direction
reverses. Boundaries are the first and last available anchor ticks in the stated
lap range, not independently timed physical start/finish crossings.

Both drivers must have ordered, nonduplicate samples spanning the anchor window
(one second allowed at either edge), with no internal gap above three seconds.
Missing anchor laps, regressing anchor lap numbers, unknown lap ticks or
ambiguous simultaneous pair events make the window unscored. An event is aligned
to its closest anchor tick within one second. These are operational checks on
the **resampled replay**, not proof of continuous original telemetry coverage.

A pure dynamic-programming matcher maximizes the number of **ordered one-to-one**
matches. Direction and exact anchor lap must agree; tolerance was frozen at zero.
One detection cannot explain two references. Ties prefer the earliest observed
sequence, then earliest reference sequence. Unmatched references and detections
are retained by index for review; they are not silently discarded.

The matcher accepts a lap tolerance for separately designed protocols, but this
panel does not loosen tolerance after observing results. The report deliberately
supports only provisional panels and publishes null precision/false-positive
counts. A future adjudicated evaluation needs an explicit, separately reviewed
protocol rather than toggling these references to "complete".

## Results and unresolved finding

Snapshot `20260911-robust-estimates-v4`, SHA-256
`af90ff3bbfab995d8aaf42d8dd18a6c055a3b0c06bf2b4a8c6f276191de2fded`.
All three selected windows pass the paired replay coverage checks.

| Pair window | Reported sequence | Detected sequence |
|---|---|---|
| Austria NOR/PIA, lap 11 | PIA passes NOR; NOR passes PIA | Neither present |
| Monza VER/NOR, laps 2-4 | NOR passes VER; VER passes NOR | Both, in order |
| Spa VER/LEC, laps 5-44 | No reported pair pass | No detected pair pass |

Monza detections are at replay seconds 111 and 285. Austria's anchor window is
805-875 seconds; both drivers have 71 one-second samples. In that window,
`race_replay.running_order` is continuously NOR=1 and PIA=2. Thus the missing
sequence is already absent from reconstructed ordering, not merely an absent
published battle row. This is a diagnostic observation, **not proof of the root
cause**. Source definitions, lap assignment and reconstruction must be reviewed
against footage. Do not attribute this automatically to the detector's existing
three-second persistence gate or lower that gate to make the panel pass.

There are two matched and two unmatched positive references. They do not yield
an accuracy percentage: duration/definition and completeness are unresolved.
No global precision, recall, false-positive rate or calibration claim follows.

## Reproduce

```powershell
.\.venv\Scripts\python.exe scripts/report_pass_windows.py
.\.venv\Scripts\python.exe -m pytest tests/test_pass_windows.py tests/test_pass_sequence_matching.py --no-cov
```

CLI accepts `--snapshot` and `--reference`, opens the database read-only and
emits full coverage diagnostics, expected/detected sequences, matching indices,
snapshot metadata and a normalized reference hash. Full results are committed
in `validation/pass-window-results-v1.json`. LF-normalized reference SHA-256:
`014500672952853d40baecdee71d504844ecea12def84bc1dd242196f0dc2cd5`.

Tests cover reverse order, repeated events, direction, a greedy-matching
counterexample, malformed inputs, deterministic ties, empty windows, missing
partners, sample gaps, unknown laps and unreviewed extra detections.

## Next gate

Review the Austrian footage with a second reviewer and record frame/time bounds
and the chosen definition of a completed pass. Then freeze exhaustive pair
windows including lapping, retirements, pit cycles and reversals before tuning.
Untouched-race production-model evaluation and calibrated uncertainty remain
separate open work. The package 6 completion gate is still open.
