with decoded as (
    select unnest(from_json(payload, '[{"evidence_type": "varchar", "status": "varchar", "report_date": "varchar", "evaluated_snapshot": "varchar", "evaluated_sha256": "varchar", "result": "varchar", "scope": "varchar"}]')) as item,
        snapshot_version, snapshot_sha256, methodology_version
    from read_parquet('../data/dashboard/audit-evidence.parquet')
    where dataset = 'validation_evidence'
        and case when snapshot_version = (select version from dashboard.snapshot_metadata)
            then true else error('Audit evidence is stale; run npm run sources:strict') end
)
select item.*, snapshot_version, snapshot_sha256, methodology_version from decoded
