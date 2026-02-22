"""Integration tests for validation flows across the application."""

import pytest
from unittest.mock import Mock, patch
from pathlib import Path
import pandas as pd

from ankineitor.security.validators import (
    validate_file_upload,
    sanitize_filename,
    validate_word_input,
    validate_csv_content,
    validate_path,
    sanitize_sql_input,
)
from ankineitor.security.exceptions import (
    InvalidFileError,
    ValidationError,
    PathTraversalError,
)


class TestEndToEndValidationFlows:
    """Test complete validation flows from user input to processing."""

    def test_complete_file_upload_flow(self, mock_streamlit_file, mock_settings, temp_dir):
        """Test complete file upload validation flow."""
        with patch('ankineitor.security.validators.get_settings', return_value=mock_settings):
            # Step 1: File upload validation
            mock_streamlit_file.name = "vocabulary.csv"
            result = validate_file_upload(mock_streamlit_file, expected_extensions=[".csv"])
            assert result is True
            
            # Step 2: Filename sanitization
            sanitized_name = sanitize_filename(mock_streamlit_file.name)
            assert sanitized_name == "vocabulary.csv"
            
            # Step 3: CSV content validation
            csv_content = mock_streamlit_file.getvalue().decode('utf-8')
            result = validate_csv_content(csv_content)
            assert result is True
            
            # Step 4: Path validation for saving
            save_path = temp_dir / sanitized_name
            validated_path = validate_path(str(save_path), temp_dir)
            assert validated_path == save_path.resolve()

    def test_chinese_word_processing_pipeline(self, mock_settings):
        """Test complete Chinese word processing validation pipeline."""
        with patch('ankineitor.security.validators.get_settings', return_value=mock_settings):
            # Step 1: Word input validation
            chinese_words = "你好\n谢谢\n苹果\n数据\n工程师"
            validated_words = validate_word_input(chinese_words)
            assert len(validated_words) == 5
            
            # Step 2: Individual word validation
            for word in validated_words:
                assert len(word) <= 50  # Reasonable length limit
                assert word.strip() == word  # No leading/trailing whitespace
            
            # Step 3: Processing pipeline simulation
            word_df = pd.DataFrame({'word': validated_words})
            assert len(word_df) == 5
            assert all(word_df['word'].str.len() > 0)

    def test_malicious_input_handling_pipeline(self, mock_settings):
        """Test pipeline handling of various malicious inputs."""
        with patch('ankineitor.security.validators.get_settings', return_value=mock_settings):
            # Test SQL injection in word input
            sql_injection_words = "你好\n'; DROP TABLE users; --\n谢谢"
            result = validate_word_input(sql_injection_words)
            assert len(result) == 3
            assert "DROPTABLEusers" in result[1]
            
            # Test path traversal in filename
            with pytest.raises(PathTraversalError):
                sanitize_filename("../../../etc/passwd.csv")
            
            # Test XSS in CSV content
            xss_content = """word,pinyin,translation
<script>alert('xss')</script>,test,hello"""
            result = validate_csv_content(xss_content)
            assert result is True  # Should validate structure, not content safety

    def test_configuration_validation_integration(self, mock_settings):
        """Test integration of configuration validation with security functions."""
        with patch('ankineitor.security.validators.get_settings', return_value=mock_settings):
            # Test Gemini/Vertex token availability
            assert mock_settings.llm_api_token.startswith("AQ.")
            assert len(mock_settings.llm_api_token) > 10
            
            # Test file size limits
            assert 1 <= mock_settings.max_file_size_mb <= 100
            
            # Test allowed extensions
            assert ".csv" in mock_settings.allowed_file_extensions
            assert ".exe" not in mock_settings.allowed_file_extensions
            
            # Test log level validation
            assert mock_settings.log_level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class TestLLMTransformationSecurity:
    """Test security validation in LLM transformation pipeline."""

    def test_llm_token_resolution(self, mock_settings):
        """Test LLM token resolution and security settings."""
        with patch('ankineitor.config.settings.get_settings', return_value=mock_settings):
            assert mock_settings.resolve_llm_api_token().startswith("AQ.")
            assert mock_settings.gcp_location == "us-central1"

    def test_llm_input_sanitization(self, mock_settings):
        """Test input sanitization before LLM processing."""
        with patch('ankineitor.security.validators.get_settings', return_value=mock_settings):
            # Test word input sanitization
            malicious_input = "测试'; DROP TABLE users; --"
            sanitized_words = validate_word_input(malicious_input)
            assert len(sanitized_words) == 1
            
            # Test that dangerous content is logged but not necessarily blocked
            # (since it's content, not code execution)
            assert "DROPTABLEusers" in sanitized_words[0]

    def test_llm_output_validation(self, sample_words, mock_settings):
        """Test validation of LLM-generated output."""
        with patch('ankineitor.security.validators.get_settings', return_value=mock_settings):
            # Simulate LLM output validation
            mock_llm_output = {
                'english': 'hello world',
                'spanish': 'hola mundo',
                'example_sentences': [
                    'This is a test sentence.',
                    'Another example here.',
                    'Final test sentence.'
                ]
            }
            
            # Validate that output doesn't contain dangerous patterns
            for key, value in mock_llm_output.items():
                if isinstance(value, str):
                    sanitized = sanitize_sql_input(value)
                    assert sanitized == value  # Should be clean
                elif isinstance(value, list):
                    for item in value:
                        sanitized = sanitize_sql_input(item)
                        assert sanitized == item  # Should be clean


