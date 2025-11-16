"""Unit tests for configuration settings."""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock

from pydantic import ValidationError

from ankineitor.config.settings import Settings, get_settings


class TestSettingsValidation:
    """Test settings validation functionality."""

    def test_valid_settings(self):
        """Test creation of valid settings."""
        settings = Settings(
            groq_api_key="gsk_test_api_key_1234567890abcdef",
            max_file_size_mb=10,
            log_level="INFO"
        )
        assert settings.groq_api_key == "gsk_test_api_key_1234567890abcdef"
        assert settings.max_file_size_mb == 10
        assert settings.log_level == "INFO"

    def test_invalid_api_key_format(self):
        """Test validation of invalid API key format."""
        with pytest.raises(ValidationError, match="Invalid Groq API key format"):
            Settings(groq_api_key="invalid_key_format")

    def test_file_size_limits(self):
        """Test file size validation limits."""
        # Test too small
        with pytest.raises(ValidationError, match="must be between 1 and 100"):
            Settings(max_file_size_mb=0)
        
        # Test too large
        with pytest.raises(ValidationError, match="must be between 1 and 100"):
            Settings(max_file_size_mb=101)

    def test_log_level_validation(self):
        """Test log level validation."""
        # Test invalid log level
        with pytest.raises(ValidationError, match="Invalid log level"):
            Settings(log_level="INVALID")

    def test_default_values(self):
        """Test default values are set correctly."""
        settings = Settings()
        assert settings.pipeline_db_path == "data/ankineitor_pipeline.db"
        assert settings.llm_model == "llama-3.3-70b-versatile"
        assert settings.llm_max_retries == 3
        assert settings.max_file_size_mb == 10
        assert settings.log_level == "INFO"

    def test_optional_api_key(self):
        """Test that API key is optional."""
        settings = Settings(groq_api_key=None)
        assert settings.groq_api_key is None


