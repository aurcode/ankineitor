"""
Pydantic models for validating the Anki deck generator configuration.
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class BasicsConfig(BaseModel):
    """Schema for the 'basics' section of the config."""

    model_id: int
    model_name: str
    deck_id: int
    note_type: str


class ModelFieldSchema(BaseModel):
    """Schema for a single field in the Anki model."""

    name: str


class MediaField(BaseModel):
    """Schema for a single media field mapping."""

    column_name: str
    media_type: str  # 'audio', 'image', or 'video'


class TagRule(BaseModel):
    """Schema for a single tag generation rule."""

    prefix: Optional[str] = None
    column: Optional[str] = None
    split_by: Optional[str] = None
    static_tags: Optional[List[str]] = None
    strip_chars: Optional[str] = None


class AnkiConfig(BaseModel):
    """Root schema for the entire configuration file."""

    basics: BasicsConfig
    model_fields: List[ModelFieldSchema]
    model_templates: Dict[str, Any]
    model_builder: List[str]
    media_fields: List[MediaField] = Field(default_factory=list)
    tag_rules: List[TagRule] = Field(default_factory=list)
