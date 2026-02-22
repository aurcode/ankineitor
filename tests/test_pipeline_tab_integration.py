"""Thin integration tests for Streamlit pipeline tab state wiring."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import sys
import types

from ankineitor.application import PIPELINE_SESSION_KEYS


class _SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


class _NoopContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False


class _FakeStreamlit:
    def __init__(self):
        self.session_state = _SessionState()
        self.button_map = {}
        self.errors = []

    def header(self, text):
        del text

    def markdown(self, text):
        del text

    def subheader(self, text):
        del text

    def caption(self, text):
        del text

    def divider(self):
        return None

    def columns(self, n):
        return [_NoopContext() for _ in range(int(n))]

    def selectbox(self, label, options, index, format_func):
        del label, format_func
        return options[index]

    def multiselect(self, label, options, key):
        del label, options
        value = self.session_state.get(key, [])
        self.session_state[key] = list(value)
        return list(value)

    def text_area(self, label, height, help, key):
        del label, height, help
        return str(self.session_state.get(key, ""))

    def button(self, label, **kwargs):
        del kwargs
        return bool(self.button_map.get(label, False))

    def expander(self, label):
        del label
        return _NoopContext()

    def error(self, text):
        self.errors.append(str(text))


@dataclass
class _Profile:
    profile_id: str
    display_name: str
    description: str
    source_language: str
    default_optional_transform_names: tuple[str, ...]
    supports_images: bool = True
    always_include_audio_transforms: bool = False


def _patch_profiles(monkeypatch):
    profile_a = _Profile(
        profile_id="profile_a",
        display_name="Profile A",
        description="Profile A description",
        source_language="Chinese (Simplified)",
        default_optional_transform_names=("audio", "image"),
    )
    profile_b = _Profile(
        profile_id="profile_b",
        display_name="Profile B",
        description="Profile B description",
        source_language="Chinese (Simplified)",
        default_optional_transform_names=("image",),
    )
    profiles = [profile_a, profile_b]
    by_id = {profile.profile_id: profile for profile in profiles}
    return profiles, by_id


def _load_pipeline_tab_module_with_fake_streamlit(monkeypatch):
    fake_streamlit_module = types.ModuleType("streamlit")
    monkeypatch.setitem(sys.modules, "streamlit", fake_streamlit_module)
    sys.modules.pop("app.tabs.pipeline_tab", None)
    return importlib.import_module("app.tabs.pipeline_tab")


def test_render_pipeline_tab_initializes_and_sanitizes_profile_state(monkeypatch):
    pipeline_tab = _load_pipeline_tab_module_with_fake_streamlit(monkeypatch)
    fake_st = _FakeStreamlit()
    fake_st.session_state.update(
        {
            "llm_profile_id_ui": "profile_a",
            PIPELINE_SESSION_KEYS.profile_transform_selections: {
                "profile_a": ["image", "unknown"],
                "stale_profile": ["audio"],
            },
            PIPELINE_SESSION_KEYS.transform_selector_profile: "profile_b",
            PIPELINE_SESSION_KEYS.selected_transform_widget: ["audio", "unknown"],
        }
    )

    monkeypatch.setattr(pipeline_tab, "st", fake_st)
    profiles, by_id = _patch_profiles(monkeypatch)
    monkeypatch.setattr(pipeline_tab, "list_llm_profiles", lambda: profiles)
    monkeypatch.setattr(
        pipeline_tab,
        "get_llm_profile",
        lambda profile_id: by_id[profile_id],
    )

    pipeline_tab.render_pipeline_tab(
        pipeline_db_client=object(),
        all_transformations={"audio": object(), "image": object()},
    )

    assert fake_st.errors == []
    assert fake_st.session_state[PIPELINE_SESSION_KEYS.word_input]
    assert fake_st.session_state[PIPELINE_SESSION_KEYS.category_name] == ""
    assert fake_st.session_state[PIPELINE_SESSION_KEYS.transform_selector_profile] == "profile_a"
    assert fake_st.session_state[PIPELINE_SESSION_KEYS.selected_transform_widget] == ["image"]
    assert fake_st.session_state[PIPELINE_SESSION_KEYS.profile_transform_selections] == {
        "profile_a": ["image"]
    }


def test_render_pipeline_tab_keeps_current_profile_filtered_selection(monkeypatch):
    pipeline_tab = _load_pipeline_tab_module_with_fake_streamlit(monkeypatch)
    fake_st = _FakeStreamlit()
    fake_st.session_state.update(
        {
            "llm_profile_id_ui": "profile_a",
            PIPELINE_SESSION_KEYS.profile_transform_selections: {"profile_a": ["audio"]},
            PIPELINE_SESSION_KEYS.transform_selector_profile: "profile_a",
            PIPELINE_SESSION_KEYS.selected_transform_widget: ["audio", "missing"],
            PIPELINE_SESSION_KEYS.word_input: "custom words",
            PIPELINE_SESSION_KEYS.category_name: "My Category",
        }
    )

    monkeypatch.setattr(pipeline_tab, "st", fake_st)
    profiles, by_id = _patch_profiles(monkeypatch)
    monkeypatch.setattr(pipeline_tab, "list_llm_profiles", lambda: profiles)
    monkeypatch.setattr(
        pipeline_tab,
        "get_llm_profile",
        lambda profile_id: by_id[profile_id],
    )

    pipeline_tab.render_pipeline_tab(
        pipeline_db_client=object(),
        all_transformations={"audio": object(), "image": object()},
    )

    assert fake_st.errors == []
    assert fake_st.session_state[PIPELINE_SESSION_KEYS.word_input] == "custom words"
    assert fake_st.session_state[PIPELINE_SESSION_KEYS.category_name] == "My Category"
    assert fake_st.session_state[PIPELINE_SESSION_KEYS.selected_transform_widget] == ["audio"]
    assert fake_st.session_state[PIPELINE_SESSION_KEYS.profile_transform_selections] == {
        "profile_a": ["audio"]
    }
