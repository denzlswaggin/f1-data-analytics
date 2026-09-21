"""Read-only current coverage and dated validation for the audit corrections."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
from scripts.check_metric_evidence import check as check_metrics
from scripts.check_robust_estimates import check as check_robustness

ROOT = Path(__file__).resolve().parents[1]
VERSION = "audit-evidence-v1"


def records(connection: duckdb.DuckDBPyConnection, query: str) -> list[dict[str, Any]]:
    result = connection.execute(query)
    names = [column[0] for column in result.description]
    return [dict(zip(names, row, strict=True)) for row in result.fetchall()]


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verified_manifest(snapshot: Path) -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads(snapshot.with_suffix(".json").read_text())
    if checksum(snapshot) != manifest.get("sha256"):
        raise ValueError("Snapshot checksum does not match its manifest")
    return manifest


# Denominators deliberately stay metric-specific: no aggregate trust score.
METRICS = [
    (
        "Career ratings",
        "marts.driver_ratings",
        "n_comparisons>=40",
        "drivers",
        "null",
        "Career display minimum; model intervals do not establish exact rank certainty.",
    ),
    (
        "Clean-air pace",
        "marts.traffic_adjusted_pace",
        "clean_air_eligible",
        "driver-races",
        "season,round",
        "Car, tyre age and race context remain in the comparison.",
    ),
    (
        "Traffic association",
        "marts.traffic_adjusted_pace",
        "traffic_association_eligible",
        "driver-races",
        "season,round",
        "Matched association, not a causal traffic cost.",
    ),
    (
        "Pace consistency",
        "marts.pace_consistency",
        "consistency_eligible",
        "driver-races",
        "season,round",
        "Unexplained residual time is not necessarily driver error.",
    ),
    (
        "Driver DNA",
        "marts.driver_dna_evidence",
        "eligible",
        "unique teammate/race pairs",
        "season,round",
        "Selected fast teammate laps; not a full-race technique census.",
    ),
    (
        "Track Fit",
        "marts.driver_track_fit",
        "interval_eligible",
        "driver/archetype groups",
        "null",
        "At least five races; selected teammate laps, not future circuit predictions.",
    ),
    (
        "Pit windows",
        "marts.pit_window_effectiveness",
        "eligible",
        "pairwise windows",
        "season,round",
        "Observed cycle swing includes tyre, traffic and pit-lane effects.",
    ),
    (
        "Pit timing",
        "marts.pit_timing_sensitivity",
        "eligible",
        "stop transitions",
        "season,round",
        "Retrospective scenarios; boundary minima do not identify an optimum.",
    ),
    (
        "Tyre warmup",
        "marts.tyre_warmup",
        "time_to_pace_laps is not null and confirmation_history_complete",
        "stints",
        "season,round",
        "Exact confirmation requires complete history; censored and unknown cases stay separate.",
    ),
    (
        "Racecraft",
        "marts.racecraft_battles",
        "eligible",
        "battle episodes",
        "season,round",
        "Selected resolved episodes; independent event accuracy remains unverified.",
    ),
]


def evidence_summary(connection: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    output = []
    for label, table, eligible, unit, race_key, limitation in METRICS:
        where = " where driver_code < teammate_code" if label == "Driver DNA" else ""
        race_count = "null" if race_key == "null" else f"count(distinct ({race_key}))"
        row = records(
            connection,
            f"""select count(*) as candidates,
            count(*) filter(where {eligible}) as eligible,
            {race_count} as races from {table}{where}""",
        )[0]
        if label == "Pit timing":
            n = connection.execute(
                f"select count(*) from {table} where eligible and boundary_minimum"
            ).fetchall()[0][0]
            limitation = f"{n} eligible boundary minima. " + limitation
        if label == "Tyre warmup":
            n = connection.execute(f"select count(*) from {table} where right_censored").fetchall()[
                0
            ][0]
            limitation = f"{n} right-censored stints. " + limitation
        output.append(
            {
                "analysis": label,
                **row,
                "unit": unit,
                "limitation": limitation,
                "validation_status": "Not evaluated for this snapshot",
            }
        )
    return output


def dataset_statistics(connection: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    output = []
    for label, table in (
        ("Lap timing", "marts.mart_lap_times"),
        ("Telemetry", "marts.mart_lap_telemetry"),
        ("Replay", "marts.race_replay"),
    ):
        row = records(
            connection,
            f"select count(*) as observations, count(distinct (season,round)) as races from {table}",
        )[0]
        output.append({"dataset": label, **row})
    return output


def historical_validation(root: Path, snapshot_sha256: str) -> list[dict[str, Any]]:
    """Read frozen reports without relabelling old evaluations as current evidence."""
    output = []
    for filename, kind in (
        ("temporal-production.json", "Predictive diagnostic"),
        ("reference-results.json", "Source agreement"),
    ):
        path = root / "validation/dashboard-audit-20260918" / filename
        report = json.loads(path.read_text()) if path.exists() else {}
        matches = (
            bool(report.get("snapshot_sha256")) and report["snapshot_sha256"] == snapshot_sha256
        )
        metadata = report.get("snapshot_metadata") or []
        if not report:
            result = "Evaluation artifact unavailable"
        elif kind == "Predictive diagnostic":
            result = (
                f"Model MAE {report['model_mae_sec']:.3f} s; constant baseline "
                f"{report['baseline_mae_sec']:.3f} s; {report['evaluated_stints']} stints."
            )
        else:
            result = (
                f"{report['exact_positive_matches']} exact positive matches in "
                f"{report['annotated_cases']} selected reference cases; not population accuracy."
            )
        output.append(
            {
                "evidence_type": kind,
                "status": "Evaluated on this snapshot"
                if matches
                else "Not evaluated for this snapshot",
                "report_date": "2026-09-18" if report else None,
                "evaluated_snapshot": metadata[0][0] if metadata else None,
                "evaluated_sha256": report.get("snapshot_sha256"),
                "result": result,
                "scope": "Pit-timing fitting component"
                if kind == "Predictive diagnostic"
                else "Selected racecraft references",
            }
        )
    pending = root / "validation/racecraft-review-v1/score-pending.json"
    review = json.loads(pending.read_text()) if pending.exists() else {}
    output.append(
        {
            "evidence_type": "Independent review",
            "status": "Not evaluated for this snapshot",
            "report_date": "2026-09-14" if review else None,
            "evaluated_snapshot": None,
            "evaluated_sha256": None,
            "result": f"{review['scored_windows']} of {review['total_windows']} prepared windows scored in the frozen review batch."
            if review
            else "Review artifact unavailable",
            "scope": "Historical footage-review batch; no current population accuracy estimate",
        }
    )
    return output


def structural_validation(
    connection: duckdb.DuckDBPyConnection, manifest: dict[str, Any]
) -> dict[str, Any]:
    checks = {**check_metrics(connection), **check_robustness(connection)}
    if any(checks.values()):
        raise ValueError(f"Evidence publication checks failed: {checks}")
    return {
        "evidence_type": "Structural checks",
        "status": "Passed on this snapshot",
        "report_date": datetime.now(UTC).isoformat(),
        "evaluated_snapshot": manifest["version"],
        "evaluated_sha256": manifest["sha256"],
        "result": f"{len(checks)} metric and robustness checks; zero violations.",
        "scope": "Traffic, tyre observation and pit-scenario publication rules; not predictive accuracy",
    }


def readme_statistics(artifact: Path) -> str:
    with duckdb.connect() as connection:
        payload, version = connection.execute(
            "select payload,snapshot_version from read_parquet(?) where dataset='dataset_statistics'",
            [str(artifact)],
        ).fetchall()[0]
    rows = json.loads(payload)
    lines = [
        f"Published snapshot: `{version}`.",
        "",
        "| Dataset | Observations | Races |",
        "| --- | ---: | ---: |",
    ]
    lines.extend(
        f"| {row['dataset']} | {row['observations']:,} | {row['races']:,} |" for row in rows
    )
    return "\n".join(lines)


def update_readme(artifact: Path, readme: Path) -> None:
    start, end = "<!-- audit-statistics:start -->", "<!-- audit-statistics:end -->"
    text = readme.read_text()
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError("README statistics markers are missing or ambiguous")
    before, rest = text.split(start)
    _, after = rest.split(end)
    readme.write_text(before + start + "\n" + readme_statistics(artifact) + "\n" + end + after)


def export(snapshot: Path, output: Path) -> dict[str, Any]:
    manifest = verified_manifest(snapshot)
    with duckdb.connect(str(snapshot), read_only=True) as connection:
        version = connection.execute("select version from dashboard.snapshot_metadata").fetchall()[
            0
        ][0]
        if version != manifest.get("version"):
            raise ValueError("Snapshot version does not match its manifest")
        datasets = {
            "evidence_summary": evidence_summary(connection),
            "dataset_statistics": dataset_statistics(connection),
            "validation_evidence": [
                structural_validation(connection, manifest),
                *historical_validation(ROOT, manifest["sha256"]),
            ],
        }
    # Detect replacement during export before publishing any new artifact.
    if verified_manifest(snapshot) != manifest:
        raise ValueError("Snapshot changed during evidence export")
    output.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(dir=output.parent, suffix=".parquet")
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        with duckdb.connect() as target:
            target.execute(
                "create table evidence(dataset varchar, payload varchar, snapshot_version varchar, snapshot_sha256 varchar, methodology_version varchar)"
            )
            target.executemany(
                "insert into evidence values (?,?,?,?,?)",
                [
                    (name, json.dumps(rows, allow_nan=False), version, manifest["sha256"], VERSION)
                    for name, rows in datasets.items()
                ],
            )
            target.execute("copy evidence to ? (format parquet)", [str(temporary)])
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "snapshot_version": version,
        "snapshot_sha256": manifest["sha256"],
        "datasets": {key: len(value) for key, value in datasets.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=ROOT / "data/dashboard/latest.duckdb")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "data/dashboard/audit-evidence.parquet"
    )
    parser.add_argument(
        "--update-readme",
        action="store_true",
        help="Explicitly refresh the README statistics block",
    )
    args = parser.parse_args()
    print(json.dumps(export(args.snapshot, args.output), indent=2))
    if args.update_readme:
        update_readme(args.output, ROOT / "README.md")


if __name__ == "__main__":
    main()