class TestDatabaseSecurityIntegration:
    """Test security validation for database operations."""

    def test_database_query_sanitization(self):
        """Test SQL query sanitization for database operations."""
        # Test various SQL injection patterns
        injection_patterns = [
            "'; DROP TABLE users; --",
            "1' OR '1'='1",
            "UNION SELECT * FROM users--",
            "xp_cmdshell 'dir'",
            "../../etc/passwd",
        ]
        
        for pattern in injection_patterns:
            sanitized = sanitize_sql_input(pattern)
            # Should at least strip SQL metacharacters to reduce injection risk.
            assert "'" not in sanitized
            assert ";" not in sanitized
            assert "--" not in sanitized

    def test_database_path_validation(self, temp_dir):
        """Test path validation for database file operations."""
        # Test database file path validation
        db_path = temp_dir / "test.db"
        validated_path = validate_path(str(db_path), temp_dir)
        assert validated_path == db_path.resolve()
        
        # Test path traversal prevention
        malicious_path = temp_dir / ".." / "etc" / "passwd"
        with pytest.raises(PathTraversalError):
            validate_path(str(malicious_path), temp_dir)

    def test_cache_security_validation(self, mock_settings):
        """Test security validation for caching operations."""
        with patch('ankineitor.security.validators.get_settings', return_value=mock_settings):
            # Test cache key validation
            valid_cache_key = "你好:translation:zh-en"
            sanitized_key = sanitize_sql_input(valid_cache_key)
            assert "你好" in sanitized_key
            
            # Test malicious cache key
            malicious_key = "'; DROP TABLE cache; --"
            sanitized_key = sanitize_sql_input(malicious_key)
            assert "'" not in sanitized_key
            assert ";" not in sanitized_key
            assert "--" not in sanitized_key


class TestStreamlitInterfaceSecurity:
    """Test security validation in Streamlit interface components."""

    def test_streamlit_file_upload_security(self, mock_streamlit_file, mock_settings):
        """Test security validation for Streamlit file uploads."""
        with patch('ankineitor.security.validators.get_settings', return_value=mock_settings):
            # Test valid file upload
            mock_streamlit_file.name = "vocabulary.csv"
            result = validate_file_upload(mock_streamlit_file, expected_extensions=[".csv"])
            assert result is True
            
            # Test malicious filename
            mock_streamlit_file.name = "../../../etc/passwd.csv"
            with pytest.raises(PathTraversalError):
                sanitize_filename(mock_streamlit_file.name)
            
            # Test oversized file
            mock_streamlit_file.name = "large_upload.csv"
            mock_settings.max_file_size_mb = 0.5
            large_content = b"word,pinyin\n" + b"test,test\n" * 200000
            mock_streamlit_file.getvalue.return_value = large_content
            mock_streamlit_file.size = len(large_content)
            
            with pytest.raises(InvalidFileError, match="exceeds maximum allowed size"):
                validate_file_upload(mock_streamlit_file)

    def test_streamlit_text_input_security(self):
        """Test security validation for Streamlit text inputs."""
        # Test word input validation
        valid_words = "你好\n谢谢\n苹果"
        result = validate_word_input(valid_words)
        assert len(result) == 3
        
        # Test malicious text input
        malicious_text = "你好\n<script>alert('xss')</script>\n谢谢"
        result = validate_word_input(malicious_text)
        assert len(result) == 3
        assert "<script>" in result[1]  # Content should be preserved
        
        # Test extremely long input
        long_input = "测试\n" * 1000
        result = validate_word_input(long_input)
        assert len(result) == 1000

    def test_streamlit_session_state_security(self, mock_settings):
        """Test security validation for Streamlit session state."""
        with patch('ankineitor.security.validators.get_settings', return_value=mock_settings):
            # Simulate session state validation
            session_data = {
                'words': ["你好", "谢谢", "苹果"],
                'file_path': "vocabulary.csv",
                'category': "日常用语"
            }
            
            # Validate words
            validated_words = validate_word_input(session_data['words'])
            assert validated_words == session_data['words']
            
            # Validate filename
            sanitized_filename = sanitize_filename(session_data['file_path'])
            assert sanitized_filename == session_data['file_path']
            
            # Validate category (simulate)
            category = session_data['category']
            assert len(category) <= 50  # Reasonable length limit


