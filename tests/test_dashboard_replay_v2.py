from pathlib import Path

ROOT = Path(__file__).parents[1]
PAGE = ROOT / "dashboard" / "pages" / "race-replay.md"
REPLAY_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "race_replay.sql"
REPLAY_LAPS_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "race_replay_laps.sql"
OVERTAKE_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "race_overtakes.sql"
META_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "race_replay_meta.sql"
TRACK_MAP = ROOT / "dashboard" / "components" / "TrackMap.svelte"
EVENT_TIMELINE = ROOT / "dashboard" / "components" / "replay" / "EventTimeline.svelte"


def test_replay_serving_contract_includes_live_timing_context() -> None:
    page = PAGE.read_text(encoding="utf-8")
    source = REPLAY_LAPS_SOURCE.read_text(encoding="utf-8")

    for field in ("lap_number", "lap_start_t_s", "stint", "compound", "tyre_life"):
        assert field in page
        assert field in source

    positional_source = REPLAY_SOURCE.read_text(encoding="utf-8")
    assert "r.compound" not in positional_source
    assert "r.tyre_life" not in positional_source
    assert "laps={replay_laps}" in page


def test_overtakes_expose_detector_confidence() -> None:
    page = PAGE.read_text(encoding="utf-8")
    source = OVERTAKE_SOURCE.read_text(encoding="utf-8")

    assert "o.confidence" in source
    assert "o.evidence" in source
    assert "o.reason" in source
    assert "confidence, evidence, reason" in page


def test_replay_uses_separate_broadcast_ui_components() -> None:
    component = TRACK_MAP.read_text(encoding="utf-8")

    assert "./replay/TimingTower.svelte" in component
    assert "./replay/DriverDetail.svelte" in component
    assert "./replay/EventTimeline.svelte" in component
    assert "<TimingTower" in component
    assert "<DriverDetail" in component
    assert "<EventTimeline" in component


def test_event_timeline_unifies_replay_intelligence() -> None:
    component = EVENT_TIMELINE.read_text(encoding="utf-8")

    assert "buildEvents(messages, overtakes, radio)" in component
    assert "Race control" in component
    assert "Overtakes" in component
    assert "Radio" in component
    assert "relevantToSelection" in component
    assert "onPlayRadio" in component


def test_selected_driver_timeline_only_shows_their_overtakes_and_radio() -> None:
    component = EVENT_TIMELINE.read_text(encoding="utf-8")

    assert "filter.id !== 'control'" in component
    assert "event.category === 'overtake'" in component
    assert "event.participants.includes(selectedCode)" in component
    assert "event.category === 'radio'" in component
    assert "event.driverCode === selectedCode" in component
    assert "Showing overtakes &amp; radio for" in component


def test_position_change_is_anchored_to_the_official_grid() -> None:
    source = META_SOURCE.read_text(encoding="utf-8")
    component = TRACK_MAP.read_text(encoding="utf-8")

    assert "results.grid_position" in source
    assert "g.startOrder = asNum(m.grid_position)" in component
