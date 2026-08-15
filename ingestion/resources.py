"""Declarative registry of Jolpica/Ergast resources and their flatteners.

Each :class:`Resource` knows how to page its endpoint and how to flatten the
nested JSON into flat rows (one dict per record) suitable for a DataFrame. The
Milestone-1 set is season-scoped and covers what the driver-rating marts need:
schedule, race results, and qualifying results.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

# A flattener takes one envelope record (e.g. a Race) and yields flat rows.
Flattener = Callable[[dict[str, Any], int], Iterator[dict[str, Any]]]


@dataclass(frozen=True)
class Resource:
    """A single Ergast/Jolpica resource that can be backfilled per season."""

    name: str
    path_template: str  # formatted with {season}
    table_key: str
    list_key: str
    flatten: Flattener


def _circuit_fields(race: dict[str, Any]) -> dict[str, Any]:
    circuit = race.get("Circuit", {})
    loc = circuit.get("Location", {})
    return {
        "circuit_id": circuit.get("circuitId"),
        "circuit_name": circuit.get("circuitName"),
        "country": loc.get("country"),
        "locality": loc.get("locality"),
        "lat": loc.get("lat"),
        "long": loc.get("long"),
    }


def _race_key(race: dict[str, Any]) -> dict[str, Any]:
    return {
        "season": int(race["season"]),
        "round": int(race["round"]),
        "race_name": race.get("raceName"),
        "date": race.get("date"),
    }


def _flatten_races(race: dict[str, Any], _season: int) -> Iterator[dict[str, Any]]:
    yield {**_race_key(race), "time": race.get("time"), **_circuit_fields(race)}


def _flatten_results(race: dict[str, Any], _season: int) -> Iterator[dict[str, Any]]:
    base = _race_key(race)
    for res in race.get("Results", []):
        driver = res.get("Driver", {})
        constr = res.get("Constructor", {})
        time = res.get("Time", {})
        flap = res.get("FastestLap", {})
        yield {
            **base,
            "driver_id": driver.get("driverId"),
            "driver_code": driver.get("code"),
            "driver_number": res.get("number"),
            "driver_given_name": driver.get("givenName"),
            "driver_family_name": driver.get("familyName"),
            "driver_nationality": driver.get("nationality"),
            "constructor_id": constr.get("constructorId"),
            "grid": _to_int(res.get("grid")),
            "position": _to_int(res.get("position")),
            "position_text": res.get("positionText"),
            "points": _to_float(res.get("points")),
            "laps": _to_int(res.get("laps")),
            "status": res.get("status"),
            "time_millis": _to_int(time.get("millis")),
            "time_text": time.get("time"),
            "fastest_lap_rank": _to_int(flap.get("rank")),
            "fastest_lap_time": flap.get("Time", {}).get("time"),
        }


def _flatten_qualifying(race: dict[str, Any], _season: int) -> Iterator[dict[str, Any]]:
    base = _race_key(race)
    for q in race.get("QualifyingResults", []):
        driver = q.get("Driver", {})
        constr = q.get("Constructor", {})
        yield {
            **base,
            "driver_id": driver.get("driverId"),
            "driver_code": driver.get("code"),
            "constructor_id": constr.get("constructorId"),
            "position": _to_int(q.get("position")),
            "q1": q.get("Q1"),
            "q2": q.get("Q2"),
            "q3": q.get("Q3"),
        }


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# Registry -------------------------------------------------------------------
RESOURCES: dict[str, Resource] = {
    "races": Resource(
        name="races",
        path_template="{season}",
        table_key="RaceTable",
        list_key="Races",
        flatten=_flatten_races,
    ),
    "results": Resource(
        name="results",
        path_template="{season}/results",
        table_key="RaceTable",
        list_key="Races",
        flatten=_flatten_results,
    ),
    "qualifying": Resource(
        name="qualifying",
        path_template="{season}/qualifying",
        table_key="RaceTable",
        list_key="Races",
        flatten=_flatten_qualifying,
    ),
}

DEFAULT_RESOURCES: tuple[str, ...] = ("races", "results", "qualifying")
