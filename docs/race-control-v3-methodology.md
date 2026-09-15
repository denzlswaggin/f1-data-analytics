# Race-control impact v3

Race-control v3 treats an intervention as a timeline of independently publishable
facts and estimates. A failed green-recovery check can suppress field-adjusted gap
movement without suppressing an exactly timed pit stop.

## Evidence classes

- **Observed** values come from exact race-control messages, FastF1 pit timestamps,
  replay state, tyre stints or classified results.
- **Estimated** values are published only with their 90% interval, confidence,
  reference sample size and methodology version.
- **Unavailable** values remain present with an exclusion reason. They are never
  replaced by zero or by a best-effort point estimate.

The driver timeline uses deployment, pit entry, pit exit, end signal, first green
leader crossing and third post-event leader crossing. Replay state is linearly
interpolated only when samples bracket the checkpoint within two seconds; the
published pit interval includes an additional one-second timing-resolution margin.

## VSC and Safety Car pit opportunity

For an observed stop, the model measures the median change in pairwise gap against
non-pitting peers whose lap deficit is stable across pit entry and exit. Its green
counterfactual uses clean, non-neutralised stops from the same race:

`normalised green loss = observed green loss - (reference duration - target duration)`

`estimated saving = median(normalised green loss) - observed neutralised loss`

The published effect is named `estimated_vsc_pit_saving` or
`estimated_safety_car_pit_saving` so the intervention type remains explicit.

Publication requires at least one comparable peer, five clean reference stops from
at least four drivers, valid pit timestamps and a reference median absolute
deviation no greater than two seconds. A deterministic 1,000-sample bootstrap
produces the 90% interval. An interval crossing zero is an inconclusive estimate,
not evidence of a benefit. If the cohort rules fail, no number is published.

## Interpretation limits

Position, field compression, pit opportunity, tyre state and restart movement have
separate eligibility. Red flags never carry a time-gap estimate across the
suspension. Final classification is context only: incidents, traffic, tyre
performance and later racing are deliberately left unattributed, so v3 never
claims that an intervention caused a victory.

Madrid 2026 R14 is the golden case. Official Formula 1 material validates the VSC
sequence and that Antonelli stopped on lap 14 while Norris stopped on lap 15. The
numeric estimate is calculated only from timing data; article prose does not enter
the model.