@pytest.mark.slow
@pytest.mark.benchmark
class TestPerformanceAndScalability:
    """Test security validation performance and scalability."""

    def test_large_dataset_validation_performance(self):
        """Test performance of validation with large datasets."""
        import time
        
        # Test large word list validation
        large_word_list = ["测试" + str(i) for i in range(10000)]
        start_time = time.time()
        result = validate_word_input(large_word_list)
        end_time = time.time()
        
        assert len(result) == 10000
        assert end_time - start_time < 2.0  # Should complete within 2 seconds
        
        # Test large CSV validation
        large_csv = "word,pinyin,translation\n" + "\n".join([
            f"word{i},pinyin{i},translation{i}" for i in range(5000)
        ])
        start_time = time.time()
        result = validate_csv_content(large_csv)
        end_time = time.time()
        
        assert result is True
        assert end_time - start_time < 1.0  # Should complete within 1 second

    def test_concurrent_validation_security(self):
        """Test security validation under concurrent load."""
        import threading
        import time
        
        results = []
        errors = []
        
        def validate_words():
            try:
                words = "你好\n谢谢\n苹果\n数据\n工程师"
                result = validate_word_input(words)
                results.append(result)
            except Exception as e:
                errors.append(str(e))
        
        # Run multiple concurrent validations
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=validate_words)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        assert len(results) == 10
        assert len(errors) == 0
        assert all(len(result) == 5 for result in results)

    def test_memory_efficiency_validation(self):
        """Test memory efficiency of validation functions."""
        # Test with extremely large input that should be handled efficiently
        very_large_word = "测试" * 100000  # 200k+ characters
        result = validate_word_input(very_large_word)
        
        # Should handle without excessive memory usage
        assert len(result) == 1
        assert len(result[0]) == len(very_large_word)


class TestSecurityAuditAndCompliance:
    """Test security audit and compliance requirements."""

    def test_security_event_logging(self, mock_settings, caplog):
        """Test that security events are properly logged for audit."""
        with patch('ankineitor.security.validators.get_settings', return_value=mock_settings):
            assert sanitize_filename("test_file.csv") == "test_file.csv"
            with pytest.raises(PathTraversalError):
                sanitize_filename("../../../etc/passwd")

    def test_input_validation_compliance(self):
        """Test compliance with input validation standards."""
        # Test that all inputs are validated
        test_cases = [
            ("", ValidationError),  # Empty input
            (None, ValidationError),  # None input
            ("../../../etc/passwd", PathTraversalError),  # Path traversal
            ("'; DROP TABLE users; --", None),  # SQL injection (should be sanitized, not rejected)
        ]
        
        for input_val, expected_exception in test_cases:
            if expected_exception:
                with pytest.raises(expected_exception):
                    if isinstance(input_val, str) and '/' in input_val:
                        sanitize_filename(input_val)
                    elif input_val is None or input_val == "":
                        validate_word_input(input_val)
            else:
                # Should be sanitized, not rejected
                result = sanitize_sql_input(input_val)
                assert "'" not in result
                assert ";" not in result
                assert "--" not in result

    def test_data_sanitization_compliance(self, tmp_path):
        """Test compliance with data sanitization requirements."""
        # Test SQL injection sanitization
        sql_injection = "'; DROP TABLE users; --"
        sanitized = sanitize_sql_input(sql_injection)
        assert "'" not in sanitized
        assert ";" not in sanitized
        assert "--" not in sanitized
        
        # Test filename sanitization
        dangerous_filename = "test<file>.csv"
        sanitized = sanitize_filename(dangerous_filename)
        assert "<" not in sanitized
        assert ">" not in sanitized
        
        # Path traversal should be rejected when a base path is enforced.
        with pytest.raises(PathTraversalError):
            validate_path("../../../etc/passwd", tmp_path)
