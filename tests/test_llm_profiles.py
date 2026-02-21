"""Unit tests for LLM profile registry."""

from ankineitor.pipeline.llm_profiles import (
    DEFAULT_LLM_PROFILE_ID,
    get_llm_profile,
    list_llm_profiles,
)


def test_get_llm_profile_defaults_to_lotm_profile():
    profile = get_llm_profile(None)
    assert profile.profile_id == DEFAULT_LLM_PROFILE_ID
    assert "LOTM" in profile.display_name


def test_profile_prompt_renders_placeholders():
    profile = get_llm_profile(DEFAULT_LLM_PROFILE_ID)
    rendered = profile.render_prompt("隐秘")
    assert "Analyze the target word '隐秘'" in rendered
    assert "{sentence_language}" not in rendered


def test_list_profiles_returns_registered_profiles():
    profiles = list_llm_profiles()
    assert len(profiles) >= 1
    assert any(profile.profile_id == DEFAULT_LLM_PROFILE_ID for profile in profiles)
