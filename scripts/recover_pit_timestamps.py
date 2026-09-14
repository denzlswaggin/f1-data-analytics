"""Capture and reconcile FastF1 pit timestamps without modifying published data."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any

import duckdb
from analytics.pit_recovery import TIMESTAMPS, recover_pit_timestamps
from ingestion.clients.fastf1_client import FastF1Client


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def capture(snapshot: Path, output: Path, *, source_capture: Path | None = None) -> dict[str, Any]:
    # Never overwrite a previous capture, including an interrupted one.
    output.mkdir(parents=True, exist_ok=False)
    baseline_hash = sha256(snapshot)
    with duckdb.connect(str(snapshot), read_only=True) as connection:
        baseline = connection.execute("select * from staging.stg_laps where session = 'R'").df()
    if sha256(snapshot) != baseline_hash:
        raise ValueError("Snapshot changed while reading the baseline")
    report: dict[str, Any] = {
        "schema_version": 1,
        "baseline_sha256": baseline_hash,
        "provider": "FastF1",
        "provider_version": version("fastf1"),
        "started_at": datetime.now(UTC).isoformat(),
        "complete": False,
        "races": [],
    }
    frozen = None
    if source_capture is not None:
        manifest = source_capture / "manifest.json"
        frozen = json.loads(manifest.read_text(encoding="utf-8"))
        if frozen["baseline_sha256"] != baseline_hash or not frozen["complete"]:
            raise ValueError("Source capture must be complete and match the baseline")
        report["source_capture_sha256"] = sha256(manifest)
        report["provider_version"] = frozen["provider_version"]

    def write_report() -> None:
        (output / "manifest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    write_report()
    client = FastF1Client()
    for (season, rnd), old in baseline.groupby(["season", "round"], sort=True):
        season, rnd = int(season), int(rnd)
        item: dict[str, Any] = {"season": season, "round": rnd, "baseline_laps": len(old)}
        try:
            donor_path = output / f"{season}-{rnd:02}-source.parquet"
            if frozen is None:
                donor = client.load_session_laps(season, rnd)
                item["retrieved_at"] = datetime.now(UTC).isoformat()
                donor.to_parquet(donor_path, index=False)
            else:
                import pandas as pd

                records = [r for r in frozen["races"] if (r["season"], r["round"]) == (season, rnd)]
                if len(records) != 1:
                    raise ValueError("Source capture scope missing or duplicated")
                record = records[0]
                if record["source_file"] != donor_path.name:
                    raise ValueError("Unexpected source filename")
                assert source_capture is not None
                shutil.copyfile(source_capture / donor_path.name, donor_path)
                if sha256(donor_path) != record["source_sha256"]:
                    raise ValueError("Source capture hash mismatch")
                donor = pd.read_parquet(donor_path)
                item["retrieved_at"] = record["retrieved_at"]
            item["source_file"] = donor_path.name
            item["source_sha256"] = sha256(donor_path)
            reconciled = recover_pit_timestamps(old, donor)
            candidate_path = output / f"{season}-{rnd:02}-reconciled.parquet"
            reconciled.to_parquet(candidate_path, index=False)
            item["candidate_file"] = candidate_path.name
            item["candidate_sha256"] = sha256(candidate_path)
            item["filled"] = {
                name: int((old[name].isna() & reconciled[name].notna()).sum())
                for name in TIMESTAMPS
            }
            item["status"] = "reconciled"
        except Exception as exc:
            # Keep the donor and diagnostics; never force a mismatched scope.
            item["status"] = "rejected"
            item["error"] = f"{type(exc).__name__}: {exc}"
        report["races"].append(item)
        write_report()
        print(f"{season} R{rnd:02}: {item['status']}", flush=True)
    report["complete"] = True
    report["finished_at"] = datetime.now(UTC).isoformat()
    write_report()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-capture", type=Path, help="reconcile a frozen capture offline")
    args = parser.parse_args()
    report = capture(args.snapshot, args.output, source_capture=args.source_capture)
    if any(race["status"] != "reconciled" for race in report["races"]):
        raise SystemExit("Some races were rejected; inspect the manifest before any publication")


if __name__ == "__main__":
    main()
