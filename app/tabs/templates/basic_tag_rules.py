"""Basic tag rules for Anki deck generation."""

DEFAULT_TAG_RULES_YAML = """
- static_tags:
    - "@AURCODE"
    - "PipelineDeck"
- prefix: "Category"
  # column: "categories" # Matches the CSV column
  split_by: ","
"""
