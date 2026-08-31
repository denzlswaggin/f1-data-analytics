"""Fail early when the local Evidence snapshot is absent or incompatible."""

from __future__ import annotations

import argparse
from pathlib import Path

from ingestion.dashboard_snapshot import validate_dashboard_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("data/dashboard/latest.duckdb"),
    )
    args = parser.parse_args()

    if not args.path.is_file():
        raise SystemExit(
            f"Dashboard snapshot not found: {args.path}\n"
            "Run `make dashboard-prepare` from the repository root before starting Evidence."
        )

    try:
        latest_event = validate_dashboard_snapshot(args.path)
    except (OSError, ValueError) as exc:
        raise SystemExit(
            f"Dashboard snapshot is incompatible: {exc}\n"
            "Rebuild the analytics marts, then run `make dashboard-prepare`."
        ) from exc

    print(f"PASS dashboard snapshot: {args.path} (latest event: {latest_event or 'unknown'})")


if __name__ == "__main__":
    main()
