"""Export immutable dashboard replay data for the static SvelteKit application."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import duckdb
import pyarrow.ipc as ipc

REQUIRED_COLUMNS = {
    "marts.race_replay": {
        "season",
        "round",
        "driver_code",
        "t_s",
        "x",
        "y",
        "running_order",
        "gap_to_leader_s",
        "gap_to_ahead_s",
    },
    "marts.race_overtakes": {
        "season",
        "round",
        "t_s",
        "for_position",
        "passer_code",
        "passed_code",
        "gap_at_pass_s",
        "confidence",
        "evidence",
        "reason",
    },
    "staging.stg_laps": {
        "season",
        "round",
        "session",
        "driver_code",
        "team",
        "lap_number",
        "lap_start_sec",
        "lap_time_sec",
        "stint",
        "compound",
        "tyre_life",
    },
    "staging.stg_results": {
        "season",
        "round",
        "driver_code",
        "driver_name",
        "grid_position",
        "finish_position",
        "status",
        "is_classified",
    },
    "staging.stg_races": {
        "season",
        "round",
        "race_name",
        "race_date",
        "circuit_name",
        "country",
        "locality",
    },
    "staging.stg_race_control": {
        "season",
        "round",
        "session",
        "session_time_sec",
        "category",
        "flag",
        "scope",
        "message",
        "driver_code",
    },
    "staging.stg_team_radio": {
        "season",
        "round",
        "session",
        "session_time_sec",
        "driver_code",
        "recording_url",
        "transcript",
    },
    "staging.stg_driver_codes": {"season", "driver_code", "driver_name"},
    "staging.constructor_colors": {"team", "team_color"},
}


def _json_default(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    raise TypeError(f"Cannot serialise {type(value).__name__}")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(
            payload,
            default=_json_default,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _rows(
    connection: duckdb.DuckDBPyConnection, sql: str, params: Iterable[Any]
) -> list[dict[str, Any]]:
    result = connection.execute(sql, list(params))
    columns = [column[0] for column in result.description]
    return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_snapshot(snapshot: Path, manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = str(manifest.get("sha256", ""))
    actual = _sha256(snapshot)
    if not expected or actual != expected:
        raise ValueError(
            f"Snapshot checksum mismatch: expected {expected or '<missing>'}, got {actual}"
        )
    return manifest


def validate_contract(connection: duckdb.DuckDBPyConnection) -> None:
    for table, expected in REQUIRED_COLUMNS.items():
        try:
            actual = {row[0] for row in connection.execute(f"describe {table}").fetchall()}
        except duckdb.Error as exc:
            raise ValueError(f"Required replay table is unavailable: {table}") from exc
        missing = expected - actual
        if missing:
            raise ValueError(f"{table} is missing required columns: {', '.join(sorted(missing))}")


def _export_positions(
    connection: duckdb.DuckDBPyConnection, season: int, round_number: int, path: Path
) -> int:
    rows = connection.execute(
        """
        select
            cast(driver_code as varchar) as driver_code,
            cast(t_s as float) as t_s,
            cast(x as float) as x,
            cast(y as float) as y,
            cast(running_order as tinyint) as running_order,
            cast(gap_to_leader_s as float) as gap_to_leader_s,
            cast(gap_to_ahead_s as float) as gap_to_ahead_s
        from marts.race_replay
        where season = ? and round = ?
        order by driver_code, t_s
        """,
        [season, round_number],
    ).to_arrow_table()
    rows = rows.set_column(
        0,
        "driver_code",
        rows.column("driver_code").combine_chunks().dictionary_encode(),
    )
    with path.open("wb") as sink, ipc.new_file(sink, rows.schema) as writer:
        writer.write_table(rows)
    return rows.num_rows


def _race_bundle(
    connection: duckdb.DuckDBPyConnection, season: int, round_number: int
) -> dict[str, Any]:
    params = [season, round_number]
    race = _rows(
        connection,
        """
        select season, round, race_name, race_date, circuit_name, country, locality
        from staging.stg_races
        where season = ? and round = ?
        """,
        params,
    )[0]
    drivers = _rows(
        connection,
        """
        with teams as (
            select driver_code, max(team) as team
            from staging.stg_laps
            where season = ? and round = ? and session = 'R'
            group by driver_code
        )
        select
            replay.driver_code,
            coalesce(codes.driver_name, results.driver_name, replay.driver_code) as driver_name,
            teams.team,
            coalesce(colors.team_color, '#9aa0a6') as team_color,
            results.grid_position,
            results.finish_position,
            results.status,
            results.is_classified
        from (
            select distinct driver_code
            from marts.race_replay
            where season = ? and round = ?
        ) replay
        left join teams using (driver_code)
        left join staging.stg_driver_codes codes
            on codes.season = ? and codes.driver_code = replay.driver_code
        left join staging.stg_results results
            on results.season = ? and results.round = ? and results.driver_code = replay.driver_code
        left join staging.constructor_colors colors on colors.team = teams.team
        order by coalesce(results.finish_position, 999), replay.driver_code
        """,
        [season, round_number, season, round_number, season, season, round_number],
    )
    laps = _rows(
        connection,
        """
        with race_window as (
            select min(lap_start_sec) as race_start_sec
            from staging.stg_laps
            where season = ? and round = ? and session = 'R'
        )
        select
            driver_code,
            cast(lap_number as integer) as lap_number,
            round(lap_start_sec - race_start_sec, 3) as lap_start_t_s,
            lap_time_sec,
            cast(stint as integer) as stint,
            compound,
            tyre_life
        from staging.stg_laps, race_window
        where season = ? and round = ? and session = 'R'
            and driver_code in (
                select distinct driver_code from marts.race_replay where season = ? and round = ?
            )
        order by driver_code, lap_number
        """,
        [season, round_number, season, round_number, season, round_number],
    )
    messages = _rows(
        connection,
        """
        with race_window as (
            select min(lap_start_sec) as race_start_sec
            from staging.stg_laps
            where season = ? and round = ? and session = 'R'
        )
        select
            round(session_time_sec - race_start_sec, 1) as t_s,
            category, flag, scope, message, driver_code
        from staging.stg_race_control, race_window
        where season = ? and round = ? and session = 'R'
            and session_time_sec - race_start_sec >= -10
        order by t_s
        """,
        [season, round_number, season, round_number],
    )
    radio = _rows(
        connection,
        """
        with race_window as (
            select
                min(lap_start_sec) as race_start_sec,
                max(lap_start_sec + coalesce(lap_time_sec, 0)) as race_end_sec
            from staging.stg_laps
            where season = ? and round = ? and session = 'R'
        )
        select
            round(session_time_sec - race_start_sec, 1) as t_s,
            driver_code, recording_url, transcript,
            case
                when session_time_sec < race_start_sec then 'pre-race'
                when session_time_sec > race_end_sec then 'post-race'
                else 'race'
            end as phase
        from staging.stg_team_radio, race_window
        where season = ? and round = ? and session = 'R'
            and recording_url is not null
        order by t_s
        """,
        [season, round_number, season, round_number],
    )
    overtakes = _rows(
        connection,
        """
        select t_s, for_position, passer_code, passed_code, gap_at_pass_s,
               confidence, evidence, reason
        from marts.race_overtakes
        where season = ? and round = ?
        order by t_s
        """,
        params,
    )
    return {
        "race": race,
        "drivers": drivers,
        "laps": laps,
        "race_control": messages,
        "radio": radio,
        "overtakes": overtakes,
    }


def export_web_data(
    snapshot: Path,
    output: Path,
    *,
    snapshot_manifest: Path | None = None,
) -> dict[str, Any]:
    snapshot = snapshot.resolve()
    output = output.resolve()
    if snapshot_manifest is not None:
        source_manifest = verify_snapshot(snapshot, snapshot_manifest.resolve())
    else:
        source_manifest = {}

    with duckdb.connect(str(snapshot), read_only=True) as connection:
        validate_contract(connection)
        races = _rows(
            connection,
            """
            select
                replay.season,
                replay.round,
                races.race_name,
                races.race_date,
                races.circuit_name,
                races.country,
                count(*) as position_rows,
                count(distinct replay.driver_code) as driver_count,
                max(replay.t_s) as duration_s
            from marts.race_replay replay
            join staging.stg_races races using (season, round)
            group by all
            having count(*) > 0
            order by replay.season desc, replay.round desc
            """,
            [],
        )
        if not races:
            raise ValueError("The snapshot contains no race replay data")

        staging = output.with_name(f".{output.name}-staging")
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        for race in races:
            season = int(race["season"])
            round_number = int(race["round"])
            race_dir = staging / "races" / f"{season}-{round_number:02d}"
            race_dir.mkdir(parents=True)
            row_count = _export_positions(
                connection, season, round_number, race_dir / "positions.arrow"
            )
            bundle = _race_bundle(connection, season, round_number)
            _write_json(race_dir / "bundle.json", bundle)
            race["position_rows"] = row_count
            race["race_control_count"] = len(bundle["race_control"])
            race["overtake_count"] = len(bundle["overtakes"])
            race["radio_count"] = len(bundle["radio"])
            race["pre_race_radio_count"] = sum(
                row["phase"] == "pre-race" for row in bundle["radio"]
            )
            race["race_radio_count"] = sum(row["phase"] == "race" for row in bundle["radio"])
            race["post_race_radio_count"] = sum(
                row["phase"] == "post-race" for row in bundle["radio"]
            )
            race["key"] = f"{season}-{round_number:02d}"
            race["bundle_url"] = f"races/{race['key']}/bundle.json"
            race["positions_url"] = f"races/{race['key']}/positions.arrow"

    representative = next(
        (race for race in races if race["radio_count"] and race["overtake_count"]),
        races[0],
    )
    manifest = {
        "schema_version": 1,
        "snapshot": {
            "version": source_manifest.get("version"),
            "generated_at": source_manifest.get("generated_at"),
            "sha256": source_manifest.get("sha256"),
        },
        "default_race": representative["key"],
        "races": races,
    }
    _write_json(staging / "manifest.json", manifest)
    if output.exists():
        shutil.rmtree(output)
    shutil.move(str(staging), str(output))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=Path("data/dashboard/latest.duckdb"))
    parser.add_argument("--output", type=Path, default=Path("web/static/data"))
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    manifest_path = args.manifest or args.snapshot.with_suffix(".json")
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Snapshot manifest not found: {manifest_path}")
    manifest = export_web_data(
        args.snapshot,
        args.output,
        snapshot_manifest=manifest_path,
    )
    print(
        json.dumps(
            {
                "races": len(manifest["races"]),
                "default_race": manifest["default_race"],
                "snapshot": manifest["snapshot"]["version"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
