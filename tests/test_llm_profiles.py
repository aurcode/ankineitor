"""Unit tests for LLM profile registry."""

from ankineitor.pipeline.llm_profiles import (
    DEFAULT_LLM_PROFILE_ID,
    SP_RUSSIAN_PROFILE_ID,
    SP_SPANISH_STANDARD_PROFILE_ID,
    get_llm_profile,
    list_llm_profiles,
)


def test_get_llm_profile_defaults_to_spanish_profile():
    profile = get_llm_profile(None)
    assert profile.profile_id == DEFAULT_LLM_PROFILE_ID
    assert "Spanish" in profile.display_name
    assert profile.source_language == "Spanish"
    assert profile.supports_images is True
    assert profile.default_tts_voice_id == "Upset Girl - Soft,Airy,Sweet"
    assert profile.tts_voice_pool == ()
    assert profile.always_include_audio_transforms is True
    assert profile.default_optional_transform_names == ()


def test_profile_prompt_renders_placeholders():
    profile = get_llm_profile(DEFAULT_LLM_PROFILE_ID)
    rendered = profile.render_prompt("quedar")
    assert "Analyze the target Spanish word 'quedar'" in rendered
    assert '"tts_clean_sentence"' in rendered
    assert "{word}" not in rendered


def test_list_profiles_returns_registered_profiles():
    profiles = list_llm_profiles()
    assert len(profiles) >= 3
    assert any(profile.profile_id == DEFAULT_LLM_PROFILE_ID for profile in profiles)
    assert any(profile.profile_id == SP_RUSSIAN_PROFILE_ID for profile in profiles)
    assert any(profile.profile_id == SP_SPANISH_STANDARD_PROFILE_ID for profile in profiles)


def test_sp_russian_profile_prompt_renders_word():
    profile = get_llm_profile(SP_RUSSIAN_PROFILE_ID)
    rendered = profile.render_prompt("набережная")
    assert "Analyze the target Russian word 'набережная'" in rendered
    assert "St. Petersburg" in rendered
    assert profile.source_language == "Russian"
    assert profile.supports_images is True
    assert profile.default_tts_voice_id == "Russian_HandsomeChildhoodFriend"
    assert profile.always_include_audio_transforms is True
