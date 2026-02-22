"""Test configuration and fixtures for Ankineitor tests."""

import pytest
import tempfile
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch
import pandas as pd
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

# Ensure tests can import the local package without requiring PYTHONPATH.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))
BACKEND_PATH = PROJECT_ROOT / "web" / "backend"
if str(BACKEND_PATH) not in sys.path:
    sys.path.insert(0, str(BACKEND_PATH))


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    with patch('ankineitor.config.settings.get_settings') as mock:
        settings = Mock()
        settings.llm_api_token = "AQ.test_token_1234567890abcdef"
        settings.gemini_api_key = None
        settings.google_api_key = None
        settings.pipeline_db_path = "test_pipeline.db"
        settings.llm_cache_db_path = "test_llm_cache.db"
        settings.llm_raw_response_db_path = "test_llm_raw_response.db"
        settings.audio_output_dir = "./test_audio_files"
        settings.image_output_dir = "./test_image_files"
        settings.llm_model = "gemini-3.1-pro-preview"
        settings.llm_image_prompt_model = "gemini-3.1-pro-preview"
        settings.llm_image_master_prompt_template = None
        settings.llm_image_do_not_generate_terms = ["与", "一个", "不会"]
        settings.llm_image_model = "gemini-3-pro-image-preview"
        settings.llm_image_max_workers = 1
        settings.llm_profile_id = "lotm_zh_en_es"
        settings.llm_profile_db_isolation = True
        settings.llm_source_language = "Chinese (Simplified)"
        settings.llm_target_language = "english"
        settings.llm_secondary_target_language = None
        settings.llm_max_retries = 3
        settings.llm_timeout = 30
        settings.gcp_project_id = "test-project"
        settings.gcp_location = "us-central1"
        settings.bq_credentials_path = None
        settings.vertex_credentials_path = None
        settings.max_file_size_mb = 10
        settings.allowed_file_extensions = [".csv", ".txt", ".pdf", ".docx", ".pptx"]
        settings.log_level = "INFO"
        settings.dev_mode = False
        settings.resolve_llm_api_token = Mock(return_value="AQ.test_token_1234567890abcdef")
        mock.return_value = settings
        yield settings


@pytest.fixture
def sample_csv_content():
    """Sample CSV content for testing."""
    return """word,pinyin,translation,audio
你好,nǐ hǎo,hello,hello.wav
谢谢,xiè xiè,thank you,thank_you.wav
苹果,píng guǒ,apple,apple.wav"""


@pytest.fixture
def sample_words():
    """Sample Chinese words for testing."""
    return ["你好", "谢谢", "苹果", "数据", "工程师"]


@pytest.fixture
def mock_streamlit_file():
    """Mock Streamlit uploaded file."""
    mock_file = Mock()
    mock_file.name = "test_vocabulary.csv"
    # Use ASCII-safe content for bytes
    mock_file.getvalue.return_value = b"word,pinyin,translation\ntest1,test2,hello\ntest3,test4,thank you"
    mock_file.size = 1024  # 1KB
    return mock_file


@pytest.fixture
def large_mock_file():
    """Mock large file for testing size limits."""
    mock_file = Mock()
    mock_file.name = "large_file.csv"
    # Create content larger than 10MB
    large_content = b"word,pinyin\n" + b"test,test\n" * 200000
    mock_file.getvalue.return_value = large_content
    mock_file.size = len(large_content)
    return mock_file


@pytest.fixture
def malicious_filename_file():
    """Mock file with malicious filename."""
    mock_file = Mock()
    mock_file.name = "../../../etc/passwd.csv"
    mock_file.getvalue.return_value = b"word,pinyin\ntest1,test2"
    mock_file.size = 1024
    return mock_file


@pytest.fixture
def invalid_csv_content():
    """Invalid CSV content for testing."""
    return """word,pinyin,translation
你好,nǐ hǎo
谢谢,xiè xiè,thank you,extra_column
苹果,píng guǒ,apple"""


@pytest.fixture
def sql_injection_attempts():
    """Common SQL injection patterns for testing."""
    return [
        "'; DROP TABLE users; --",
        "1' OR '1'='1",
        "UNION SELECT * FROM users--",
        "xp_cmdshell",
        "../../etc/passwd",
    ]


@pytest.fixture
def path_traversal_attempts():
    """Common path traversal patterns for testing."""
    return [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
        "/etc/shadow",
        "C:\\Windows\\System32\\config\\SAM",
        "file:///etc/passwd",
    ]


@pytest.fixture
def sample_dataframe():
    """Sample pandas DataFrame for testing."""
    return pd.DataFrame({
        'word': ['你好', '谢谢', '苹果'],
        'pinyin': ['nǐ hǎo', 'xiè xiè', 'píng guǒ'],
        'translation': ['hello', 'thank you', 'apple'],
        'frequency': [10, 8, 5]
    })


@pytest.fixture
def empty_dataframe():
    """Empty pandas DataFrame for testing."""
    return pd.DataFrame(columns=['word', 'pinyin', 'translation'])


@pytest.fixture
def malformed_csv_content():
    """Malformed CSV content for testing."""
    return """word,pinyin,translation
你好,nǐ hǎo,hello
谢谢,xiè xiè,"thank
you"
苹果,píng guǒ,apple"""


@pytest.fixture
def authenticated_api_client(db):
    user = get_user_model().objects.create_user(
        username="api-user",
        password="api-password",
    )
    token = Token.objects.create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client, user, token
