from pathlib import Path

ROOT = Path(__file__).parents[1]
REPLAY_LAPS_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "race_replay_laps.sql"
OVERTAKE_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "race_overtakes.sql"
META_SOURCE = ROOT / "dashboard" / "sources" / "f1" / "race_replay_meta.sql"
TRACK_MAP = ROOT / "dashboard" / "components" / "TrackMap.svelte"
EVENT_TIMELINE = ROOT / "dashboard" / "components" / "replay" / "EventTimeline.svelte"
WEB_EXPORTER = ROOT / "scripts" / "export_web_data.py"
WEB_MODEL = ROOT / "web" / "src" / "lib" / "replay" / "model.ts"


def test_replay_serving_contract_includes_live_timing_context() -> None:
    source = REPLAY_LAPS_SOURCE.read_text(encoding="utf-8")
    exporter = WEB_EXPORTER.read_text(encoding="utf-8")
    model = WEB_MODEL.read_text(encoding="utf-8")

    for field in ("lap_number", "lap_start_t_s", "stint", "compound", "tyre_life"):
        assert field in source
        assert field in exporter

    # The positional feed is exported as per-race Arrow bundles for the
    # dedicated SvelteKit replay. It must not also be materialised as one giant
    # Evidence source, which previously added hundreds of MB to the static site.
    assert not (ROOT / "dashboard" / "sources" / "f1" / "race_replay.sql").exists()
    assert 'race_dir / "positions.arrow"' in exporter
    assert "lap_start_t_s" in model
    assert "tyreLife" in model


def test_overtakes_expose_detector_confidence() -> None:
    source = OVERTAKE_SOURCE.read_text(encoding="utf-8")
    exporter = WEB_EXPORTER.read_text(encoding="utf-8")
    model = WEB_MODEL.read_text(encoding="utf-8")

    assert "o.confidence" in source
    assert "o.evidence" in source
    assert "o.reason" in source
    assert "confidence, evidence, reason" in exporter
    assert "row.confidence" in model


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
    assert "relevantToSelection(event, selectedCode)" in component
    assert "event.participants.includes(driverCode)" in component
    assert "event.category === 'radio'" in component
    assert "event.driverCode === driverCode" in component
    assert "Showing overtakes &amp; radio for" in component


def test_radio_playback_has_visible_controls_and_error_feedback() -> None:
    track_map = TRACK_MAP.read_text(encoding="utf-8")
    timeline = EVENT_TIMELINE.read_text(encoding="utf-8")

    assert "normaliseRadioClip" in track_map
    assert "playRadio(clip)" in track_map
    assert "audioEl.play()" in track_map
    assert "on:error={handleRadioError}" in track_map
    assert 'role="alert"' in track_map
    assert "controls" in track_map
    assert "activateMarker(event)" in timeline


def test_position_change_is_anchored_to_the_official_grid() -> None:
    source = META_SOURCE.read_text(encoding="utf-8")
    component = TRACK_MAP.read_text(encoding="utf-8")

    assert "results.grid_position" in source
    assert "g.startOrder = asNum(m.grid_position)" in component