class TestSettingsEnvironment:
    """Test settings environment variable loading."""

    def test_settings_from_env_file(self, temp_dir):
        """Test loading settings from .env file."""
        env_file = temp_dir / ".env"
        env_content = """
        GROQ_API_KEY=gsk_env_api_key_1234567890abcdef
        MAX_FILE_SIZE_MB=5
        LOG_LEVEL=DEBUG
        DEV_MODE=true
        """
        env_file.write_text(env_content)
        
        with patch.dict(os.environ, {}, clear=True):
            with patch('ankineitor.config.settings.Settings.Config.env_file', str(env_file)):
                settings = Settings()
                assert settings.groq_api_key == "gsk_env_api_key_1234567890abcdef"
                assert settings.max_file_size_mb == 5
                assert settings.log_level == "DEBUG"
                assert settings.dev_mode is True

    def test_env_variables_override_defaults(self):
        """Test that environment variables override defaults."""
        env_vars = {
            "GROQ_API_KEY": "gsk_env_key_1234567890abcdef",
            "MAX_FILE_SIZE_MB": "20",
            "LOG_LEVEL": "WARNING",
            "LLM_MODEL": "custom-model",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            assert settings.groq_api_key == "gsk_env_key_1234567890abcdef"
            assert settings.max_file_size_mb == 20
            assert settings.log_level == "WARNING"
            assert settings.llm_model == "custom-model"


class TestSettingsDirectories:
    """Test directory creation functionality."""

    def test_ensure_directories_creates_required_dirs(self, temp_dir):
        """Test that ensure_directories creates required directories."""
        with patch('ankineitor.config.settings.Settings.pipeline_db_path', str(temp_dir / "data" / "pipeline.db")):
            with patch('ankineitor.config.settings.Settings.audio_output_dir', str(temp_dir / "audio")):
                settings = Settings()
                settings.ensure_directories()
                
                assert (temp_dir / "data").exists()
                assert (temp_dir / "audio").exists()
                assert (temp_dir / "logs").exists()
                assert (temp_dir / "output").exists()

    def test_ensure_directories_handles_existing_dirs(self, temp_dir):
        """Test that ensure_directories handles existing directories."""
        (temp_dir / "data").mkdir()
        (temp_dir / "audio").mkdir()
        
        with patch('ankineitor.config.settings.Settings.pipeline_db_path', str(temp_dir / "data" / "pipeline.db")):
            with patch('ankineitor.config.settings.Settings.audio_output_dir', str(temp_dir / "audio")):
                settings = Settings()
                # Should not raise error for existing directories
                settings.ensure_directories()


class TestGetSettingsSingleton:
    """Test get_settings singleton functionality."""

    def test_get_settings_returns_same_instance(self):
        """Test that get_settings returns the same instance (singleton)."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_get_settings_creates_directories(self):
        """Test that get_settings calls ensure_directories."""
        with patch('ankineitor.config.settings.Settings.ensure_directories') as mock_ensure:
            settings = get_settings()
            mock_ensure.assert_called_once()

    def test_get_settings_multiple_calls(self):
        """Test multiple calls to get_settings."""
        with patch('ankineitor.config.settings.Settings.ensure_directories') as mock_ensure:
            # First call should create directories
            settings1 = get_settings()
            assert mock_ensure.call_count == 1
            
            # Second call should not call ensure_directories again
            settings2 = get_settings()
            assert mock_ensure.call_count == 1
            assert settings1 is settings2


class TestSettingsEdgeCases:
    """Test edge cases and error conditions."""

    def test_case_insensitive_log_level(self):
        """Test that log level validation is case-insensitive."""
        settings = Settings(log_level="debug")
        assert settings.log_level == "DEBUG"
        
        settings = Settings(log_level="Warning")
        assert settings.log_level == "WARNING"

    def test_empty_allowed_extensions(self):
        """Test settings with empty allowed extensions."""
        settings = Settings(allowed_file_extensions=[])
        assert settings.allowed_file_extensions == []

    def test_single_allowed_extension(self):
        """Test settings with single allowed extension."""
        settings = Settings(allowed_file_extensions=[".csv"])
        assert settings.allowed_file_extensions == [".csv"]

    def test_allowed_extensions_from_comma_separated_string(self):
        """Test parsing allowed extensions from comma-separated string."""
        settings = Settings(allowed_file_extensions=".csv,.txt,.pdf")
        assert settings.allowed_file_extensions == [".csv", ".txt", ".pdf"]

    def test_allowed_extensions_from_comma_separated_string_with_spaces(self):
        """Test parsing allowed extensions from comma-separated string with spaces."""
        settings = Settings(allowed_file_extensions=".csv, .txt, .pdf")
        assert settings.allowed_file_extensions == [".csv", ".txt", ".pdf"]

    def test_allowed_extensions_from_string_without_dots(self):
        """Test parsing allowed extensions from string without leading dots."""
        settings = Settings(allowed_file_extensions="csv,txt,pdf")
        assert settings.allowed_file_extensions == [".csv", ".txt", ".pdf"]

    def test_allowed_extensions_from_env_string(self):
        """Test parsing allowed extensions from environment variable string."""
        with patch.dict(os.environ, {"ALLOWED_FILE_EXTENSIONS": ".csv,.txt,.pdf,.docx"}, clear=True):
            settings = Settings()
            assert settings.allowed_file_extensions == [".csv", ".txt", ".pdf", ".docx"]

    def test_complex_path_settings(self, temp_dir):
        """Test settings with complex paths."""
        complex_path = temp_dir / "deep" / "nested" / "path"
        settings = Settings(
            pipeline_db_path=str(complex_path / "pipeline.db"),
            audio_output_dir=str(complex_path / "audio")
        )
        assert "deep/nested/path/pipeline.db" in str(settings.pipeline_db_path)
        assert "deep/nested/path/audio" in str(settings.audio_output_dir)

    def test_settings_with_unicode_paths(self, temp_dir):
        """Test settings with Unicode characters in paths."""
        unicode_path = temp_dir / "测试路径"
        settings = Settings(
            pipeline_db_path=str(unicode_path / "pipeline.db")
        )
        assert "测试路径" in str(settings.pipeline_db_path)


class TestSettingsValidationMessages:
    """Test validation error messages."""

    def test_api_key_validation_message(self):
        """Test API key validation error message."""
        try:
            Settings(groq_api_key="invalid_key")
        except ValidationError as e:
            assert "Invalid Groq API key format" in str(e)

    def test_file_size_validation_message(self):
        """Test file size validation error message."""
        try:
            Settings(max_file_size_mb=0)
        except ValidationError as e:
            assert "must be between 1 and 100" in str(e)

    def test_log_level_validation_message(self):
        """Test log level validation error message."""
        try:
            Settings(log_level="INVALID")
        except ValidationError as e:
            assert "Invalid log level" in str(e)
            assert "DEBUG, INFO, WARNING, ERROR, CRITICAL" in str(e)


class TestSettingsConfiguration:
    """Test Pydantic configuration."""

    def test_case_sensitive_false(self):
        """Test that settings are case-insensitive."""
        with patch.dict(os.environ, {"log_level": "debug"}, clear=True):
            settings = Settings()
            assert settings.log_level == "DEBUG"

    def test_env_file_encoding(self):
        """Test that env file encoding is set correctly."""
        config = Settings.Config
        assert config.env_file_encoding == "utf-8"

    def test_env_file_default(self):
        """Test default env file setting."""
        config = Settings.Config
        assert config.env_file == ".env"
