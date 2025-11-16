"""Templates package for Anki deck generation."""

from .basic_model_templates import DEFAULT_MODEL_TEMPLATES_YAML
from .basic_tag_rules import DEFAULT_TAG_RULES_YAML
from .chinese_pipeline_config import CHINESE_PIPELINE_SETUP
from .chinese_pipeline_templates import CHINESE_PIPELINE_MODEL_TEMPLATES_YAML
from .chinese_pipeline_tag_rules import CHINESE_PIPELINE_TAG_RULES_YAML

__all__ = [
    "DEFAULT_MODEL_TEMPLATES_YAML",
    "DEFAULT_TAG_RULES_YAML", 
    "CHINESE_PIPELINE_SETUP",
    "CHINESE_PIPELINE_MODEL_TEMPLATES_YAML",
    "CHINESE_PIPELINE_TAG_RULES_YAML",
]
