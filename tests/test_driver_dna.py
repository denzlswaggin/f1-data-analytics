from __future__ import annotations

import duckdb
import numpy as np
import pandas as pd
import pytest
from analytics.driver_dna import (
    METRICS,
    analyse_driver_dna,
    bootstrap_profile,
    build_microsectors,
    build_profiles,
    clean_telemetry,
    confirmed_brake_onsets,
    distance_weighted_share,
    integrate_segment_time,
    validate_driver_dna,
)
from analytics.pipeline import build_driver_dna, build_driver_dna_incremental
from ingestion.config import Settings


def _telemetry(driver: str, *, season: int = 2025, rnd: int = 1) -> pd.DataFrame:
    distance = np.arange(0.0, 3025.0, 25.0)
    brake = (((distance >= 500) & (distance <= 575)) | ((distance >= 1800) & (distance <= 1875)))
    phase = 0.0 if driver == "AAA" else 0.3
    return pd.DataFrame(
        {
            "season": season,
            "round": rnd,
            "driver_code": driver,
            "lap_number": 10 if driver == "AAA" else 12,
            "distance_m": distance,
            "speed_kph": 220 + 80 * np.sin(distance / 350 + phase),
            "throttle": np.where(brake, 0, 100 if driver == "AAA" else 96),
            "brake": brake.astype(int),
            "gear": 7,
            "x": np.cos(distance / 450) * 1000,
            "y": np.sin(distance / 450) * 1000,
        }
    )


def _laps(**overrides: object) -> pd.DataFrame:
    rows = [
        {
            "season": 2025,
            "round": 1,
            "session": "R",
            "race_name": "Test Grand Prix",
            "driver_code": "AAA",
            "driver_name": "Driver A",
            "team": "Test Team",
            "lap_number": 10,
            "compound": "MEDIUM",
            "tyre_life": 8,
            "track_status": "1",
            "lap_time_sec": 90.0,
        },
        {
            "season": 2025,
            "round": 1,
            "session": "R",
            "race_name": "Test Grand Prix",
            "driver_code": "BBB",
            "driver_name": "Driver B",
            "team": "Test Team",
            "lap_number": 12,
            "compound": "MEDIUM",
            "tyre_life": 10,
            "track_status": "1",
            "lap_time_sec": 90.5,
        },
    ]
    for key, value in overrides.items():
        target, column = key.split("__", maxsplit=1)
        rows[int(target)][column] = value
    return pd.DataFrame(rows)


def test_distance_weighted_share_uses_distance_not_sample_count() -> None:
    share = distance_weighted_share([0, 10, 100], [False, True, False])
    assert share == pytest.approx(0.1)


def test_confirmed_brake_onset_requires_quiet_and_sustained_distance() -> None:
    frame = pd.DataFrame(
        {
            "distance_m": np.arange(0, 225, 25),
            "speed_kph": np.arange(200, 191, -1),
            "throttle": 0,
            "brake": [0, 0, 0, 0, 1, 1, 1, 0, 0],
        }
    )
    onsets = confirmed_brake_onsets(frame)
    assert onsets["distance_m"].tolist() == [100]
    frame.loc[5, "brake"] = 0
    assert confirmed_brake_onsets(frame).empty


def test_microsector_trapezoid_integration_and_sign() -> None:
    assert integrate_segment_time(np.array([0, 100]), np.array([100, 100]))[0] == pytest.approx(
        3.6
    )
    driver = pd.DataFrame(
        {
            "distance_m": [0, 100, 200],
            "speed_kph": [200, 200, 200],
            "throttle": [100, 100, 100],
            "brake": [0, 0, 0],
            "gear": [7, 7, 7],
            "x": [0, 1, 2],
            "y": [0, 1, 0],
        }
    )
    teammate = driver.copy()
    teammate["speed_kph"] = 100
    micro = build_microsectors(driver, teammate)
    assert len(micro) == 1
    assert micro.loc[0, "segment_delta_sec"] == pytest.approx(3.6)


def test_cleaning_clamps_throttle_tracks_gear_and_removes_zero_speed() -> None:
    frame = _telemetry("AAA").iloc[:5].copy()
    frame.loc[0, "throttle"] = 104
    frame.loc[1, "gear"] = 21
    frame.loc[2, "speed_kph"] = 0
    cleaned, audit = clean_telemetry(frame)
    assert cleaned["throttle"].max() == 100
    assert audit["throttle_corrections"] == 1
    assert audit["gear_anomalies"] == 1
    assert len(cleaned) == 4


