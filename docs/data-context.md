# Data context: 2024–2026

The active product uses Formula 1 seasons **2024, 2025 and 2026**. Dagster
partitions, the backfill command, dbt staging models and published dashboard
snapshots follow this range. The configured unattended refresh season defaults
to 2026 and may be pinned to 2024 or 2025.

Older rows may remain in a developer's raw lake or warehouse for recovery and
audit history. They are excluded from dbt staging and cannot enter a newly
published snapshot. A full dbt refresh removes them from incremental marts;
Python-built marts such as driver ratings and replay must then be rebuilt.

Some dated validation reports in `docs/` and `validation/` record earlier
experiments with wider datasets. Their figures are historical evidence, not
claims about the active 2024–2026 product. Re-run a validation before quoting
numbers for the current context.

To rebuild the warehouse context, run `dbt build --full-refresh` from the dbt
project and rebuild Python analytics marts. The current checked-in snapshot was
migrated from a checksum-verified publication because the local warehouse did
not retain every heavy source partition in that publication. The migration
removes older season rows, recomputes rating marts from the snapshot's own
2024–2026 comparisons, and applies the usual publication checks:

```bash
python scripts/dashboard_snapshot.py build --base-snapshot data/dashboard/latest.duckdb
python scripts/export_audit_evidence.py --update-readme
```
