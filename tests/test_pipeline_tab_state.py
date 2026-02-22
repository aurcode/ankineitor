"""Tests for non-UI pipeline tab state helper."""

from ankineitor.application.pipeline_tab_state import (
    DEFAULT_PIPELINE_WORD_INPUT,
    PIPELINE_SESSION_KEYS,
    PipelineTabStateService,
)


def test_initialize_session_defaults_sets_expected_keys():
    service = PipelineTabStateService()
    session_state = {}

    service.initialize_session_defaults(session_state)

    assert session_state[PIPELINE_SESSION_KEYS.profile_transform_selections] == {}
    assert session_state[PIPELINE_SESSION_KEYS.word_input] == DEFAULT_PIPELINE_WORD_INPUT
    assert session_state[PIPELINE_SESSION_KEYS.category_name] == ""


def test_resolve_profile_transform_state_sanitizes_map_and_uses_default_on_profile_switch():
    service = PipelineTabStateService()

    result = service.resolve_profile_transform_state(
        raw_profile_transform_map={
            "profile_a": ["audio", "img", 123],
            "stale_profile": ["x"],
            "profile_b": "bad-type",
        },
        valid_profile_ids=["profile_a", "profile_b"],
        selected_profile_id="profile_b",
        active_selector_profile="profile_a",
        current_widget_selection=["audio"],
        available_transform_names=["audio", "image"],
        default_selection=["image", "missing"],
    )

    assert result.profile_transform_map == {
        "profile_a": ["audio", "img", "123"],
        "profile_b": [],
    }
    assert result.widget_selection == ["image"]
    assert result.active_profile_id == "profile_b"


def test_resolve_profile_transform_state_keeps_filtered_current_when_profile_unchanged():
    service = PipelineTabStateService()

    result = service.resolve_profile_transform_state(
        raw_profile_transform_map={"profile_a": ["audio"]},
        valid_profile_ids=["profile_a"],
        selected_profile_id="profile_a",
        active_selector_profile="profile_a",
        current_widget_selection=["audio", "not-available"],
        available_transform_names=["audio"],
        default_selection=["audio"],
    )

    assert result.profile_transform_map == {"profile_a": ["audio"]}
    assert result.widget_selection == ["audio"]
    assert result.active_profile_id == "profile_a"
