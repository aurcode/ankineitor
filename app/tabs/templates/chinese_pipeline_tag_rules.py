"""Chinese pipeline tag rules for Anki deck generation."""

CHINESE_PIPELINE_TAG_RULES_YAML = """
- static_tags:
    - "Chinese"
    - "Pipeline"
- prefix: "Category"
  # column: "categories" # Matches the CSV column # This is giving error for it im commenting, fix in the future
  split_by: ","
  # Cleans up the "['...']" format from the CSV
  strip: ' []''"' 
"""
