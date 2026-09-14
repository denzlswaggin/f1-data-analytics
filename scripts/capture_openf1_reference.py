"""Freeze public historical OpenF1 responses for a separate feed comparison.

These are source observations, not independently adjudicated ground truth.
The command neither authenticates nor modifies production data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://api.openf1.org/v1"


def capture(
    session_key: int,
    drivers: list[int],
    output: Path,
    *,
    include_intervals: bool = False,
    full_field: bool = False,
) -> dict[str, Any]:
    if session_key < 1 or (
        not full_field and (len(drivers) != 2 or len(set(drivers)) != 2 or min(drivers) < 1)
    ):
        raise ValueError("A session and two distinct driver numbers are required")
    if full_field and drivers:
        raise ValueError("Full-field capture derives its roster from the source")
    output.mkdir(parents=True, exist_ok=False)
    queries = [
        ("sessions", {"session_key": session_key}),
        ("overtakes", {"session_key": session_key}),
    ]
    queries.extend(
        (endpoint, {"session_key": session_key, "driver_number": driver})
        for endpoint in (
            ("position", "laps", "intervals") if include_intervals else ("position", "laps")
        )
        for driver in drivers
    )
    if full_field:
        queries.extend(
            (endpoint, {"session_key": session_key})
            for endpoint in ("drivers", "position", "laps", "intervals")
        )
    files: list[dict[str, Any]] = []
    payloads: dict[str, Any] = {}
    with requests.Session() as client:
        for endpoint, parameters in queries:
            if files:
                time.sleep(1)
            response = client.get(f"{BASE_URL}/{endpoint}", params=parameters, timeout=30)
            response.raise_for_status()
            rows = response.json()
            if not isinstance(rows, list) or any(
                not isinstance(row, dict) or row.get("session_key") != session_key for row in rows
            ):
                raise ValueError(f"Unexpected {endpoint} response; capture remains incomplete")
            driver = parameters.get("driver_number")
            if driver is not None and any(row.get("driver_number") != driver for row in rows):
                raise ValueError(f"Wrong driver in {endpoint} response")
            name = f"{endpoint}{'-' + str(driver) if driver is not None else ''}.json"
            raw = response.content
            (output / name).write_bytes(raw)
            payloads[name] = rows
            files.append(
                {
                    "file": name,
                    "endpoint": endpoint,
                    "parameters": parameters,
                    "url": response.url,
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "http_status": response.status_code,
                    "rows": len(rows),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
    if full_field:
        drivers = [row.get("driver_number") for row in payloads["drivers.json"]]
        if (
            len(drivers) < 2
            or any(type(d) is not int or d < 1 for d in drivers)
            or len(set(drivers)) != len(drivers)
        ):
            raise ValueError("Invalid or duplicate full-field roster")
        for endpoint in ("position", "laps", "intervals"):
            if any(row.get("driver_number") not in drivers for row in payloads[f"{endpoint}.json"]):
                raise ValueError("Observation outside captured roster")
    manifest = {
        "schema_version": 3 if full_field else (2 if include_intervals else 1),
        "session_key": session_key,
        "drivers": drivers,
        "documentation_url": "https://openf1.org/docs/",
        "files": files,
        "limitations": "Historical public API capture, not footage truth. OpenF1 may share underlying F1 timing with FastF1. Position observations can be delayed or incomplete; overtakes include pit-cycle and penalty changes and may be incomplete. Empty responses are not proof of no event.",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=int, required=True)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--drivers", type=int, nargs=2)
    scope.add_argument("--full-field", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-intervals", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            capture(
                args.session,
                args.drivers or [],
                args.output,
                include_intervals=args.include_intervals,
                full_field=args.full_field,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
