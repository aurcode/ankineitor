"""Profile registry for LLM vocabulary generation prompts."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

LOTM_ZH_EN_ES_PROFILE_ID = "lotm_zh_en_es"
SP_RUSSIAN_PROFILE_ID = "sp_russian"
SP_SPANISH_STANDARD_PROFILE_ID = "sp_spanish_standard"
DEFAULT_LLM_PROFILE_ID = SP_SPANISH_STANDARD_PROFILE_ID

LOTM_SCHEMA_ID = "lotm_v1"
SP_RUSSIAN_SCHEMA_ID = "sp_russian_v1"
SP_SPANISH_SCHEMA_ID = "sp_spanish_v1"


@dataclass(frozen=True)
class LLMProfile:
    """Configuration for a prompt profile used by LLMTransformation."""

    profile_id: str
    display_name: str
    description: str
    source_language: str
    sentence_language: str
    secondary_target_language: Optional[str]
    supports_images: bool
    prompt_template: str
    prompt_version: str
    response_schema: str
    default_tts_voice_id: Optional[str] = None
    tts_voice_pool: Tuple[str, ...] = ()
    always_include_audio_transforms: bool = False
    default_optional_transform_names: Tuple[str, ...] = ()

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
      "tts_clean_sentence": "The exact target language sentence with NO HTML tags and NO markdown. Keep natural Simplified Chinese text only so it can be used for TTS audio generation.",
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
6. Proper Nouns: If the word is a specific character name or location from the novel, identify it as a "Proper Noun", explain it thoroughly, and you may leave the arrays empty [].
7. TTS Field Required: Every sentence object MUST include `tts_clean_sentence`, which must exactly match the sentence content but without HTML tags."""


SP_RUSSIAN_PROMPT = """You are an expert language teacher creating advanced Anki flashcard data for a student learning Russian, specifically tailored for socializing, nightlife, clubbing, and partying with friends during the summer in St. Petersburg.

Analyze the target Russian word '{word}'.

Return a strictly valid JSON object matching this exact structure, with no markdown formatting or extra text outside the JSON:

{
  "word": "{word}",
  "word_with_stress": "The target word with the acute accent mark for stress (e.g., тусо́вка). MANDATORY for all Russian words.",
  "romanization": "Provide the Latin alphabet transliteration of the word, including the stress mark.",
  "part_of_speech": "Noun (include Gender), Verb (include Aspect), Adjective, Adverb, Particle, Preposition, etc.",
  "aspect_pair": "If the word is a verb, provide its Perfective/Imperfective counterpart. If not a verb, leave empty \"\".",
  "morphological_breakdown": "Break down the word into prefix, root, suffix, and ending to help the learner understand its core meaning.",
  "register": "Categorize the word strictly as: 'Standard', 'Informal Slang', 'Rude', or 'Vulgar/Mat'. Explain who it is safe to use this with.",
  "grammar_formula": "If the word dictates a specific grammatical case (e.g., verb + Accusative, or preposition + Dative), write the formula here. Otherwise, leave empty \"\".",
  "detailed_explanation_english": "Provide a highly comprehensive, extended explanation. Cover all edge cases thoroughly. If the word has multiple meanings, list ALL of them using bullet points formatted with escaped newlines (e.g., '\\n- [First meaning...] \\n- [Second meaning...]'). Include deep usage nuances or slang context.",
  "detailed_explanation_spanish": "Provide the same comprehensive, extended explanation in Spanish, keeping the exact same bullet point formatting.",
  "mnemonic_hook_spanish": "Create a short, memorable, and slightly absurd mental hook linking the pronunciation of the Russian word strictly to Spanish words or phrases.",
  "piter_summer_variant": "Explain how this concept adapts specifically to summer nightlife in St. Petersburg (e.g., White Nights, boat parties, terrace bars). If a St. Petersburg regional slang equivalent exists, provide it here.",
  "synonyms": ["List Russian synonyms with stress marks. You determine the optimal number. Leave empty [] if none apply."],
  "antonyms": ["List Russian antonyms with stress marks. You determine the optimal number. Leave empty [] if none apply."],
  "collocations": ["List common, natural word pairings or short phrases (with stress marks), especially those used in party settings. E.g., which verbs pair with this drink?"],
  "edge_case_notes": "Provide a longer explanation managing any edge cases. Explain grammatical quirks, slang derivations, or shifting stress in different cases.",
  "sentences": [
    {
      "target_language_highlighted": "Example sentence in Russian with the target word wrapped in HTML bold tags (e.g., '... <b>{word}</b> ...'). INCLUDE STRESS MARKS on all words of multiple syllables.",
      "tts_clean_sentence": "The exact target language sentence with NO HTML tags, NO stress marks, and NO markdown. Just the raw, natural Cyrillic text for Text-to-Speech audio generation.",
      "target_language_cloze": "The exact same sentence, but the target word is replaced by '___' for fill-in-the-blank testing.",
      "sentence_romanization": "Full Latin transliteration of the example sentence, keeping the stress marks.",
      "translation_english": "Natural English translation.",
      "translation_spanish": "Natural Spanish translation."
    }
  ]
}

Strict Constraints & Logic Rules:
1. Valid JSON: Ensure all strings are properly escaped. Do not use unescaped line breaks.
2. Thematic Context (Piter Summer Nightlife): The example sentences MUST lean heavily into casual socializing, drinking, and partying specifically during the summer in St. Petersburg. Subject matter should involve things like terrace bars, the White Nights, getting a taxi after the bridges open, splitting the bill, or weekend plans in July.
3. Contextual Difficulty & Tone (Casual / Slang): Grammatical structures should align with intermediate-to-advanced Russian (B1-B2 level), but the vocabulary and tone must reflect real-life, spoken Russian. Use appropriate modern slang.
4. Dynamic Sizing: YOU determine the length of the 'sentences', 'synonyms', 'antonyms', and 'collocations' arrays. Generate as many or as few as necessary based on the word's utility.
5. No Numbering or Labels: Do NOT number the sentences or the meanings. Never write prefixes like "Sentence 1:" or "1.". Just output the raw bulleted text or the raw sentence directly.
6. Proper Nouns: If the word is a specific place, identify it as a "Proper Noun", explain it thoroughly, and you may leave the arrays empty [].
7. Russian Stress Marks: You must include acute accents (´) on the stressed vowel of every Russian word that has more than one syllable, across all Cyrillic and Romanized fields (except tts_clean_sentence)."""


