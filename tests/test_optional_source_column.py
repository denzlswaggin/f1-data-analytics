"""The additive staging fields work with both legacy and updated raw schemas."""

from pathlib import Path
from types import SimpleNamespace

import duckdb
from jinja2 import Environment


def test_optional_pit_timestamp_sql_preserves_values_and_legacy_nulls() -> None:
    template = (
        Path(__file__).resolve().parents[1] / "warehouse/dbt/macros/optional_source_column.sql"
    ).read_text(encoding="utf-8")
    environment = Environment(extensions=["jinja2.ext.do"])
    with duckdb.connect() as connection:
        connection.execute("create table legacy as select 1 lap_number")
        connection.execute("create table updated as select 1 lap_number, 80.125 pit_in_time_sec")
        adapter = SimpleNamespace(
            get_columns_in_relation=lambda table: [
                SimpleNamespace(name=row[0])
                for row in connection.execute(f"describe {table}").fetchall()
            ],
            quote=lambda column: f'"{column}"',
        )
        module = environment.from_string(template).make_module(
            {"adapter": adapter, "execute": True}
        )
        macro = module.__dict__["optional_source_column"]
        for table, expected in (("legacy", None), ("updated", 80.125)):
            expression = macro(table, "pit_in_time_sec", "double precision")
            result = connection.execute(f"select {expression} from {table}").fetchone()
            assert result == (expected,)
