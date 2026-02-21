"""Secure configuration management using Pydantic settings."""

import os
import json
from typing import Optional
from pydantic import validator
from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    """Secure application settings with validation."""
    
    # API Keys
    llm_api_token: Optional[str] = None
    gemini_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    
    # Database settings
    pipeline_db_path: str = "data/ankineitor_pipeline.db"
    llm_cache_db_path: str = "data/ankineitor_llm_cache.db"
    
    # Audio settings
    audio_output_dir: str = "./my_audio_files"
    image_output_dir: str = "./my_image_files"
    
    # LLM settings
    llm_model: str = "gemini-3-flash-preview"
    llm_image_prompt_model: str = "gemini-3-flash-preview"
    llm_image_master_prompt_template: Optional[str] = None
    llm_image_do_not_generate_terms: list = [
        "与",
        "一个",
        "不会",
        "而",
        "于",
        "以",
        "以及",
        "想要",
        "觉",
        "之",
        "之中",
        "可",
        "心头",
        "一阵",
        "难以",
        "大半夜",
        "嘶",
        "看来",
        "将",
        "下意识",
        "这时",
        "下方",
        "一下",
        "连通",
        "半个",
    ]
    llm_image_model: str = "gemini-3-pro-image-preview"
    llm_image_max_workers: int = 1
    llm_source_language: str = "Chinese (Simplified)"
    llm_target_language: str = "english"
    llm_secondary_target_language: Optional[str] = None
    llm_max_retries: int = 3
    llm_timeout: int = 30
    gcp_project_id: Optional[str] = None
    gcp_location: str = "us-central1"
    bq_credentials_path: Optional[str] = None
    vertex_credentials_path: Optional[str] = None
    
    # Security settings
    max_file_size_mb: int = 10
    allowed_file_extensions: list = [".csv", ".txt", ".pdf", ".docx", ".pptx"]
    
    # Application settings
    log_level: str = "INFO"
    dev_mode: bool = False
    
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

    @validator("llm_image_do_not_generate_terms", pre=True)
    def parse_llm_image_do_not_generate_terms(cls, v):
        """Parse blocked image terms from JSON list or comma-separated string."""
        if isinstance(v, str):
            cleaned = v.strip()
            if not cleaned:
                return []
            if cleaned.startswith("["):
                try:
                    parsed = json.loads(cleaned)
                    if isinstance(parsed, list):
                        return parsed
                except Exception:
                    pass
            return [term.strip() for term in cleaned.split(",") if term.strip()]
        return v
    
    def ensure_directories(self):
        """Ensure required directories exist."""
        directories = [
            Path(self.pipeline_db_path).parent,
            Path(self.llm_cache_db_path).parent,
            Path(self.audio_output_dir),
            Path(self.image_output_dir),
            Path("logs"),
            Path("output"),
            Path("data"),
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def resolve_llm_api_token(self) -> Optional[str]:
        """
        Resolve LLM token using the same alias precedence as the private agent.
        """
        candidates = [
            self.llm_api_token,
            self.gemini_api_key,
            self.google_api_key,
            os.getenv("VERTEX_API_TOKEN"),
            os.getenv("GCP_API_TOKEN"),
            os.getenv("GOOGLE_CLOUD_ACCESS_TOKEN"),
        ]
        for candidate in candidates:
            if candidate and candidate.strip():
                return candidate.strip()
        return None
    
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