SP_SPANISH_STANDARD_PROMPT = """You are an expert language teacher creating advanced Anki flashcard data for a student learning Spanish for standard, everyday communication (espanol estandar y cotidiano), with practical real-life usage.

Analyze the target Spanish word '{word}'.

Return a strictly valid JSON object matching this exact structure, with no markdown formatting or extra text outside the JSON:

{
  "word": "{word}",
  "lemma": "Dictionary base form. For verbs use infinitive (e.g., 'ir', 'ponerse').",
  "pronunciation_ipa": "IPA pronunciation in neutral modern Spanish.",
  "syllabification_and_stress": "Split into syllables and indicate stress type (aguda/llana/esdrujula/sobreesdrujula), e.g., 'ca-mi-NAR (aguda)'.",
  "part_of_speech": "Noun (include gender), Verb (include transitivity/reflexive behavior), Adjective, Adverb, Connector, Interjection, etc.",
  "morphological_breakdown": "Break into meaningful parts (prefix/root/suffix/clitic) when useful. If not useful, explain briefly why.",
  "register": "Categorize strictly as one of: 'Standard', 'Colloquial', 'Informal Slang', 'Rude', 'Vulgar'. Also explain safe usage context.",
  "regional_scope": "Indicate whether usage is Pan-Hispanic or region-specific (Spain, Mexico, River Plate, Caribbean, etc.).",
  "grammar_formula": "If the word requires a structure, write it (e.g., 'depender de + sustantivo/infinitivo', 'ponerse + adjetivo'). Otherwise leave ''.",
  "ser_estar_note": "If relevant, clarify ser vs estar implications; otherwise ''.",
  "por_para_note": "If relevant, clarify por vs para implications; otherwise ''.",
  "reflexive_variant": "If applicable, contrast non-reflexive vs reflexive meaning (e.g., 'ir' vs 'irse'). Otherwise ''.",
  "irregular_forms": ["List only key irregular forms when relevant (e.g., present yo form, preterite stem, participle). Leave [] if not applicable."],
  "detailed_explanation_english": "Provide a comprehensive explanation. If multiple meanings/usages exist, list ALL with bullet points formatted with escaped newlines (e.g., '\\n- [Meaning 1...] \\n- [Meaning 2...]'). Include nuance, pragmatics, and common contexts.",
  "detailed_explanation_spanish": "Provide the same explanation in clear, learner-friendly Spanish (not too advanced), preserving the same bullet formatting.",
  "common_mistakes": ["List common learner mistakes and how to avoid them. Include confusion cases (false friends, prepositions, wrong register)."],
  "synonyms": ["List Spanish synonyms that are natural in real life. Include regional limits when needed."],
  "antonyms": ["List Spanish antonyms when meaningful; otherwise []"],
  "collocations": ["List common collocations and short chunks used in daily speech."],
  "edge_case_notes": "Handle edge cases explicitly: accent/diacritic contrasts (tu/tú, el/él), meaning shifts by region, politeness/register risks, or grammatical traps. If none, leave ''.",
  "sentences": [
    {
      "target_language_highlighted": "Example sentence in Spanish with the target word wrapped in HTML bold tags (e.g., '... <b>{word}</b> ...').",
      "tts_clean_sentence": "Exact same sentence with NO HTML tags and NO markdown, natural Spanish for TTS.",
      "target_language_cloze": "Exact same sentence but target word replaced by '___'.",
      "sentence_pronunciation_hint": "Short pronunciation aid only if needed (liaison, stress pitfall, or silent letters). Otherwise ''.",
      "translation_english": "Natural English translation.",
      "translation_spanish": "Simple Spanish paraphrase for learner reinforcement."
    }
  ]
}

Strict Constraints & Logic Rules:
1. Valid JSON only: all strings properly escaped, no unescaped line breaks.
2. Context must be practical daily life: errands, work/study, friends, family, transport, shopping, appointments, online chat, etc.
3. Tone should prioritize standard + cotidiano Spanish. Use slang only when truly common and clearly label register/region.
4. Dynamic sizing: YOU choose the useful number of sentences/synonyms/antonyms/collocations/common_mistakes.
5. No numbering labels in generated content (never output 'Meaning 1', 'Sentence 1', '1.', etc.).
6. Proper nouns: tag as Proper Noun, explain usage, and you may leave arrays empty [] if appropriate.
7. Orthography precision: accents and punctuation must be correct in Spanish output.
8. Edge-case priority:
   - Distinguish homographs/diacritic pairs where relevant.
   - Clarify reflexive vs non-reflexive meaning shifts.
   - Clarify preposition-governing patterns.
   - Flag regional-only forms and provide neutral alternative if possible.
9. Safety/register: if word can sound rude/vulgar, explicitly warn and provide safer alternatives.
10. TTS field required: every sentence object MUST include 'tts_clean_sentence'."""


