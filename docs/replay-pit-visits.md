# Pit visits in race replay

The replay exports optional `pit_entry_t_s` and `pit_exit_t_s` lap fields, using
exactly the existing race-clock origin. Older snapshots and version-1 bundles
remain supported: absent columns export null, and absent fields use the existing
stint-transition estimate. The snapshot itself is not modified.

`buildPitVisits` supplies both motion windows and timeline events. Within each
driver, recorded entries pair with the next exit, without pairing across another
entry. Duplicate boundaries are ignored; unmatched boundaries remain incomplete.
Stint transitions matching a recorded visit do not create duplicate events.
Recorded visits do not require a tyre change. Tyre details describe adjacent lap
stint data; same-compound transitions are retained.

A complete recorded pair establishes time in the pit lane, not stationary service
time. The schematic animation traverses that window continuously, without the old
universal three-second hold. Partial recorded visits may use a labeled estimated
playback window when a matching stint transition supplies the missing boundary;
the measured duration remains unavailable. Otherwise watching is disabled.

## Interaction

- Selecting a marker or event opens details without seeking. Closely spaced
  timeline markers open a chronological selection list. The pit filter also lists
  every visit within the selected driver scope.
- The inspector shows timing provenance and tyres, with previous/next controls.
  Desktop uses a panel beside the circuit; smaller displays put it below the map.
- The inset separates simultaneously pitting drivers into schematic rows. Rows
  do not represent garages. The traffic list scrolls to keep controls reachable.
- Watch selects the driver, preserves the full circuit view, and plays at 1× from
  five seconds before entry until five seconds after exit, clamped to race bounds.
  It pauses at the endpoint; replay restarts the clip. Continue restores the prior
  speed. Manual seeking, driver/race changes, or another visit cancel the endpoint.
  Speed changes also exit focused playback. Closing the inspector pauses playback.

## Verification

Run the replay server tests and exporter/replay Python tests:

```sh
npm --prefix web run test:unit -- --run --project server
npm --prefix web run check
.venv/bin/python -m pytest tests/test_export_web_data.py tests/test_replay.py tests/test_dashboard_replay_v2.py --no-cov
npm --prefix web run data
npm --prefix web run build
```

With a production preview on port 4175:

```sh
node scripts/test_replay_pits.mjs http://127.0.0.1:4175/f1-data-analytics/replay/
PLAYWRIGHT_CHANNEL=chrome node scripts/test_replay_smoke.mjs
```

The pit browser test covers desktop/mobile recorded and incomplete visits,
non-seeking selection, keyboard group selection, simultaneous cars, clip endpoint
pausing, restored speed, manual seek cancellation, and closing. Screenshots are
written to the ignored `data/replay-pits/` directory. Use a production preview for
clock-controlled tests so development-server heartbeat timers cannot reload pages.

Verified against the current snapshot: 36 replay unit tests, 29 Python replay/export tests, Svelte checks, targeted ESLint, the production build, and both desktop/mobile browser suites passed.
