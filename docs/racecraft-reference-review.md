# Racecraft reference review: first diagnostic batch

This delivery starts independent adjudication; it does not certify detector
accuracy. Three previously inspected pair windows are prepared for review:
Austria 2025 NOR/PIA lap 11, Monza 2025 VER/NOR laps 2–4, and Spa 2025 VER/LEC
laps 5–44. They are diagnostic cases, not complete races or untouched holdouts.

## Frozen definition and review workflow

`validation/racecraft-review-v1/packet.json` freezes the scope, anchor driver,
zero-lap matching tolerance and `sustained-pair-pass-v1` definition. A counted
event is an on-track exchange held for at least three continuous seconds.
Position returns count as exchanges; pit-cycle changes, lapping and retirements
do not. This target is not proof of competitive intent or Racecraft's ten-second
pressure requirement. Shorter exchanges must be recorded in the review notes,
not silently relabeled as three-second passes.

Give each reviewer only `packet.json` and their own blank `reviewer-a.json` or
`reviewer-b.json`. Do not distribute the provisional report labels or diagnostic
results before their annotations are frozen. The packets omit prior expected
events and narrative hints, but the cases themselves have already been inspected;
this cannot create pristine race holdouts retrospectively.

Each reviewer must independently inspect footage covering the whole specified
pair window and both directions, then record:

- A distinct reviewer identity, ISO review date, footage URL and start/end times
  in that footage. The footage window must cover the complete anchor-lap window,
  plus enough trailing footage to check the last event's hold duration.
- Every qualifying exchange in chronological order, with `passer_code`,
  `passed_code`, anchor-driver `lap_number`, `footage_t_s` and `held_until_s`.
  Film clocks and replay clocks need not match. Evaluation matches direction,
  sequence and exact anchor lap, not exact video seconds.
- Any uncertainty or occlusion. Highlights and a report mentioning a pass do not
  establish exhaustive coverage. Leave `complete=false` when an unseen exchange
  cannot be excluded. A genuinely reviewed negative window has an empty event
  list, `complete=true` and no uncertainty.
- `independent_of_detector=true` only if the annotation was made without using
  detector output as ground truth. Never copy the expected events from the
  existing report panel into these files as if footage had been reviewed.

The tool requires exactly two distinct reviewer IDs, matching protocol hashes,
complete review-window inventories, independent-review declarations, footage
references and agreement on the full event sequence. Disagreement, missing replay
samples/order, incomplete footage review and uncertainty leave the window
unscored. They are not false negatives, false positives or true negatives.

Reviewer identities and footage declarations are not authenticated by this tool.
Checksums detect changed artifacts, not fabricated attestations. The two reviewers
must actually be independent; two names entered by one person do not establish
that fact. Preserve original reviews and resolve disagreements with a documented
third review before designing a later adjudication protocol.

## Current results and reproduction

Both committed review files are intentionally blank. `score-pending.json` has
zero of three windows scored and null precision/recall/counts. No human review
has been invented. The existing provisional sequence report remains separate.

```powershell
.venv/Scripts/python.exe scripts/racecraft_review.py score --packet validation/racecraft-review-v1/packet.json --review validation/racecraft-review-v1/reviewer-a.json --review validation/racecraft-review-v1/reviewer-b.json
.venv/Scripts/python.exe scripts/report_racecraft_order.py
.venv/Scripts/python.exe -m pytest tests/test_racecraft_review.py tests/test_pass_windows.py tests/test_pass_sequence_matching.py --no-cov
```

After genuine agreement, the evaluator reports TP/FP/FN and precision/recall only
for the covered reviewed windows, alongside scored and total window counts. An
empty denominator stays null. It never reports population accuracy or a
per-tick false-positive rate; neither is identified by these selected cases.
The output records hashes of the protocol, reviews and snapshot for reproduction.
This workflow is separate from production publication integrity checks. It does
not automatically mark existing dashboard episodes as independently verified.

## Austria: narrower source of the discrepancy

The [official F1 report](https://www.formula1.com/en/latest/article/norris-fends-off-piastri-for-austrian-gp-victory-in-thrilling-race-long.2CH71wVvRP1FaU8s04Tj7f)
describes a Piastri/Norris exchange on lap 11. Its text does not establish a
three-second hold. Footage adjudication is still required to label this case.

The diagnostic on snapshot `20260914-racecraft-integrity` reproduces these facts:

- Anchor replay interval: seconds 805–875; 71 samples for each driver. NOR remains
  rank 1 and PIA rank 2 throughout.
- The current replay ranks cars by linear lap-progress curves derived from lap
  timing. X/Y supports activity/proximity checks, not the ranking itself.
- Recomputing both curves from stored race laps shows NOR's modeled progress
  ahead by 0.009106–0.009968 laps throughout this interval. There are no interior
  interpolation knots in this interval. The linear model therefore cannot contain
  a reversal here, even between its one-second output samples.

`austria-order-diagnostic.json` records the lap timing inputs, curve knots and
snapshot hash. This narrows the observed discrepancy to upstream modeled order;
lowering the overtake persistence threshold cannot recover an order reversal
that this input never contains. It does not prove the physical duration of the
reported exchange or prove that the detector should count it under its definition.

## Next evidence gate

Complete these reviews with suitable footage and independent reviewers. Then
freeze a separate whole-race protocol and an untouched evaluation split before
changing the order reconstruction. Whole-race TV coverage alone may not establish
all pair interactions; missing views require onboard evidence or unscored scope.
Use the diagnostic races for development only. Report missed events, extra events,
coverage exclusions and per-race counts on the untouched split before making
stronger accuracy claims. The current three-case batch does not complete that gate.
