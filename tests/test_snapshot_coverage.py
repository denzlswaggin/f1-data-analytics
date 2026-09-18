from pathlib import Path

import duckdb
import pytest

from ingestion.snapshot_coverage import validate_partition_preservation


def test_lost_partition_requires_an_explicit_reason(tmp_path: Path):
    old, new = tmp_path / 'old.duckdb', tmp_path / 'new.duckdb'
    for path, rounds in [(old, '(2026,13),(2026,14)'), (new, '(2026,14)')]:
        with duckdb.connect(str(path)) as c:
            c.execute('create schema marts')
            c.execute(f'create table marts.weather as select * from (values {rounds}) t(season,round)')
    with pytest.raises(ValueError, match='lose published'):
        validate_partition_preservation(old, new)
    validate_partition_preservation(old, new, [dict(table='marts.weather', season=2026,
                                                   round=13, reason='source correction')])
