# Recorded result classification

`stg_results.is_classified` now follows the preserved Jolpica `positionText`
field, independently of the descriptive result `status`. A positive position
matching the numeric finishing position is classified. `R`, `D`, `W` and `F`
mean unclassified. Missing, unfamiliar or conflicting evidence remains null.

The [Jolpica results serializer at the reviewed revision](https://github.com/jolpica/jolpica-f1/blob/11f9d1dd481240d38c21e78388af515dbe2d611d/jolpica_api/ergastapi/serializers.py#L166-L199)
provides numeric text for classified entries and replaces it with these codes
for unclassified entries. Descriptive statuses such as `Lapped`, `Engine` or
`+10 Laps` cannot determine classification by themselves.

As a primary-source cross-check, the [FIA Austrian GP 2024 classification](https://www.fia.com/events/fia-formula-one-world-championship/season-2024/austrian-grand-prix/race-classification)
places Norris twentieth with 64 laps. His stored numeric position text was
already correct; the application incorrectly treated his `Lapped` status as
unclassified. This is one corroborated example, not a review of every result.

The migration corrects 566 of 8,653 stored results: 556 become classified and
10 become unclassified. Its [row-level audit](../validation/result-classification-20260914.json)
records the baseline and candidate hashes and every changed classification.
All other columns and relations are compared in both directions with
`EXCEPT ALL`; they must remain identical. Model passes and battles are unchanged.

Reproduction, using the original pit-interval snapshot as the source:

```powershell
.venv/Scripts/python.exe scripts/migrate_result_classification.py --source data/dashboard/f1-dashboard-20260914-pit-interval-gate.duckdb --output data/warehouse/classification-reproduction/f1.duckdb --report data/warehouse/classification-reproduction.json
```

Candidate and report paths must be new. The candidate passes the complete
snapshot contract and Racecraft receipt checks before an audit is written.
Normal dbt refreshes use the corrected staging expression. Snapshot publication
checks every staged result against its source text before comparing the recorded
story, so repeating a wrong flag in both tables cannot pass validation.

Replay labels now say `classified` or `not classified` after a driver's samples
end. These labels describe the recorded classification and do not assert that
the driver reached the finish or retired. Missing samples still remove the car
from the track. The pipeline does not independently certify the upstream results.
