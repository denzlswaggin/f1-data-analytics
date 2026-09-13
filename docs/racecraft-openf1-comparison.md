# Austria source-order comparison without F1 TV

The diagnostic now has additional source evidence: OpenF1's captured historical
position stream contains both NOR/PIA lead exchanges that are absent from the
lap-interpolated replay. This is a reproducible feed disagreement, not completed
independent video adjudication or an accuracy estimate.

## Sources and scope

The [OpenF1 documentation](https://openf1.org/docs/) describes historical data as
publicly accessible without authentication. Its position endpoint records changes
in race position. Its overtake endpoint also includes pit/penalty-related changes
and can be incomplete. It is not a clean competitive-pass reference.

The captured session is race 9955, Austria on June 29, 2025, mapped to 2025 round
11 in the snapshot by season and race date. Six original JSON responses are
committed under `validation/openf1-austria-2025`: session metadata, all session
overtake records, and position/lap records for driver numbers 4 and 81. The
manifest records URL, parameters, retrieval time, row count and SHA-256 of every
response. Capture fails on denied requests, malformed data or a wrong session or
driver; it does not turn those failures into empty event lists. An interrupted
capture does not publish a complete manifest, and existing captures are preserved.

The manifest, filenames, query scope, row identities, counts and raw-response
hashes are checked before comparison. Checksums establish artifact integrity,
not the source's authenticity, completeness or independence from FastF1.

## Measured disagreement

Snapshot: `20260914-racecraft-integrity`, SHA-256
`ead8a7cb49900b74da08e840d6c7e9724fab3e4c76aabe52124309f4a0f88664`.

The comparison uses lap-start timestamps for laps 11 and 12 for both drivers.
The four UTC-to-replay offsets span 0.159 seconds, within the fixed
one-second diagnostic limit. Missing/duplicate anchors, another race or a larger
spread abort comparison. This limit is not calibrated measurement uncertainty.
The mapped window is the anchor driver's lap 11, replay seconds 804.292–875.238.
It includes fractional lap boundaries, unlike the earlier sampled 805–875 window.

| Source UTC timestamp | Position-stream exchange | Mapped replay second | Nearest replay order |
| --- | --- | ---: | --- |
| 13:31:42.901 | PIA ahead of NOR | 821.662 | NOR 1, PIA 2 |
| 13:31:55.526 | NOR ahead of PIA | 834.287 | NOR 1, PIA 2 |

The overtake endpoint lists the same two directions and timestamps; the
snapshot's detected-pass table has neither event in this window. Those two
endpoints are not two independent confirmations. The source state between them
lasts 12.625 seconds; this is elapsed time between timestamped updates, **not a
measurement of how long the cars were physically in that order**.

The timeline applies simultaneous driver updates as one batch. Equal, missing
or invalid ranks create an unresolved interval, and a reversal is not inferred
across that interval. The final state duration is explicitly right-censored by
the window boundary. Sparse events are carried forward, with baseline update
times retained; long event silence is not proof of uninterrupted feed delivery.
`complete_source_coverage` and `accuracy` therefore remain null.

The published overlapping episode `2025-R11-B0002` is already interrupted and
ineligible because of a later pit boundary. This comparison does not establish
two eligible Racecraft conversions: eligibility additionally needs coherent
pressure/gap evidence and exclusions. Production marts and rates are unchanged.

## Video status

A [public F1 clip page](https://www.formula1.com/en/video/2025-austrian-grand-prix-norris-and-piastris-thrilling-wheel-to-wheel-fight-for-the-lead.1836276410694438753)
lists a 75-second clip. Its page was accessible, but footage playback was not
verified: no browser was connected, and the page's public embed endpoint returned
HTTP 403. No account, subscription or access restriction was bypassed. Page
descriptions were not substituted for visual annotations. Both human review
templates remain pending; no video reviewer was invented.

## Comparison windows beyond Austria

The same frozen protocol windows were also captured for Monza (session 9912,
drivers 1/4) and Spa (session 9939, drivers 1/16). The captures and comparisons
live in `validation/openf1-monza-2025` and `validation/openf1-spa-2025`.

| Window | Position-stream exchanges | Overtake endpoint rows | Snapshot pair detections | Clock spread |
| --- | ---: | ---: | ---: | ---: |
| Austria NOR/PIA, lap 11 | 2 | 2 | 0 | 0.159 s |
| Monza VER/NOR, laps 2–4 | 2 | 2 | 2 | 0.232 s |
| Spa VER/LEC, laps 5–44 | 0 | 0 | 0 | 0.232 s |

Monza retains the reported position return followed by the reverse exchange,
but agreement on counts/direction does not imply timing accuracy. The aligned
source events are at replay seconds 95.2965 and 266.2335, while the detector emits
111 and 285: differences of 15.7035 and 18.7665 seconds respectively. This is much
larger than the 0.232-second spread between its four clock anchors. These are
feed-to-model differences, not certified physical timing errors. The events are
not automatically competitive-skill evidence. The Spa feeds
contain no pair exchange in the inspected window. Zero observed changes is not
proof of exhaustive negative footage coverage. None of these rows is scored as
TP/FP/FN, and they do not provide a population accuracy percentage.

Spa ends on the final recorded lap. When both sources end on that same lap, a
recorded lap-start plus a finite positive lap duration supplies the end anchor.
It is explicitly marked `recorded_lap_end`. This fallback cannot bridge a
missing interior lap or replace a missing duration; those cases still fail.
All four boundary clocks must still meet the unchanged one-second spread limit.

## Reproduce

```powershell
.venv/Scripts/python.exe scripts/compare_openf1_orders.py --capture validation/openf1-austria-2025
.venv/Scripts/python.exe -m pytest tests/test_openf1_reference_capture.py tests/test_openf1_order_comparison.py --no-cov
```

For a fresh capture, choose a new directory:

```powershell
.venv/Scripts/python.exe scripts/capture_openf1_reference.py --session 9955 --drivers 4 81 --output data/warehouse/openf1-austria-new-capture
```

`comparison.json` records the source states, four clock anchors, nearby replay
positions and snapshot/capture identities. Automated tests use frozen responses
and a minimal snapshot slice; CI needs no OpenF1 credentials or network access.

## What this enables next

The first [source-order and interval adapter](racecraft-source-order.md) now
audits all three windows with frozen interval responses. It retains observation
ages and rejects stale or mismatched gaps; production promotion remains disabled.

Use recorded position changes as a candidate input to an experimental replay,
then evaluate it on separately frozen scopes. Do not simply overwrite
`running_order`: leader and ahead gaps currently come from the same lap-progress
model, and mixed inputs could attach pressure to the wrong opponent. A candidate
must provide coherent order, gaps, timestamps and missing-data handling together.
Compare broader race windows, pit cycles and negative cases before changing
production. Independent visual checks remain necessary to distinguish source
agreement from physical-event truth.
