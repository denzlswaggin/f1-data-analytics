# Race replay motion continuity plan

## Problem statement

The replay position feed is sampled independently from the browser animation clock. Some
FastF1 sessions also contain long runs of repeated coordinates followed by a large coordinate
update. The current pipeline preserves those sample-and-hold plateaus, resamples every gap with
`numpy.interp`, and the browser applies a uniform Catmull-Rom spline. Together these behaviours
can make a car stop, cross a large distance too quickly, or overshoot the visible circuit.

An audit of the 39 replay bundles currently shipped in `web/static/data` found one-second moves
as large as 2,998 position units (about 300 m/s) and races where 73.2% of consecutive raw samples
repeat the previous coordinate. This is source-feed quantisation, not normal vehicle motion.

## Delivery plan

1. Normalise position samples before replay resampling.
   - Drop non-finite coordinates, timestamps, and `(0, 0)` sentinels.
   - Collapse each run of equal coordinates to a point at the run's temporal midpoint so a
     sample-and-hold feed becomes continuous movement between genuine position updates.
   - Preserve the original samples for retirement detection; a parked car must still disappear.
   - Do not interpolate across a source outage. Missing intervals remain absent from the replay.
2. Make browser interpolation geometry-safe.
   - Score complete laps by coverage, step stability, and start/finish closure, then use the
     cleanest lap as the canonical closed circuit path.
   - Drive every car forward along that path using its continuously interpolated lap progress.
     Raw X/Y remains a fallback when timing context is unavailable, not the animation authority.
   - Use linear interpolation between validated fallback samples. A line segment stays inside its
     endpoints' convex hull and cannot produce Catmull-Rom corner overshoot.
   - Do not draw a car while the replay clock is inside a discontinuity reported by the backend.
3. Add regression and quality coverage.
   - Python tests cover repeated-coordinate plateaus, non-finite input, source outages, and
     retirement behaviour.
   - TypeScript tests cover sharp-corner interpolation and discontinuities.
   - Existing replay, export, type, lint, and production-build checks stay green.
4. Rebuild replay partitions from the cleaned source and republish the static snapshot.
   - Compare maximum motion, stationary-run share, missing intervals, and source coverage before
     replacing the published assets.
   - Spot-check at least one high-quantisation race and one normal race at 1x, 6x, and 24x.

## Acceptance criteria

- Cars never follow a spline outside the segment defined by adjacent replay samples.
- A car with monotonic lap progress cannot reverse direction because of corrupted live X/Y.
- Animated cars remain on the same canonical path that the canvas draws as the circuit.
- A source outage is not represented as an on-track straight-line shortcut.
- Quantised coordinate runs produce steady motion instead of a stop-and-jump pattern.
- Retired cars still disappear according to the configured retirement grace period.
- Running order, lap state, event timing, and the shared replay clock remain unchanged.

The checked-in Arrow bundles are generated artifacts. Code and tests land first; the final data
refresh should be a separate operational commit so its large binary diff is auditable and can be
reverted independently.
