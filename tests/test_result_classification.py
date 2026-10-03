"""Classification comes from result positionText, never retirement wording."""

from pathlib import Path

import duckdb
import pytest
from ingestion.dashboard_snapshot import validate_recorded_story
from jinja2 import Environment


@pytest.mark.parametrize(
    ("position", "position_text", "status", "expected"),
    [
        (1, "1", "Finished", True),
        (20, "20", "Lapped", True),  # Norris, Austria 2024
        (18, "18", "Engine", True),  # classified retirement
        (18, "R", "+10 Laps", False),
        (2, "D", "Disqualified", False),
        (20, "W", "Did not start", False),
        (20, "F", "Did not qualify", False),
        (1, None, "Finished", None),
        (1, "", "Finished", None),
        (1, "mystery", "Finished", None),
        (1, "2", "Finished", None),  # conflicting positions
        (0, "0", "Finished", None),
    ],
)
def test_staging_classification(
    position: int, position_text: str | None, status: str, expected: bool | None
) -> None:
    template = Path("warehouse/dbt/models/staging/stg_results.sql").read_text(encoding="utf-8")
    sql = (
        Environment()
        .from_string(template)
        .render(
            source=lambda *_: "source_results",
            season_in_context=lambda column: f"cast({column} as integer) between 2024 and 2026",
            dbt_utils={"generate_surrogate_key": lambda _: "'key'"},
        )
    )
    with duckdb.connect() as conn:
        conn.execute(
            """
            create table source_results as select
                2024 season, 11 as round, 'norris' driver_id, 'NOR' driver_code,
                'Lando' driver_given_name, 'Norris' driver_family_name,
                'British' driver_nationality, 'mclaren' constructor_id,
                2 grid, ? as position, cast(? as varchar) position_text,
                0 points, 64 laps, ? status, null time_millis
        """,
            [position, position_text, status],
        )
        conn.execute("create schema staging")
        conn.execute("create table staging.stg_results as " + sql)
        actual = conn.sql("select is_classified from staging.stg_results").fetchone()
        assert actual is not None and actual[0] is expected
        # Even if a downstream copy repeats the same mistake, publication rejects it.
        conn.execute("update staging.stg_results set is_classified = ?", [expected is not True])
        with pytest.raises(ValueError, match="classification disagrees"):
            validate_recorded_story(conn)
