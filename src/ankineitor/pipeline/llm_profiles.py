"""Profile registry for LLM vocabulary generation prompts."""

from dataclasses import dataclass
from typing import Dict, List, Optional

DEFAULT_LLM_PROFILE_ID = "lotm_zh_en_es"


@dataclass(frozen=True)
class LLMProfile:
    """Configuration for a prompt profile used by LLMTransformation."""

    profile_id: str
    display_name: str
    description: str
    sentence_language: str
    secondary_target_language: Optional[str]
    prompt_template: str
    prompt_version: str

    def render_prompt(self, word: str) -> str:
        """Render the profile prompt by replacing supported placeholders."""
        return (
            self.prompt_template.replace("{word}", word)
            .replace("{sentence_language}", self.sentence_language)
            .replace("{secondary_target}", self.secondary_target_language or "")
        )


LOTM_ZH_EN_ES_PROMPT = """You are an expert language teacher creating advanced Anki flashcard data for a student learning Chinese specifically to read the web novel "Lord of the Mysteries" (诡秘之主).

Analyze the target word '{word}'.

Return a strictly valid JSON object matching this exact structure, with no markdown formatting or extra text outside the JSON:

{
  "word": "{word}",
  "pinyin": "Include tone marks (e.g., pīn yīn)",
  "part_of_speech": "Noun, Verb, Adjective, Particle, Proper Noun, Onomatopoeia, Phrase, etc.",
  "character_breakdown": "Break down the literal meaning of each individual character to help the learner remember the word (e.g., '手 = hand, 枪 = gun').",
  "detailed_explanation_english": "Provide a highly comprehensive explanation. Do not limit the length. If the word has multiple meanings, list ALL of them using bullet points formatted with escaped newlines (e.g., '\\n- [First meaning...] \\n- [Second meaning...]'). Include deep usage nuances, etymology, or cultural context if relevant.",
  "detailed_explanation_spanish": "Provide the same comprehensive explanation in Spanish, keeping the exact same bullet point formatting. (Leave as \"\" if {secondary_target} is not requested).",
  "synonyms": ["List Chinese synonyms. You determine the necessary and optimal number based on usefulness. Leave empty [] if none apply."],
  "antonyms": ["List Chinese antonyms. You determine the necessary and optimal number based on usefulness. Leave empty [] if none apply."],
  "collocations": ["List common, natural word pairings or short phrases. You determine the necessary and optimal number."],
  "edge_case_notes": "Explain grammatical quirks, the feeling conveyed by an onomatopoeia, or how a particle functions. Otherwise, leave empty.",
  "sentences": [
    {
      "target_language_highlighted": "Example sentence in {sentence_language} with the target word wrapped in HTML bold tags (e.g., '... <b>{word}</b> ...').",
      "target_language_cloze": "The exact same sentence, but the target word is replaced by '___' for fill-in-the-blank testing.",
      "sentence_pinyin": "Full pinyin with tone marks for the entire sentence.",
      "translation_english": "Natural English translation.",
      "translation_spanish": "Natural Spanish translation. (Leave as \"\" if not requested.)"
    }
  ]
}

Strict Constraints & Logic Rules:
1. Valid JSON: Ensure all strings are properly escaped. Do not use unescaped line breaks.
2. Thematic Context (LOTM): The example sentences MUST lean heavily into a dark, Victorian, Lovecraftian, steampunk, or mystic fantasy aesthetic. Subject matter should involve things like crimson moons, revolvers, secret organizations, potions, detectives, creeping madness, or the Beyonder world.
3. Contextual Difficulty (HSK 5): While the theme is dark fantasy, the grammatical structures and non-target vocabulary should generally align with the HSK 5 level to remain comprehensible.
4. Dynamic Sizing: YOU determine the length of the 'sentences', 'synonyms', 'antonyms', and 'collocations' arrays. Generate as many or as few as necessary based on the word's utility, polysemy, and complexity.
5. No Numbering or Labels: Do NOT number the sentences or the meanings. Never write prefixes like "Sentence 1:", "Meaning 1:", "1.", or "2.". Just output the raw bulleted text or the raw sentence directly.
6. Proper Nouns: If the word is a specific character name or location from the novel, identify it as a "Proper Noun", explain it thoroughly, and you may leave the arrays empty []."""


LLM_PROFILES: Dict[str, LLMProfile] = {
    DEFAULT_LLM_PROFILE_ID: LLMProfile(
        profile_id=DEFAULT_LLM_PROFILE_ID,
        display_name="LOTM: Chinese to English/Spanish",
        description=(
            "Chinese vocabulary profile for Lord of the Mysteries with detailed "
            "EN/ES explanations and thematic example sentences."
        ),
        sentence_language="Simplified Chinese",
        secondary_target_language="Spanish",
        prompt_template=LOTM_ZH_EN_ES_PROMPT,
        prompt_version="2026-02-21-v1",
    ),
}


def get_llm_profile(profile_id: Optional[str] = None) -> LLMProfile:
    """Get a registered profile, falling back to default when missing."""
    resolved = (profile_id or "").strip() or DEFAULT_LLM_PROFILE_ID
    return LLM_PROFILES.get(resolved, LLM_PROFILES[DEFAULT_LLM_PROFILE_ID])


def list_llm_profiles() -> List[LLMProfile]:
    """Return all available profiles in deterministic order."""
    return list(LLM_PROFILES.values())
