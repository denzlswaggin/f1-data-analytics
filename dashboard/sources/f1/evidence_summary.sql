-- Exported together and validated against the immutable snapshot before sourcing.
with decoded as (
    select unnest(from_json(payload, '[{"analysis": "varchar", "candidates": "integer", "eligible": "integer", "races": "integer", "unit": "varchar", "limitation": "varchar", "validation_status": "varchar"}]')) as item,
        snapshot_version, snapshot_sha256, methodology_version
    from read_parquet('../data/dashboard/audit-evidence.parquet')
    where dataset = 'evidence_summary'
        and case when snapshot_version = (select version from dashboard.snapshot_metadata)
            then true else error('Audit evidence is stale; run npm run sources:strict') end
)
select item.*, snapshot_version, snapshot_sha256, methodology_version from decoded
