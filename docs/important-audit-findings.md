# Important audit findings: corrections before feature expansion

Branch: `fix/important-audit-findings`, based on `main`. The separate
`feat/evidence-backed-insights` branch is preserved; new Cockpit findings and
direct teammate battles are not part of this correction branch.

## Requirements

1. Keep pit-timing scenarios explicitly experimental. Remove promoted timing-gain
   headlines and stop recommendations. Show eligible/analysed counts and boundary
   minima while retaining conditional scenario diagnostics and exclusions.
2. Align rating claims with actual static/dynamic resampling units. Individual
   rating intervals do not establish exact-rank probabilities or isolate talent.
3. Put paired Saturday/Sunday uncertainty in the primary display, distinguish
   missing intervals from intervals crossing zero, and avoid specialist labels.
   Explain the exploratory nature of screening multiple drivers.
4. Generate current evidence counts from the verified snapshot and distinguish
   those counts from dated historical diagnostics. Refresh README statistics
   without rewriting historical reports as current evaluations.
5. Preserve and test missing-versus-zero, censored-versus-exact, partial-field and
   failed-publication safeguards. Publish no accuracy claim from passing tests.

## Pit-timing promotion gate

The 18 September diagnostic evaluates a fitting component, not complete strategy
accuracy: 1.136 s MAE versus 0.652 s for a training-median baseline. It does not
justify selecting a more attractive model after inspecting the same holdout.
The current release leaves the estimator unchanged and removes recommendation
framing from its presentation.

Before any future promotion, freeze the model, cohort, exclusions, metrics and
baseline before observing a new race holdout. Evaluate observable held-out pace
targets with race-clustered uncertainty and report coverage and failures as well
as errors. Training must precede evaluation. An improvement in that component
does not establish the unobserved outcome of a different stop: a separate,
explicit identification argument and calibrated uncertainty are required before
causal or optimal-strategy claims. No passed publication check waives this gate.
