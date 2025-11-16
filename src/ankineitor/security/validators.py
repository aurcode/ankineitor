"""Input validation and sanitization utilities."""

import re
import csv
import io
from pathlib import Path
from typing import List, Union
import pandas as pd
from loguru import logger

from .exceptions import InvalidFileError, ValidationError, PathTraversalError
from ..config import get_settings


def validate_file_upload(file_obj, expected_extensions: List[str] = None) -> bool:
    """
    Validate uploaded file for security and integrity.
    
    Args:
        file_obj: Streamlit UploadedFile object
        expected_extensions: List of allowed file extensions
        
    Returns:
        bool: True if file is valid
        
    Raises:
        InvalidFileError: If file validation fails
    """
    settings = get_settings()
    
    if not file_obj:
        raise InvalidFileError("No file provided")
    
    # Check file size
    file_size_mb = len(file_obj.getvalue()) / (1024 * 1024)
    if file_size_mb > settings.max_file_size_mb:
        raise InvalidFileError(
            f"File size ({file_size_mb:.1f}MB) exceeds maximum allowed size "
            f"({settings.max_file_size_mb}MB)"
        )
    
    # Validate filename
    filename = sanitize_filename(file_obj.name)
    
    # Check file extension
    if expected_extensions:
        file_ext = Path(filename).suffix.lower()
        if file_ext not in expected_extensions:
            raise InvalidFileError(
                f"Invalid file extension '{file_ext}'. Allowed: {expected_extensions}",
                filename
            )
    
    # Content-based validation for CSV files
    if filename.lower().endswith('.csv'):
        try:
            content = file_obj.getvalue().decode('utf-8')
            validate_csv_content(content)
        except UnicodeDecodeError:
            raise InvalidFileError("CSV file must be UTF-8 encoded", filename)
        except Exception as e:
            raise InvalidFileError(f"Invalid CSV format: {str(e)}", filename)
    
    logger.info(f"File validation passed: {filename} ({file_size_mb:.1f}MB)")
    return True


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal and injection attacks.
    
    Args:
        filename: Original filename
        
    Returns:
        str: Sanitized filename
        
    Raises:
        PathTraversalError: If path traversal is detected
    """
    if not filename:
        raise ValidationError("Filename cannot be empty")
    
    # Remove path traversal attempts
    if '..' in filename or '/' in filename or '\\' in filename:
        raise PathTraversalError("Path traversal detected in filename")
    
    # Remove dangerous characters
    sanitized = re.sub(r'[<>:\"|?*\x00-\x1f]', '', filename)
    sanitized = sanitized.strip()
    
    if not sanitized:
        raise ValidationError("Filename contains only invalid characters")
    
    # Limit length
    max_length = 255
    if len(sanitized) > max_length:
        name_part = Path(sanitized).stem[:max_length-10]
        ext_part = Path(sanitized).suffix
        sanitized = name_part + ext_part
    
    return sanitized


def validate_word_input(words: Union[str, List[str]]) -> List[str]:
    """
    Validate and sanitize Chinese word input.
    
    Args:
        words: Input words as string or list
        
    Returns:
        List[str]: Validated and cleaned words
        
    Raises:
        ValidationError: If input validation fails
    """
    if isinstance(words, str):
        # Split by newlines and clean
        word_list = [word.strip() for word in words.split('\n') if word.strip()]
    elif isinstance(words, list):
        word_list = [str(word).strip() for word in words if word and str(word).strip()]
    else:
        raise ValidationError("Words must be string or list of strings")
    
    if not word_list:
        raise ValidationError("No valid words provided")
    
    # Validate each word
    validated_words = []
    for word in word_list:
        # Remove excessive whitespace
        word = re.sub(r'\s+', '', word)
        
        # Check for suspicious patterns
        if len(word) > 50:  # Reasonable limit for Chinese words
            logger.warning(f"Suspiciously long word detected: {word[:20]}...")
        
        # Check for non-Chinese characters (allow some punctuation)
        if re.search(r'[a-zA-Z0-9]{3,}', word):
            logger.warning(f"Word contains suspicious Latin characters: {word}")
        
        if word:  # Only add non-empty words
            validated_words.append(word)
    
    if not validated_words:
        raise ValidationError("No valid Chinese words found after validation")
    
    logger.info(f"Validated {len(validated_words)} words")
    return validated_words


def validate_csv_content(content: str, max_rows: int = 10000) -> bool:
    """
    Validate CSV content for security and format.
    
    Args:
        content: CSV content as string
        max_rows: Maximum allowed rows
        
    Returns:
        bool: True if CSV is valid
        
    Raises:
        InvalidFileError: If CSV validation fails
    """
    try:
        # Parse CSV
        csv_reader = csv.reader(io.StringIO(content))
        rows = list(csv_reader)
        
        if not rows:
            raise InvalidFileError("CSV file is empty")
        
        if len(rows) > max_rows:
            raise InvalidFileError(
                f"CSV file has too many rows ({len(rows)}). Maximum: {max_rows}"
            )
        
        # Check for reasonable column count
        header_row = rows[0]
        if len(header_row) > 50:
            raise InvalidFileError(
                f"Too many columns ({len(header_row)}). Maximum: 50"
            )
        
        # Validate column names
        for col_name in header_row:
            if not isinstance(col_name, str):
                raise InvalidFileError("Column names must be strings")
            if len(col_name) > 100:
                raise InvalidFileError("Column names too long")
            # Check for suspicious characters in column names
            if re.search(r'[<>\"\'&]', col_name):
                logger.warning(f"Suspicious characters in column name: {col_name}")
        
        # Sample data validation (check first few rows)
        sample_size = min(10, len(rows) - 1)
        for i in range(1, sample_size + 1):
            if len(rows[i]) != len(header_row):
                logger.warning(
                    f"Row {i} has different column count than header: "
                    f"{len(rows[i])} vs {len(header_row)}"
                )
        
        logger.info(f"CSV validation passed: {len(rows)} rows, {len(header_row)} columns")
        return True
        
    except csv.Error as e:
        raise InvalidFileError(f"CSV parsing error: {str(e)}")
    except Exception as e:
        raise InvalidFileError(f"CSV validation error: {str(e)}")


def validate_path(path_str: str, base_path: Union[str, Path] = None) -> Path:
    """
    Validate file path to prevent directory traversal.
    
    Args:
        path_str: Path string to validate
        base_path: Base directory path for validation
        
    Returns:
        Path: Validated and resolved path
        
    Raises:
        PathTraversalError: If path traversal is detected
    """
    try:
        path = Path(path_str).resolve()
        
        # Check for path traversal
        if '..' in str(path):
            raise PathTraversalError("Path traversal detected")
        
        # Check against base path if provided
        if base_path:
            base_path = Path(base_path).resolve()
            try:
                path.relative_to(base_path)
            except ValueError:
                raise PathTraversalError(
                    f"Path '{path}' is outside allowed base directory '{base_path}'"
                )
        
        # Additional security checks
        if path.is_absolute() and not str(path).startswith(str(Path.cwd())):
            logger.warning(f"Absolute path outside current directory: {path}")
        
        return path
        
    except Exception as e:
        if isinstance(e, PathTraversalError):
            raise
        raise PathTraversalError(f"Invalid path: {str(e)}")


def sanitize_sql_input(value: str) -> str:
    """
    Basic SQL injection prevention by sanitizing input.
    
    Note: This is a basic implementation. Always use parameterized queries
    when possible instead of string concatenation.
    
    Args:
        value: Input string to sanitize
        
    Returns:
        str: Sanitized string
    """
    if not isinstance(value, str):
        return str(value)
    
    # Remove SQL metacharacters
    dangerous_chars = ["'", '"', ';', '--', '/*', '*/', 'xp_', 'sp_']
    sanitized = value
    
    for char in dangerous_chars:
        sanitized = sanitized.replace(char, '')
    
    # Remove multiple whitespace
    sanitized = re.sub(r'\s+', ' ', sanitized).strip()
    
    return sanitized
