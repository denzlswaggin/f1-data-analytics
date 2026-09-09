from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb
import pyarrow.ipc as ipc
from scripts.export_web_data import export_web_data


def _snapshot(path: Path) -> None:
    with duckdb.connect(str(path)) as connection:
        connection.execute("create schema marts; create schema staging")
        connection.execute(
            """
            create table marts.race_replay (
                season integer, round integer, driver_code varchar, t_s double,
                x double, y double, running_order integer,
                gap_to_leader_s double, gap_to_ahead_s double
            );
            create table marts.race_overtakes (
                season integer, round integer, t_s double, for_position integer,
                passer_code varchar, passed_code varchar, gap_at_pass_s double,
                confidence double, evidence varchar, reason varchar
            );
            create table staging.stg_laps (
                season integer, round integer, session varchar, driver_code varchar,
                team varchar, lap_number integer, lap_start_sec double, lap_time_sec double,
                stint integer, compound varchar, tyre_life double
            );
            create table staging.stg_results (
                season integer, round integer, driver_code varchar, driver_name varchar,
                grid_position integer, finish_position integer, status varchar,
                is_classified boolean
            );
            create table staging.stg_races (
                season integer, round integer, race_name varchar, race_date date,
                circuit_name varchar, country varchar, locality varchar
            );
            create table staging.stg_race_control (
                season integer, round integer, session varchar, session_time_sec double,
                category varchar, flag varchar, scope varchar, message varchar,
                driver_code varchar
            );
            create table staging.stg_team_radio (
                season integer, round integer, session varchar, session_time_sec double,
                driver_code varchar, recording_url varchar, transcript varchar
            );
            create table staging.stg_weather (
                season integer, round integer, session varchar, time_sec double,
                air_temp double, track_temp double, humidity double, pressure double,
                wind_speed double, wind_direction double, is_raining boolean
            );
            create table staging.stg_driver_codes (
                season integer, driver_code varchar, driver_name varchar
            );
            create table staging.constructor_colors (team varchar, team_color varchar);
            insert into marts.race_replay values
                (2026, 1, 'NOR', 0, 10, 20, 1, 0, 0),
                (2026, 1, 'NOR', 1, 20, 30, 1, 0, 0);
            insert into marts.race_overtakes values
                (2026, 1, .5, 1, 'NOR', 'VER', .1, .95, 'adjacent swap', 'pass');
            insert into staging.stg_laps values
                (2026, 1, 'R', 'NOR', 'McLaren', 1, 100, 80, 1, 'MEDIUM', 1);
            insert into staging.stg_results values
                (2026, 1, 'NOR', 'Lando Norris', 1, 1, 'Finished', true);
            insert into staging.stg_races values
                (2026, 1, 'Test Grand Prix', date '2026-03-01', 'Test Circuit', 'Testland', 'Test City');
            insert into staging.stg_race_control values
                (2026, 1, 'R', 101, 'Flag', 'GREEN', 'Track', 'Green flag', null);
            insert into staging.stg_team_radio values
                (2026, 1, 'R', 95, 'NOR', 'https://example.com/pre-race.mp3', 'Radio check'),
                (2026, 1, 'R', 101, 'NOR', 'https://example.com/race.mp3', null),
                (2026, 1, 'R', 190, 'NOR', 'https://example.com/post-race.mp3', 'Great job');
            insert into staging.stg_weather values
                (2026, 1, 'R', 100, 21.5, 31.2, 58, 1012.4, 2.7, 245, false),
                (2026, 1, 'R', 160, 21.8, 30.7, 60, 1012.1, 3.1, 250, true);
            insert into staging.stg_driver_codes values (2026, 'NOR', 'Lando Norris');
            insert into staging.constructor_colors values ('McLaren', '#ff8700');
            """
        )


def test_exports_deterministic_per_race_bundle(tmp_path: Path) -> None:
    snapshot = tmp_path / "latest.duckdb"
    _snapshot(snapshot)
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    source_manifest = tmp_path / "latest.json"
    source_manifest.write_text(
        json.dumps(
            {"sha256": digest, "version": "test-v1", "generated_at": "2026-03-01T00:00:00Z"}
        ),
        encoding="utf-8",
    )

    result = export_web_data(snapshot, tmp_path / "web-data", snapshot_manifest=source_manifest)

    assert result["default_race"] == "2026-01"
    assert result["races"][0]["position_rows"] == 2
    assert result["races"][0]["radio_count"] == 3
    assert result["races"][0]["pre_race_radio_count"] == 1
    assert result["races"][0]["race_radio_count"] == 1
    assert result["races"][0]["post_race_radio_count"] == 1
    assert result["races"][0]["weather_sample_count"] == 2
    bundle = json.loads((tmp_path / "web-data/races/2026-01/bundle.json").read_text())
    assert bundle["drivers"][0]["driver_name"] == "Lando Norris"
    assert [row["phase"] for row in bundle["radio"]] == ["pre-race", "race", "post-race"]
    assert bundle["radio"][0]["recording_url"].endswith("pre-race.mp3")
    assert bundle["weather"] == [
        {
            "t_s": 0.0,
            "air_temperature": 21.5,
            "track_temperature": 31.2,
            "humidity": 58.0,
            "pressure": 1012.4,
            "rainfall": False,
            "wind_direction": 245.0,
            "wind_speed": 2.7,
        },
        {
            "t_s": 60.0,
            "air_temperature": 21.8,
            "track_temperature": 30.7,
            "humidity": 60.0,
            "pressure": 1012.1,
            "rainfall": True,
            "wind_direction": 250.0,
            "wind_speed": 3.1,
        },
    ]
    with ipc.open_file(tmp_path / "web-data/races/2026-01/positions.arrow") as reader:
        table = reader.read_all()
    assert table.num_rows == 2
    assert table.column("driver_code")[0].as_py() == "NOR"
