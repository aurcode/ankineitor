"""Unit tests for LLM profile registry."""

from ankineitor.pipeline.llm_profiles import (
    DEFAULT_LLM_PROFILE_ID,
    SP_RUSSIAN_PROFILE_ID,
    get_llm_profile,
    list_llm_profiles,
)


def test_get_llm_profile_defaults_to_lotm_profile():
    profile = get_llm_profile(None)
    assert profile.profile_id == DEFAULT_LLM_PROFILE_ID
    assert "LOTM" in profile.display_name
    assert profile.source_language == "Chinese (Simplified)"
    assert profile.supports_images is True
    assert profile.default_tts_voice_id == "Chinese (Mandarin)_Mature_Woman"
    assert profile.tts_voice_pool == ()


def test_profile_prompt_renders_placeholders():
    profile = get_llm_profile(DEFAULT_LLM_PROFILE_ID)
    rendered = profile.render_prompt("隐秘")
    assert "Analyze the target word '隐秘'" in rendered
    assert '"tts_clean_sentence"' in rendered
    assert "{sentence_language}" not in rendered


def test_list_profiles_returns_registered_profiles():
    profiles = list_llm_profiles()
    assert len(profiles) >= 2
    assert any(profile.profile_id == DEFAULT_LLM_PROFILE_ID for profile in profiles)
    assert any(profile.profile_id == SP_RUSSIAN_PROFILE_ID for profile in profiles)


def test_sp_russian_profile_prompt_renders_word():
    profile = get_llm_profile(SP_RUSSIAN_PROFILE_ID)
    rendered = profile.render_prompt("набережная")
    assert "Analyze the target Russian word 'набережная'" in rendered
    assert "St. Petersburg" in rendered
    assert profile.source_language == "Russian"
    assert profile.supports_images is True
    assert profile.default_tts_voice_id == "Russian_HandsomeChildhoodFriend"