def test_analysis_is_directed_antisymmetric_and_eligible() -> None:
    telemetry = pd.concat([_telemetry("AAA"), _telemetry("BBB")], ignore_index=True)
    result = analyse_driver_dna(telemetry, _laps(), n_boot=20)
    assert len(result.evidence) == 2
    assert result.evidence["eligible"].all()
    forward, reverse = result.evidence.sort_values("driver_code").to_dict("records")
    for metric in METRICS:
        assert forward[f"{metric}_delta"] == pytest.approx(-reverse[f"{metric}_delta"])
        assert forward[f"{metric}_z"] == pytest.approx(-reverse[f"{metric}_z"])
    assert result.microsectors.groupby("driver_code")["segment_delta_sec"].sum().sum() == pytest.approx(
        0
    )


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"1__compound": None}, "missing compound"),
        ({"1__compound": "WET"}, "non-dry compound"),
        ({"1__compound": "SOFT"}, "different compound"),
        ({"1__track_status": "4"}, "non-green track status"),
        ({"1__lap_number": 30}, "lap-number gap above 10"),
        ({"1__tyre_life": 30}, "tyre-life gap above 10"),
    ],
)
def test_eligibility_exclusions(overrides: dict[str, object], reason: str) -> None:
    telemetry = pd.concat([_telemetry("AAA"), _telemetry("BBB")], ignore_index=True)
    if "1__lap_number" in overrides:
        telemetry.loc[telemetry["driver_code"] == "BBB", "lap_number"] = overrides[
            "1__lap_number"
        ]
    result = analyse_driver_dna(telemetry, _laps(**overrides), n_boot=10)
    assert not result.evidence["eligible"].any()
    assert set(result.evidence["exclusion_reason"]) == {reason}


def test_incomplete_common_distance_is_rejected() -> None:
    telemetry = pd.concat(
        [_telemetry("AAA"), _telemetry("BBB").iloc[:90]], ignore_index=True
    )
    result = analyse_driver_dna(telemetry, _laps(), n_boot=10)
    assert set(result.evidence["exclusion_reason"]) == {
        "fewer than 100 common telemetry points"
    }


def test_bootstrap_is_deterministic_and_profiles_require_five_comparisons() -> None:
    rows = []
    for rnd in range(1, 6):
        row = {
            "season": 2025,
            "round": rnd,
            "driver_code": "AAA",
            "driver_name": "Driver A",
            "teammate_code": "BBB",
            "eligible": True,
        }
        row.update({f"{metric}_z": rnd / 10 for metric in METRICS})
        rows.append(row)
    evidence = pd.DataFrame(rows)
    first = bootstrap_profile(evidence, n_boot=100, seed=12)
    second = bootstrap_profile(evidence, n_boot=100, seed=12)
    assert first == second
    assert build_profiles(evidence.iloc[:4], n_boot=10).empty
    profile = build_profiles(evidence, n_boot=100, seed=12)
    assert len(profile) == 1
    assert profile.loc[0, "confidence"] == "limited"


def test_incremental_refresh_replaces_one_race_and_preserves_others(tmp_path) -> None:
    database = tmp_path / "driver-dna.duckdb"
    telemetry = pd.concat(
        [
            _telemetry(driver, rnd=rnd)
            for rnd in (1, 2)
            for driver in ("AAA", "BBB")
        ],
        ignore_index=True,
    )
    laps = pd.concat(
        [_laps().assign(round=rnd, race_name=f"Race {rnd}") for rnd in (1, 2)],
        ignore_index=True,
    )
    races = laps[["season", "round", "race_name"]].drop_duplicates()
    codes = laps[["season", "driver_code", "driver_name"]].drop_duplicates()
    with duckdb.connect(str(database)) as connection:
        connection.execute("create schema marts")
        connection.execute("create schema staging")
        for name, frame in (
            ("telemetry", telemetry),
            ("laps", laps),
            ("races", races),
            ("codes", codes),
        ):
            connection.register(name, frame)
        connection.execute("create table marts.mart_lap_telemetry as select * from telemetry")
        connection.execute("create table staging.stg_laps as select * from laps")
        connection.execute("create table staging.stg_races as select * from races")
        connection.execute("create table staging.stg_driver_codes as select * from codes")
    settings = Settings(warehouse="duckdb", duckdb_path=database)
    initial = build_driver_dna(2025, settings=settings, n_boot=10)
    untouched = initial.evidence[initial.evidence["round"] == 2][
        ["driver_code", *[f"{metric}_delta" for metric in METRICS]]
    ].reset_index(drop=True)

    with duckdb.connect(str(database)) as connection:
        connection.execute(
            "update marts.mart_lap_telemetry set speed_kph = speed_kph + 5 "
            "where round = 1 and driver_code = 'AAA'"
        )
    refreshed = build_driver_dna_incremental(2025, 1, settings=settings, n_boot=10)

    assert set(refreshed.evidence["round"]) == {1}
    with duckdb.connect(str(database), read_only=True) as connection:
        persisted = connection.execute(
            "select * from marts.driver_dna_evidence order by round, driver_code"
        ).fetchdf()
        micro_rounds = connection.execute(
            "select distinct round from marts.driver_dna_microsectors order by round"
        ).fetchdf()["round"].tolist()
    after_untouched = persisted[persisted["round"] == 2][untouched.columns].reset_index(drop=True)
    pd.testing.assert_frame_equal(after_untouched, untouched, check_dtype=False)
    assert set(persisted["round"]) == {1, 2}
    assert micro_rounds == [1, 2]


def test_publication_validation_rejects_non_finite_eligible_metric() -> None:
    telemetry = pd.concat([_telemetry("AAA"), _telemetry("BBB")], ignore_index=True)
    result = analyse_driver_dna(telemetry, _laps(), n_boot=10)
    result.evidence.loc[0, "low_speed_kph_delta"] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        validate_driver_dna(result)
