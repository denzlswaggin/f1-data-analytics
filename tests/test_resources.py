"""Unit tests for resource flatteners (offline, fixture-driven)."""

from __future__ import annotations

from ingestion.resources import (
    RESOURCES,
    _flatten_ergast_laps,
    _flatten_pitstops,
)

RACE_WITH_RESULTS = {
    "season": "2023",
    "round": "1",
    "raceName": "Bahrain Grand Prix",
    "date": "2023-03-05",
    "Circuit": {
        "circuitId": "bahrain",
        "circuitName": "Bahrain International Circuit",
        "Location": {
            "lat": "26.0325",
            "long": "50.5106",
            "locality": "Sakhir",
            "country": "Bahrain",
        },
    },
    "Results": [
        {
            "number": "1",
            "position": "1",
            "positionText": "1",
            "points": "25",
            "grid": "1",
            "laps": "57",
            "status": "Finished",
            "Driver": {
                "driverId": "max_verstappen",
                "code": "VER",
                "givenName": "Max",
                "familyName": "Verstappen",
                "nationality": "Dutch",
            },
            "Constructor": {"constructorId": "red_bull"},
            "Time": {"millis": "5637366", "time": "1:33:56.736"},
            "FastestLap": {"rank": "3", "Time": {"time": "1:36.236"}},
        }
    ],
}

RACE_WITH_QUALI = {
    "season": "2023",
    "round": "1",
    "raceName": "Bahrain Grand Prix",
    "date": "2023-03-05",
    "Circuit": {"circuitId": "bahrain", "Location": {}},
    "QualifyingResults": [
        {
            "position": "1",
            "Driver": {"driverId": "max_verstappen", "code": "VER"},
            "Constructor": {"constructorId": "red_bull"},
            "Q1": "1:30.503",
            "Q2": "1:29.914",
            "Q3": "1:29.708",
        }
    ],
}


def test_flatten_results_extracts_typed_fields() -> None:
    rows = list(RESOURCES["results"].flatten(RACE_WITH_RESULTS, 2023))
    assert len(rows) == 1
    row = rows[0]
    assert row["season"] == 2023 and row["round"] == 1
    assert row["driver_id"] == "max_verstappen"
    assert row["driver_given_name"] == "Max"
    assert row["driver_family_name"] == "Verstappen"
    assert row["driver_nationality"] == "Dutch"
    assert row["constructor_id"] == "red_bull"
    assert row["grid"] == 1 and row["position"] == 1
    assert row["points"] == 25.0
    assert row["time_millis"] == 5637366
    assert row["fastest_lap_rank"] == 3


def test_flatten_qualifying_keeps_session_times() -> None:
    rows = list(RESOURCES["qualifying"].flatten(RACE_WITH_QUALI, 2023))
    assert rows[0]["q3"] == "1:29.708"
    assert rows[0]["position"] == 1


def test_flatten_races_pulls_circuit_location() -> None:
    rows = list(RESOURCES["races"].flatten(RACE_WITH_RESULTS, 2023))
    assert rows[0]["circuit_id"] == "bahrain"
    assert rows[0]["country"] == "Bahrain"


def test_missing_numeric_fields_become_none() -> None:
    race = {
        "season": "2023",
        "round": "1",
        "Results": [{"position": "R", "grid": "", "points": "", "Driver": {}, "Constructor": {}}],
    }
    row = next(iter(RESOURCES["results"].flatten(race, 2023)))
    assert row["position"] is None
    assert row["grid"] is None
    assert row["points"] is None


RACE_WITH_PITSTOPS = {
    "season": "2023",
    "round": "1",
    "PitStops": [
        {
            "driverId": "max_verstappen",
            "lap": "14",
            "stop": "1",
            "time": "17:05:23",
            "duration": "22.343",
        },
        {"driverId": "perez", "lap": "17", "stop": "1", "time": "17:09:11", "duration": "1:04.500"},
    ],
}

RACE_WITH_LAPS = {
    "season": "2023",
    "round": "1",
    "Laps": [
        {
            "number": "1",
            "Timings": [
                {"driverId": "max_verstappen", "position": "1", "time": "1:38.001"},
                {"driverId": "perez", "position": "2", "time": "1:38.500"},
            ],
        },
        {
            "number": "2",
            "Timings": [
                {"driverId": "max_verstappen", "position": "1", "time": "1:36.900"},
            ],
        },
    ],
}


def test_flatten_pitstops_one_row_per_stop() -> None:
    rows = list(_flatten_pitstops(RACE_WITH_PITSTOPS, 2023))
    assert len(rows) == 2
    first = rows[0]
    assert first["season"] == 2023 and first["round"] == 1
    assert first["driver_id"] == "max_verstappen"
    assert first["stop"] == 1 and first["lap"] == 14
    assert first["duration"] == "22.343"  # parsed to seconds downstream in dbt


def test_flatten_ergast_laps_expands_timings() -> None:
    rows = list(_flatten_ergast_laps(RACE_WITH_LAPS, 2023))
    assert len(rows) == 3  # 2 timings on lap 1 + 1 on lap 2
    assert rows[0] == {
        "season": 2023,
        "round": 1,
        "driver_id": "max_verstappen",
        "lap": 1,
        "position": 1,
        "lap_time": "1:38.001",
    }
    assert rows[2]["lap"] == 2 and rows[2]["driver_id"] == "max_verstappen"
