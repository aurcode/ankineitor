"""Chinese pipeline configuration for Anki deck generation."""

from .chinese_pipeline_templates import CHINESE_PIPELINE_MODEL_TEMPLATES_YAML
from .chinese_pipeline_tag_rules import CHINESE_PIPELINE_TAG_RULES_YAML

# --- NEW: Full Configuration for the "Chinese Pipeline" Button ---
# This dictionary contains all the settings for your specific CSV
CHINESE_PIPELINE_SETUP = {
    "model_id": 20251110,  # New custom ID for this model
    "model_name": "Chinese Pipeline Model (Full)",
    "deck_id": 20251111,
    "note_type": "Chinese (Pipeline)",
    # 1. Anki Model Fields: All the fields in the Anki note
    "model_fields": [
        {"name": "Word"},  # Front
        {"name": "Pinyin"},
        {"name": "English Meaning"},
        {"name": "Spanish Meaning"},
        {"name": "Audio"},
        {"name": "Image"},
        {"name": "Example 1"},
        {"name": "Example 2"},
        {"name": "Example 3"},
        {"name": "Example 1 Audio"},
        {"name": "Example 2 Audio"},
        {"name": "Example 3 Audio"},
        {"name": "All Sentences"},
        {"name": "Part of Speech"},
        {"name": "Character Breakdown"},
        {"name": "Detailed Explanation (EN)"},
        {"name": "Detailed Explanation (ES)"},
        {"name": "Synonyms"},
        {"name": "Antonyms"},
        {"name": "Collocations"},
        {"name": "Edge Case Notes"},
        {"name": "Translation (Extras)"},
        {"name": "Categories"},
        {"name": "Timestamp"},
    ],
    # 2. CSV Column Mapping: Connects CSV columns to Anki fields (in order)
    "model_builder": [
        {"csv_column": "word"},
        {"csv_column": "pinyin"},
        {"csv_column": "meaning_english"},
        {"csv_column": "meaning_spanish"},
        {"csv_column": "audio"},
        {"csv_column": "picture"},
        {"csv_column": "sentence_1"},
        {"csv_column": "sentence_2"},
        {"csv_column": "sentence_3"},
        {"csv_column": "sentence_1_audio"},
        {"csv_column": "sentence_2_audio"},
        {"csv_column": "sentence_3_audio"},
        {"csv_column": "sentences_rendered_html"},
        {"csv_column": "part_of_speech"},
        {"csv_column": "character_breakdown"},
        {"csv_column": "detailed_explanation_english"},
        {"csv_column": "detailed_explanation_spanish"},
        {"csv_column": "synonyms_rendered"},
        {"csv_column": "antonyms_rendered"},
        {"csv_column": "collocations_rendered"},
        {"csv_column": "edge_case_notes"},
        {"csv_column": "translation"},
        {"csv_column": "categories"},
        {"csv_column": "timestamp"},
    ],
    # 3. Media Fields: Tells the generator which columns are files
    "media_fields": [
        {"column_name": "audio", "media_type": "audio"},
        {"column_name": "picture", "media_type": "image"},
        {"column_name": "sentence_1_audio", "media_type": "audio"},
        {"column_name": "sentence_2_audio", "media_type": "audio"},
        {"column_name": "sentence_3_audio", "media_type": "audio"},
    ],
    # 4. "Beautiful Template" (YAML for Templates + CSS)
    "model_templates_yaml": CHINESE_PIPELINE_MODEL_TEMPLATES_YAML,
    # 5. Tag Rules: Auto-generates tags from the 'categories' column
    "tag_rules_yaml": CHINESE_PIPELINE_TAG_RULES_YAML,
}
