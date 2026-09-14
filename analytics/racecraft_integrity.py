"""Reproducibility receipts for Racecraft, not certificates of event accuracy."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from numbers import Number

import duckdb
import pandas as pd

RECEIPT_VERSION = "racecraft-inputs-v2-observed-persistence"
INPUT_TABLES = {
    "replay": "marts.race_replay",
    "laps": "staging.stg_laps",
    "pit_context": "marts.pit_lap_context",
}
OUTPUT_TABLES = {
    "overtakes": "marts.race_overtakes",
    "battles": "marts.racecraft_battles",
    "summary": "marts.racecraft_driver_summary",
}
RECEIPT_COLUMNS = {
    "season",
    "round",
    "receipt_version",
    "overtake_parameters",
    "methodology_version",
    "processed_at",
    "replay_rows",
    "overtake_rows",
    "battle_rows",
    *(f"{name}_sha256" for name in (*INPUT_TABLES, *OUTPUT_TABLES)),
}


def fingerprint(frame: pd.DataFrame) -> str:
    """Hash values and columns independent of row order and nullable storage types.

    JSON normalises missing values. Floats use 15 decimal places, matching the
    precision of the timing/position data; this is an integrity check, not a
    cryptographic signature or evidence of real-world accuracy.
    """
    normal = frame.reindex(sorted(frame.columns), axis=1).copy()
    for name in normal:
        numeric = pd.api.types.is_numeric_dtype(normal[name]) and not pd.api.types.is_bool_dtype(
            normal[name]
        )
        if normal[name].dtype == object:
            present = normal[name].dropna()
            numeric = (
                not present.empty
                and present.map(
                    lambda value: isinstance(value, Number) and not isinstance(value, bool)
                ).all()
            )
        if numeric:
            normal[name] = pd.to_numeric(normal[name]).astype("float64")
    normal = normal.sort_values(list(normal.columns), na_position="last").reset_index(drop=True)
    payload = normal.to_json(orient="split", index=False, double_precision=15, date_format="iso")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def partition_query(table: str, season: int, rnd: int) -> str:
    session = " and session = 'R'" if table == "staging.stg_laps" else ""
    return f"select * from {table} where season = {int(season)} and round = {int(rnd)}{session}"


def receipt(
    season: int,
    rnd: int,
    frames: Mapping[str, pd.DataFrame],
    parameters: Mapping[str, float],
    methodology: str,
) -> pd.DataFrame:
    row: dict[str, object] = {
        "season": season,
        "round": rnd,
        "receipt_version": RECEIPT_VERSION,
        "overtake_parameters": json.dumps(dict(parameters), sort_keys=True),
        "methodology_version": methodology,
        "processed_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "replay_rows": len(frames["replay"]),
        "overtake_rows": len(frames["overtakes"]),
        "battle_rows": len(frames["battles"]),
    }
    row.update(
        {f"{name}_sha256": fingerprint(frames[name]) for name in (*INPUT_TABLES, *OUTPUT_TABLES)}
    )
    return pd.DataFrame([row])


def validate_processing(read: Callable[[str], pd.DataFrame]) -> None:
    """Fail closed for absent, duplicate, stale or partially replaced results.

    Zero detected events is valid only with a matching processing receipt.
    Recomputing detector accuracy is deliberately a separate validation task.
    """
    records = read("select * from marts.racecraft_processing")
    expected = read("select distinct season, round from marts.race_replay")
    actual = set(zip(records["season"], records["round"], strict=True))
    required = set(zip(expected["season"], expected["round"], strict=True))
    if records.duplicated(["season", "round"]).any() or actual != required:
        raise ValueError(
            "Racecraft processing coverage mismatch; rerun analytics.cli racecraft --all"
        )
    for table in OUTPUT_TABLES.values():
        scopes = read(f"select distinct season, round from {table}")
        if not set(zip(scopes["season"], scopes["round"], strict=True)).issubset(required):
            raise ValueError(f"Racecraft output has unprocessed partitions: {table}")
    for record in records.to_dict("records"):
        season, rnd = int(record["season"]), int(record["round"])
        if record["receipt_version"] != RECEIPT_VERSION:
            raise ValueError(f"Unsupported Racecraft receipt: {season}/{rnd}")
        for name, table in {**INPUT_TABLES, **OUTPUT_TABLES}.items():
            frame = read(partition_query(table, season, rnd))
            if fingerprint(frame) != record[f"{name}_sha256"]:
                raise ValueError(
                    f"Stale Racecraft {name} for {season}/{rnd}; "
                    "rerun analytics.cli racecraft --all"
                )


def validate_snapshot_processing(connection: duckdb.DuckDBPyConnection) -> None:
    validate_processing(lambda query: connection.execute(query).fetchdf())
