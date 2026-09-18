"""Build or fetch an immutable dashboard snapshot."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ingestion.dashboard_snapshot import build_dashboard_snapshot, fetch_dashboard_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="export the configured warehouse")
    build.add_argument("--output-dir", type=Path, default=Path("data/dashboard"))
    build.add_argument("--version")
    build.add_argument("--publish-uri")
    build.add_argument("--coverage-exceptions", type=Path,
                       help="JSON list of explicit table/season/round/reason exceptions")

    fetch = subparsers.add_parser("fetch", help="install the latest published snapshot")
    fetch.add_argument("--uri", required=True)
    fetch.add_argument("--output", type=Path, default=Path("data/dashboard/latest.duckdb"))

    args = parser.parse_args()
    if args.command == "build":
        manifest = build_dashboard_snapshot(
            args.output_dir, version=args.version, publish_uri=args.publish_uri,
            coverage_exceptions=(json.loads(args.coverage_exceptions.read_text())
                                 if args.coverage_exceptions else None),
        )
    else:
        manifest = fetch_dashboard_snapshot(args.uri, args.output)
    print(json.dumps(asdict(manifest), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
