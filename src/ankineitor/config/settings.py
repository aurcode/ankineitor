"""Secure configuration management using Pydantic settings."""

import os
from typing import Optional
from pydantic import validator
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """Secure application settings with validation."""
    
    # API Keys
    groq_api_key: Optional[str] = None
    
    # Database settings
    pipeline_db_path: str = "data/ankineitor_pipeline.db"
    llm_cache_db_path: str = "data/ankineitor_llm_cache.db"
    
    # Audio settings
    audio_output_dir: str = "./my_audio_files"
    
    # LLM settings
    llm_model: str = "llama-3.3-70b-versatile"
    llm_max_retries: int = 3
    llm_timeout: int = 30
    
    # Security settings
    max_file_size_mb: int = 10
    allowed_file_extensions: list = [".csv", ".txt", ".pdf", ".docx", ".pptx"]
    
    # Application settings
    log_level: str = "INFO"
    dev_mode: bool = False
    
    @validator("groq_api_key")
    def validate_api_key(cls, v):
        """Validate API key format."""
        if v and not v.startswith("gsk_"):
            raise ValueError("Invalid Groq API key format")
        return v
    
    @validator("max_file_size_mb")
    def validate_file_size(cls, v):
        """Validate file size limits."""
        if v <= 0 or v > 100:
            raise ValueError("File size must be between 1 and 100 MB")
        return v
    
    @validator("log_level")
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level. Must be one of: {valid_levels}")
        return v.upper()
    
    @validator("allowed_file_extensions", pre=True)
    def parse_allowed_extensions(cls, v):
        """Parse allowed file extensions from string or list."""
        if isinstance(v, str):
            # Split comma-separated string and clean up extensions
            extensions = [ext.strip() for ext in v.split(",")]
            # Ensure each extension starts with a dot
            return [ext if ext.startswith(".") else f".{ext}" for ext in extensions]
        elif isinstance(v, list):
            # Ensure each extension in the list starts with a dot
            return [ext if ext.startswith(".") else f".{ext}" for ext in v]
        return v
    
    def ensure_directories(self):
        """Ensure required directories exist."""
        directories = [
            Path(self.pipeline_db_path).parent,
            Path(self.llm_cache_db_path).parent,
            Path(self.audio_output_dir),
            Path("logs"),
            Path("output"),
            Path("data"),
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# Global settings instance
_settings = None


def get_settings() -> Settings:
    """Get application settings (singleton pattern)."""
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_directories()
    return _settings
