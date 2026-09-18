import pandas as pd
from scripts.expand_dna_telemetry import expansion_pairs


def test_expansion_selects_joint_pair_instead_of_incompatible_fastest_laps() -> None:
    laps = pd.DataFrame(
        [
            {"driver_code": "AAA", "lap_number": 10, "lap_time_sec": 88.0, "compound": "SOFT"},
            {"driver_code": "AAA", "lap_number": 30, "lap_time_sec": 90.0, "compound": "HARD"},
            {"driver_code": "BBB", "lap_number": 31, "lap_time_sec": 89.0, "compound": "HARD"},
        ]
    ).assign(
        team="Team",
        tyre_life=5,
        track_status="1",
        pit_in_time_sec=float("nan"),
        pit_out_time_sec=float("nan"),
    )
    assert expansion_pairs(laps) == [("AAA", 30), ("BBB", 31)]
    # Never relax matching when the only candidate has a large race-lap gap.
    laps.loc[laps.driver_code.eq("BBB"), "lap_number"] = 40
    assert expansion_pairs(laps) == []


def test_expansion_rejects_pit_laps_and_unready_tyres() -> None:
    laps = pd.DataFrame(
        [
            {"driver_code": "AAA", "lap_number": 10},
            {"driver_code": "BBB", "lap_number": 11},
        ]
    ).assign(
        team="Team",
        lap_time_sec=90.0,
        compound="HARD",
        tyre_life=5,
        track_status="1",
        pit_in_time_sec=float("nan"),
        pit_out_time_sec=float("nan"),
    )
    assert len(expansion_pairs(laps)) == 2
    for column, value in (
        ("pit_in_time_sec", 1000),
        ("pit_out_time_sec", 1000),
        ("tyre_life", 1),
        ("track_status", "4"),
        ("compound", "WET"),
    ):
        invalid = laps.copy()
        invalid.loc[0, column] = value
        assert expansion_pairs(invalid) == []
