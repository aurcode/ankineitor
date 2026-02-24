"""Unit tests for configuration settings."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

import ankineitor.config.settings as settings_module
from ankineitor.config.settings import Settings, get_settings


class TestSettingsValidation:
    """Test settings validation functionality."""

    def test_valid_settings(self):
        settings = Settings(
            _env_file=None,
            llm_api_token="AQ.test_token_1234567890abcdef",
            max_file_size_mb=10,
            log_level="INFO",
        )
        assert settings.llm_api_token == "AQ.test_token_1234567890abcdef"
        assert settings.max_file_size_mb == 10
        assert settings.log_level == "INFO"

    def test_file_size_limits(self):
        with pytest.raises(ValidationError, match="must be between 1 and 100"):
            Settings(_env_file=None, max_file_size_mb=0)

        with pytest.raises(ValidationError, match="must be between 1 and 100"):
            Settings(_env_file=None, max_file_size_mb=101)

    def test_log_level_validation(self):
        with pytest.raises(ValidationError, match="Invalid log level"):
            Settings(_env_file=None, log_level="INVALID")

    def test_default_values(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.pipeline_db_path == "data/ankineitor_pipeline.db"
            assert settings.llm_raw_response_db_path == "data/ankineitor_llm_raw_response.db"
            assert settings.llm_model == "gemini-3.1-pro-preview"
            assert settings.llm_image_prompt_model == "gemini-3.1-pro-preview"
            assert settings.llm_image_master_prompt_template is None
            assert "与" in settings.llm_image_do_not_generate_terms
            assert settings.llm_image_model == "gemini-3-pro-image-preview"
            assert settings.llm_image_max_workers == 1
            assert settings.llm_profile_id == "sp_spanish_standard"
            assert settings.llm_profile_db_isolation is True
            assert settings.llm_source_language == "Spanish"
            assert settings.llm_target_language == "english"
            assert settings.llm_secondary_target_language is None
            assert settings.llm_max_retries == 3
            assert settings.max_file_size_mb == 10
            assert settings.log_level == "INFO"
            assert settings.gcp_location == "us-central1"

    def test_optional_token(self):
        settings = Settings(_env_file=None, llm_api_token=None)
        assert settings.llm_api_token is None


class TestSettingsEnvironment:
    """Test settings environment variable loading."""

    def test_settings_from_env_file(self, temp_dir):
        env_file = temp_dir / ".env"
        env_content = """
        LLM_API_TOKEN=AQ.env_token_1234567890abcdef
        MAX_FILE_SIZE_MB=5
        LOG_LEVEL=DEBUG
        DEV_MODE=true
        GCP_PROJECT_ID=data-worldsacross
        """
        env_file.write_text(env_content)

        with patch.dict(os.environ, {}, clear=True):
            settings = Settings(_env_file=str(env_file))
            assert settings.llm_api_token == "AQ.env_token_1234567890abcdef"
            assert settings.max_file_size_mb == 5
            assert settings.log_level == "DEBUG"
            assert settings.dev_mode is True
            assert settings.gcp_project_id == "data-worldsacross"

    def test_env_variables_override_defaults(self):
        env_vars = {
            "LLM_API_TOKEN": "AQ.env_key_1234567890abcdef",
            "MAX_FILE_SIZE_MB": "20",
            "LOG_LEVEL": "WARNING",
            "LLM_MODEL": "gemini-3-flash-preview",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings(_env_file=None)
            assert settings.llm_api_token == "AQ.env_key_1234567890abcdef"
            assert settings.max_file_size_mb == 20
            assert settings.log_level == "WARNING"
            assert settings.llm_model == "gemini-3-flash-preview"

    def test_resolve_llm_token_aliases(self):
        settings = Settings(
            _env_file=None,
            llm_api_token=None,
            gemini_api_key="AIzaGeminiKey",
            google_api_key=None,
        )
        assert settings.resolve_llm_api_token() == "AIzaGeminiKey"

        with patch.dict(os.environ, {"VERTEX_API_TOKEN": "AQ.vertex_alias_token"}, clear=True):
            settings = Settings(
                _env_file=None,
                llm_api_token=None,
                gemini_api_key=None,
                google_api_key=None,
            )
            assert settings.resolve_llm_api_token() == "AQ.vertex_alias_token"


class TestSettingsDirectories:
    """Test directory creation functionality."""

    def test_ensure_directories_creates_required_dirs(self, temp_dir):
        settings = Settings(
            _env_file=None,
            pipeline_db_path=str(temp_dir / "data" / "pipeline.db"),
            llm_cache_db_path=str(temp_dir / "data" / "llm_cache.db"),
            llm_raw_response_db_path=str(temp_dir / "data" / "llm_raw.db"),
            audio_output_dir=str(temp_dir / "audio"),
            image_output_dir=str(temp_dir / "images"),
        )
        settings.ensure_directories()
        assert (temp_dir / "data").exists()
        assert (temp_dir / "audio").exists()
        assert (temp_dir / "images").exists()


class TestGetSettingsSingleton:
    """Test get_settings singleton functionality."""

    def test_get_settings_returns_same_instance(self):
        settings_module._settings = None
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_get_settings_creates_directories(self):
        settings_module._settings = None
        with patch("ankineitor.config.settings.Settings.ensure_directories") as mock_ensure:
            _ = get_settings()
            mock_ensure.assert_called_once()


class TestSettingsEdgeCases:
    """Test edge cases and error conditions."""

    def test_case_insensitive_log_level(self):
        settings = Settings(_env_file=None, log_level="debug")
        assert settings.log_level == "DEBUG"

        settings = Settings(_env_file=None, log_level="Warning")
        assert settings.log_level == "WARNING"

    def test_allowed_extensions_parsing(self):
        settings = Settings(_env_file=None, allowed_file_extensions=".csv,txt,.pdf")
        assert settings.allowed_file_extensions == [".csv", ".txt", ".pdf"]

    def test_allowed_extensions_from_env(self):
        env_value = '[".csv", ".txt", ".pdf", ".docx"]'
        with patch.dict(os.environ, {"ALLOWED_FILE_EXTENSIONS": env_value}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.allowed_file_extensions == [".csv", ".txt", ".pdf", ".docx"]

    def test_image_blocked_terms_parsing_from_constructor_csv(self):
        settings = Settings(
            _env_file=None,
            llm_image_do_not_generate_terms="与, 一个, 不会",
        )
        assert settings.llm_image_do_not_generate_terms == ["与", "一个", "不会"]

    def test_image_blocked_terms_parsing_from_env_json(self):
        with patch.dict(
            os.environ,
            {"LLM_IMAGE_DO_NOT_GENERATE_TERMS": '["与", "一个", "不会"]'},
            clear=True,
        ):
            settings = Settings(_env_file=None)
            assert settings.llm_image_do_not_generate_terms == ["与", "一个", "不会"]


class TestSettingsConfiguration:
    """Test Pydantic configuration."""

    def test_case_sensitive_false(self):
        with patch.dict(os.environ, {"log_level": "debug"}, clear=True):
            settings = Settings(_env_file=None)
            assert settings.log_level == "DEBUG"

    def test_env_file_default(self):
        config = Settings.model_config
        assert config.get("env_file") == ".env"
        assert config.get("env_file_encoding") == "utf-8"
