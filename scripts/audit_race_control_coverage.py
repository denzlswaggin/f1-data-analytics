"""Audit every dashboard race against its loaded official timing messages.

This verifier intentionally reads the source messages and the published marts
separately.  It proves source-to-mart reconciliation and records limitations;
it does not turn an absent message into proof that an incident never happened.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import duckdb

START_MESSAGES = {
    "VSC DEPLOYED": "VSC",
    "VIRTUAL SAFETY CAR DEPLOYED": "VSC",
    "SAFETY CAR DEPLOYED": "Safety Car",
}
END_MESSAGES = {
    "VSC ENDING": "VSC",
    "VIRTUAL SAFETY CAR ENDING": "VSC",
    "SAFETY CAR IN THIS LAP": "Safety Car",
    "STANDING START": "Red Flag",
    "ROLLING START": "Red Flag",
}


def _normalise(value: object) -> str:
    return " ".join(str(value or "").upper().split())


def _source_marker(message: object, flag: object) -> tuple[str, str] | None:
    normalised_message = _normalise(message)
    normalised_flag = _normalise(flag)
    if normalised_message in START_MESSAGES:
        return START_MESSAGES[normalised_message], "start"
    if (
        normalised_flag == "RED"
        or normalised_message == "RED FLAG"
        or normalised_message.startswith("RED FLAG - RACE SUSPENDED")
    ):
        return "Red Flag", "start"
    if normalised_message in END_MESSAGES:
        return END_MESSAGES[normalised_message], "end"
    return None


def _same_marker(event: dict[str, Any], marker: dict[str, Any], *, boundary: str) -> bool:
    event_time = event[f"{boundary}_t_s"]
    event_lap = event["deployment_lap" if boundary == "start" else "end_lap"]
    return (
        event_time is not None
        and event["event_type"] == marker["event_type"]
        and math.isclose(float(event_time), float(marker["t_s"]), abs_tol=1e-6)
        and (event_lap is None or marker["lap"] is None or int(event_lap) == int(marker["lap"]))
    )


def _hash_source(rows: list[tuple[Any, ...]]) -> str:
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def audit_races(
    connection: duckdb.DuckDBPyConnection, from_season: int, to_season: int
) -> dict[str, Any]:
    races = connection.execute(
        """select distinct results.season, results.round, races.race_name, races.race_date
        from staging.stg_results results
        join staging.stg_races races using(season, round)
        where results.season between ? and ?
        order by results.season, results.round""",
        [from_season, to_season],
    ).fetchall()
    source_rows = connection.execute(
        """with race_windows as (
            select season, round, min(lap_start_sec) as race_start_sec
            from staging.stg_laps where session='R' group by season, round
        )
        select messages.season, messages.round,
            messages.session_time_sec - windows.race_start_sec as t_s,
            messages.lap, messages.category, messages.flag, messages.message,
            messages.message_key
        from staging.stg_race_control messages
        join race_windows windows using(season, round)
        where messages.session='R' and messages.season between ? and ?
        order by messages.season, messages.round, messages.session_time_sec,
            messages.message_key""",
        [from_season, to_season],
    ).fetchall()
    event_columns = [
        row[0] for row in connection.execute("describe marts.race_control_events").fetchall()
    ]
    events = [
        dict(zip(event_columns, row, strict=True))
        for row in connection.execute(
            "select * from marts.race_control_events where season between ? and ? "
            "order by season, round, event_number",
            [from_season, to_season],
        ).fetchall()
    ]
    replay_counts = {
        (int(season), int(rnd)): int(count)
        for season, rnd, count in connection.execute(
            """select season, round, count(*) from marts.race_replay
            where season between ? and ? group by season, round""",
            [from_season, to_season],
        ).fetchall()
    }
    impact_counts = {
        (int(season), int(rnd)): int(count)
        for season, rnd, count in connection.execute(
            """select season, round, count(*) from marts.race_control_impact
            where season between ? and ? group by season, round""",
            [from_season, to_season],
        ).fetchall()
    }

    source_by_race: dict[tuple[int, int], list[tuple[Any, ...]]] = {}
    for row in source_rows:
        source_by_race.setdefault((int(row[0]), int(row[1])), []).append(row)
    events_by_race: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for event in events:
        events_by_race.setdefault((int(event["season"]), int(event["round"])), []).append(event)

    race_results = []
    global_violations = []
    for season, rnd, race_name, race_date in races:
        key = (int(season), int(rnd))
        raw_rows = source_by_race.get(key, [])
        race_events = events_by_race.get(key, [])
        markers = []
        chequered = []
        for row in raw_rows:
            marker = _source_marker(row[6], row[5])
            if marker is not None:
                markers.append(
                    {
                        "event_type": marker[0],
                        "action": marker[1],
                        "t_s": float(row[2]),
                        "lap": int(row[3]) if row[3] is not None else None,
                    }
                )
            if _normalise(row[5]) == "CHEQUERED" or _normalise(row[6]) == "CHEQUERED FLAG":
                chequered.append({"t_s": float(row[2]), "lap": row[3]})
        starts = [marker for marker in markers if marker["action"] == "start"]
        ends = [marker for marker in markers if marker["action"] == "end"]
        unmatched_starts = [
            marker
            for marker in starts
            if not any(_same_marker(event, marker, boundary="start") for event in race_events)
        ]
        unmatched_events = [
            event["event_id"]
            for event in race_events
            if not any(_same_marker(event, marker, boundary="start") for marker in starts)
        ]
        boundary_results = []
        for event in race_events:
            status = str(event["event_status"])
            if status == "complete":
                matched = any(_same_marker(event, marker, boundary="end") for marker in ends)
                source = "explicit_end_message"
            elif status == "interrupted":
                matched = any(
                    event["end_t_s"] is not None
                    and math.isclose(float(event["end_t_s"]), float(marker["t_s"]), abs_tol=1e-6)
                    for marker in starts
                )
                source = "superseding_neutralisation"
            elif status == "finished":
                matched = any(
                    event["end_t_s"] is not None
                    and math.isclose(float(event["end_t_s"]), float(flag["t_s"]), abs_tol=1e-6)
                    for flag in chequered
                )
                source = "chequered_flag"
            else:
                matched = False
                source = "missing_source_end"
            boundary_results.append(
                {
                    "event_id": event["event_id"],
                    "event_type": event["event_type"],
                    "status": status,
                    "start_lap": event["deployment_lap"],
                    "end_lap": event["end_lap"],
                    "end_source": source,
                    "boundary_verified": matched,
                    "limitation": event["exclusion_reason"] or None,
                }
            )
        violations = []
        if not raw_rows:
            violations.append("Missing race-control source partition")
        if any(row[2] is None for row in raw_rows):
            violations.append("Race-control source row has no aligned timestamp")
        if unmatched_starts or unmatched_events or len(starts) != len(race_events):
            violations.append("Source deployment markers do not reconcile with mart events")
        if any(
            not boundary["boundary_verified"] and boundary["status"] != "unclosed"
            for boundary in boundary_results
        ):
            violations.append("Published event boundary does not reconcile with its source marker")
        global_violations.extend(f"{season} R{rnd}: {item}" for item in violations)

        reasons = sorted(
            {str(event["exclusion_reason"]) for event in race_events if event["exclusion_reason"]}
        )
        source_limited = (
            not replay_counts.get(key, 0)
            or any(event["event_status"] == "unclosed" for event in race_events)
            or (bool(race_events) and not impact_counts.get(key, 0))
        )
        components = {
            component: sum(event[f"{component}_status"] != "unavailable" for event in race_events)
            for component in ("position", "gap", "pit", "restart", "tyre")
        }
        if violations:
            status = "failed_reconciliation"
        elif source_limited:
            status = "verified_source_limited"
        elif not race_events:
            status = "verified_no_neutralisation_marker"
        elif any(value < len(race_events) for value in components.values()):
            status = "verified_with_withheld_components"
        else:
            status = "verified_all_components"
        race_results.append(
            {
                "season": int(season),
                "round": int(rnd),
                "race_name": race_name,
                "race_date": str(race_date),
                "verification_status": status,
                "source_message_count": len(raw_rows),
                "source_sha256": _hash_source(raw_rows),
                "source_start_markers": len(starts),
                "modelled_events": len(race_events),
                "replay_rows": replay_counts.get(key, 0),
                "driver_impact_rows": impact_counts.get(key, 0),
                "publishable_event_components": components,
                "limitations": reasons,
                "events": boundary_results,
                "violations": violations,
            }
        )

    status_counts = Counter(race["verification_status"] for race in race_results)
    return {
        "schema_version": 1,
        "scope": {"from_season": from_season, "to_season": to_season},
        "source_basis": (
            "Loaded Formula 1 live-timing race-control messages, independently reconciled "
            "to published event starts and boundary markers."
        ),
        "limitations": (
            "A verified absence means no supported SC, VSC or red-flag deployment marker in "
            "the loaded source partition; it is not independent proof that no incident occurred."
        ),
        "summary": {
            "audited_races": len(race_results),
            "source_races": len(source_by_race),
            "modelled_events": len(events),
            "source_start_markers": sum(race["source_start_markers"] for race in race_results),
            "status_counts": dict(sorted(status_counts.items())),
            "structural_violations": len(global_violations),
            "audit_pass": not global_violations and len(race_results) == len(source_by_race),
        },
        "violations": global_violations,
        "races": race_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, nargs="?", default=Path("data/warehouse/f1.duckdb"))
    parser.add_argument("--from-season", type=int, default=2024)
    parser.add_argument("--to-season", type=int, default=2026)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.from_season > args.to_season:
        parser.error("--from-season must not exceed --to-season")
    with duckdb.connect(str(args.path), read_only=True) as connection:
        result = audit_races(connection, args.from_season, args.to_season)
    rendered = json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if not result["summary"]["audit_pass"]:
        raise SystemExit("FAIL: race-control race audit found structural violations")


if __name__ == "__main__":
    main()
