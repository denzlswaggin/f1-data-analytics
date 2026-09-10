import pandas as pd
import pytest
from analytics.pit_context import attach_pit_lap_context, build_pit_lap_context


def _laps() -> pd.DataFrame:
    return pd.DataFrame(
        {"season": 2025, "round": 8, "driver_code": "RUS", "lap_number": range(60, 66), "stint": 1}
    )


def test_pit_without_tyre_change_and_repeated_stop_records() -> None:
    stops = pd.DataFrame(
        {
            "season": [2025, 2025],
            "round": [8, 8],
            "driver_code": ["RUS", "RUS"],
            "pit_lap": [62, 62],
        }
    )
    context = build_pit_lap_context(_laps(), stops).set_index("lap_number")
    assert context.index.is_unique
    assert context.loc[62, "is_pit_in_lap"]
    assert context.loc[63, "is_pit_out_lap"]
    assert context["is_pit_boundary"].sum() == 2
    assert context.loc[62, "pit_context_source"] == "jolpica"
    assert context.loc[62, "pit_context_status"] == "observed_pit"


def test_direct_fastf1_mapping_does_not_shift_outlap() -> None:
    laps = _laps()
    laps["pit_in_time_sec"] = [None, None, 100.0, None, None, None]
    laps["pit_out_time_sec"] = [None, None, 102.0, None, None, None]
    context = build_pit_lap_context(laps).set_index("lap_number")
    assert context.loc[62, "pit_exclusion_reason"] == "pit_in_out_lap"
    assert not context.loc[63, "is_pit_boundary"]


def test_stint_boundaries_and_first_observed_stint() -> None:
    laps = _laps()
    laps["stint"] = [1, 1, 1, 2, 2, 2]
    context = build_pit_lap_context(laps).set_index("lap_number")
    assert not context.loc[60, "is_pit_out_lap"]
    assert context.loc[62, "is_pit_in_lap"]
    assert context.loc[63, "is_pit_out_lap"]
    assert context.loc[63, "pit_context_status"] == "inferred_pit"
    partial = build_pit_lap_context(laps.loc[laps["stint"].eq(2)])
    assert partial.iloc[0]["is_pit_out_lap"]


def test_sources_union_in_stable_order() -> None:
    laps = _laps()
    laps["stint"] = [1, 1, 1, 2, 2, 2]
    laps["pit_in_time_sec"] = [None, None, 100.0, None, None, None]
    stops = pd.DataFrame({"season": [2025], "round": [8], "driver_code": ["RUS"], "pit_lap": [62]})
    context = build_pit_lap_context(laps, stops).set_index("lap_number")
    assert context.loc[62, "pit_context_source"] == "fastf1+jolpica+stint_inference"
    assert context.loc[62, "pit_context_status"] == "observed_pit"


def test_unknown_is_not_confirmed_absence() -> None:
    laps = _laps().drop(columns="stint")
    laps["pit_in_time_sec"] = None
    laps["pit_out_time_sec"] = None
    for stops in (None, pd.DataFrame()):
        context = build_pit_lap_context(laps, stops)
        assert context["pit_context_status"].eq("unknown").all()
        assert not context["is_pit_boundary"].any()
    context = build_pit_lap_context(_laps())
    assert context["pit_context_status"].eq("no_pit_observed").all()


def test_other_driver_stop_does_not_establish_coverage() -> None:
    stops = pd.DataFrame({"season": [2025], "round": [8], "driver_code": ["VER"], "pit_lap": [62]})
    context = build_pit_lap_context(_laps().drop(columns="stint"), stops)
    assert context["pit_context_status"].eq("unknown").all()


def test_duplicates_rejected_and_session_filtered() -> None:
    laps = _laps()
    with pytest.raises(ValueError, match="Duplicate"):
        build_pit_lap_context(pd.concat([laps, laps]))
    laps["session"] = "R"
    qualifying = laps.assign(session="Q")
    assert len(build_pit_lap_context(pd.concat([laps, qualifying]))) == len(laps)


def test_empty_types_and_attach_missing_context_overwrites_stale_values() -> None:
    empty = build_pit_lap_context(pd.DataFrame())
    assert str(empty["is_pit_boundary"].dtype) == "bool"
    laps = _laps().assign(is_pit_boundary=True, pit_context_status="observed_pit")
    attached = attach_pit_lap_context(laps, empty)
    assert not attached["is_pit_boundary"].any()
    assert attached["pit_context_status"].eq("unknown").all()
    assert attached["pit_context_source"].eq("unavailable").all()
    pd.testing.assert_series_equal(attached["lap_number"], laps["lap_number"])


def test_partial_explicit_flags_are_not_lost() -> None:
    laps = _laps().assign(is_pit_boundary=[False, False, True, False, False, False])
    context = build_pit_lap_context(laps)
    assert context.loc[2, "is_pit_boundary"]
    assert context.loc[2, "pit_context_status"] == "inferred_pit"
    assert context.loc[2, "pit_context_source"] == "provided_flags"


def test_unsorted_input_is_deterministic() -> None:
    laps = _laps()
    pd.testing.assert_frame_equal(
        build_pit_lap_context(laps), build_pit_lap_context(laps.iloc[::-1])
    )
