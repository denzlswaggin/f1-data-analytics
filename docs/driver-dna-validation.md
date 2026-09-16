# Driver DNA validation protocol

Driver DNA describes observed technique on representative fast race laps. It is
not a driver ranking and does not identify a causal driver effect independent of
the car, setup or race state.

## Pair construction

The production comparison is selected jointly for both teammates. A valid pair
must come from the same race and team, use the same dry compound, have green
track status, and remain within three race laps and three tyre-life laps. Among
valid pairs, the selector minimises the combined deficit to each driver's
fastest telemetry-backed lap plus small lap-number and tyre-age penalties. The
selected gaps and score are retained in the evidence mart.

## Robustness battery

Run `f1-analytics driver-dna-validate --from-season 2024` after rebuilding the
mart. The command reports:

- split-sample agreement between the early and late half of each profile;
- maximum leave-one-race-out movement;
- race-level sign agreement;
- coverage under ±1/±2, ±3/±3 and ±5/±5 lap/tyre-life tolerances;
- a shuffled-driver-label negative control for every technique axis.

A driver-axis is labelled stable only with at least five races, split movement
at or below 1.0 robust-z, leave-one-out movement at or below 0.75 robust-z and
at least 60% sign agreement. These are publication diagnostics, not p-values.
The published stability mart evaluates every contiguous available season window,
so dashboard diagnostics always match the season range used by the corresponding
Driver DNA profile.

## Interpretation

The strongest claims are repeated directions with narrow bootstrap intervals,
stable split/leave-one-out diagnostics and observed between-driver separation
above the shuffled control. Limited profiles remain visible as evidence, but
should be described as hypotheses rather than durable traits.