LLM_PROFILES: Dict[str, LLMProfile] = {
    SP_SPANISH_STANDARD_PROFILE_ID: LLMProfile(
        profile_id=SP_SPANISH_STANDARD_PROFILE_ID,
        display_name="Spanish Standard/Cotidiano",
        description=(
            "Spanish standard everyday learner profile with practical usage, "
            "EN/ES explanations, edge cases, and daily-life sentence coverage."
        ),
        source_language="Spanish",
        sentence_language="Spanish",
        secondary_target_language="Spanish",
        supports_images=True,
        prompt_template=SP_SPANISH_STANDARD_PROMPT,
        prompt_version="2026-02-24-v1",
        response_schema=SP_SPANISH_SCHEMA_ID,
        default_tts_voice_id="Upset Girl - Soft,Airy,Sweet",
        always_include_audio_transforms=True,
    ),
    LOTM_ZH_EN_ES_PROFILE_ID: LLMProfile(
        profile_id=LOTM_ZH_EN_ES_PROFILE_ID,
        display_name="LOTM: Chinese to English/Spanish",
        description=(
            "Chinese vocabulary profile for Lord of the Mysteries with detailed "
            "EN/ES explanations and thematic example sentences."
        ),
        source_language="Chinese (Simplified)",
        sentence_language="Simplified Chinese",
        secondary_target_language="Spanish",
        supports_images=True,
        prompt_template=LOTM_ZH_EN_ES_PROMPT,
        prompt_version="2026-02-21-v1",
        response_schema=LOTM_SCHEMA_ID,
        default_tts_voice_id="Chinese (Mandarin)_Mature_Woman",
        always_include_audio_transforms=True,
    ),
    SP_RUSSIAN_PROFILE_ID: LLMProfile(
        profile_id=SP_RUSSIAN_PROFILE_ID,
        display_name="SP Russian",
        description=(
            "Russian nightlife/social vocabulary for Saint Petersburg summers "
            "with EN/ES explanations, stress marks, spoken usage, and Victorian-style imagery."
        ),
        source_language="Russian",
        sentence_language="Russian",
        secondary_target_language="Spanish",
        supports_images=True,
        prompt_template=SP_RUSSIAN_PROMPT,
        prompt_version="2026-02-21-v1",
        response_schema=SP_RUSSIAN_SCHEMA_ID,
        default_tts_voice_id="Russian_HandsomeChildhoodFriend",
        always_include_audio_transforms=True,
    ),
}


def get_llm_profile(profile_id: Optional[str] = None) -> LLMProfile:
    """Get a registered profile, falling back to default when missing."""
    resolved = (profile_id or "").strip() or DEFAULT_LLM_PROFILE_ID
    return LLM_PROFILES.get(resolved, LLM_PROFILES[DEFAULT_LLM_PROFILE_ID])


def list_llm_profiles() -> List[LLMProfile]:
    """Return all available profiles in deterministic order."""
    return list(LLM_PROFILES.values())
