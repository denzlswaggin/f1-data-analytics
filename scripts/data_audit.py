#!/usr/bin/env python3
"""Audit dashboard data provenance, integrity, coverage and freshness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ingestion.data_audit import audit_dashboard_data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "snapshot",
        nargs="?",
        type=Path,
        default=Path("data/dashboard/latest.duckdb"),
    )
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--lake-dir", type=Path, default=Path("data/lake"))
    parser.add_argument("--json", action="store_true", help="Print the complete JSON report")
    parser.add_argument("--skip-checksum", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on failed checks")
    args = parser.parse_args()

    report = audit_dashboard_data(
        args.snapshot,
        manifest_path=args.manifest,
        lake_dir=args.lake_dir,
        verify_checksum=not args.skip_checksum,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Data audit: {report['status'].upper()} — {report['snapshot']}")
        for finding in report["findings"]:
            print(f"[{finding['status'].upper():4}] {finding['check']}: {finding['detail']}")
        print(
            f"Tables: {len(report.get('table_rows', {}))}; "
            f"methodologies: {len(report.get('methodology_versions', {}))}; "
            f"lake parquet files: {report.get('lake', {}).get('files', 0)}"
        )
    if args.strict and report["status"] == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
