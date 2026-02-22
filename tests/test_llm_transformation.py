"""Unit tests for Gemini-backed LLM transformation."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from ankineitor.pipeline.db_client import SQLAlchemyClient
from ankineitor.pipeline.llm_profiles import get_llm_profile
from ankineitor.pipeline.llm_transformation import (
    LLMTransformation,
    LLMWordPayload,
    SPRussianSentencePayload,
    SPRussianWordPayload,
    SentencePayload,
)
from ankineitor.security.exceptions import ValidationError


class TestLLMTransformationInit:
    def test_valid_token_initialization(self, mock_settings):
        mock_db_client = Mock()
        mock_settings.resolve_llm_api_token.return_value = "AQ.test_token_123"

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(
                    db_client=mock_db_client,
                    api_key="AQ.test_token_123",
                )
                assert transformation.api_key == "AQ.test_token_123"
                assert transformation.profile.profile_id == "lotm_zh_en_es"

    def test_missing_credentials_raises_validation_error(self, mock_settings):
        mock_db_client = Mock()
        mock_settings.resolve_llm_api_token.return_value = None
        mock_settings.bq_credentials_path = None
        mock_settings.vertex_credentials_path = None

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", side_effect=Exception("no creds")
            ):
                with pytest.raises(ValidationError, match="Gemini credentials are required"):
                    LLMTransformation(db_client=mock_db_client)

    def test_model_name_from_settings(self, mock_settings):
        mock_db_client = Mock()
        mock_settings.llm_model = "vertex_ai/gemini-3-flash-preview"

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                assert transformation.model_name == "gemini-3-flash-preview"

    def test_profile_db_path_derived_from_profile_id(self, mock_settings):
        mock_db_client = Mock()
        mock_settings.llm_cache_db_path = "data/ankineitor_llm_cache.db"

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                db_path = transformation._build_profile_db_path(
                    "LOTM: Chinese to English/Spanish"
                )
                assert db_path.endswith(
                    "ankineitor_llm_cache__lotm_chinese_to_english_spanish.db"
                )

    def test_profile_db_isolation_falls_back_to_mock_client(self, mock_settings):
        mock_db_client = Mock()

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                transformation.profile = get_llm_profile("lotm_zh_en_es")
                assert transformation._get_active_profile_db_client() is mock_db_client

    def test_profile_db_isolation_uses_profile_specific_sqlite(self, mock_settings, temp_dir):
        base_db = temp_dir / "ankineitor_llm_cache.db"
        mock_settings.llm_cache_db_path = str(base_db)
        base_client = SQLAlchemyClient(db_path=str(base_db))

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=base_client)
                transformation.profile = get_llm_profile("lotm_zh_en_es")
                profiled_client = transformation._get_active_profile_db_client()

                assert profiled_client is not base_client
                assert Path(profiled_client.engine.url.database).name == (
                    "ankineitor_llm_cache__lotm_zh_en_es.db"
                )


class TestLLMTransformationProcess:
    def test_column_name_property(self, mock_settings):
        mock_db_client = Mock()

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                assert transformation.column_name == "meaning_english"

    def test_build_profile_prompt_includes_word(self, mock_settings):
        mock_db_client = Mock()

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                prompt = transformation._build_profile_prompt("隐秘")
                assert "Analyze the target word '隐秘'" in prompt
                assert "Lord of the Mysteries" in prompt

    def test_build_sp_russian_prompt_includes_word(self, mock_settings):
        mock_db_client = Mock()
        mock_settings.llm_profile_id = "sp_russian"

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                prompt = transformation._build_profile_prompt("набережная")
                assert "Analyze the target Russian word 'набережная'" in prompt
                assert "Piter Summer Nightlife" in prompt

    def test_process_word_empty_returns_none(self, mock_settings):
        mock_db_client = Mock()

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                assert transformation.process_word("") is None
                assert transformation.process_word("   ") is None

    def test_cache_hit_avoids_generation_with_payload_json(self, mock_settings):
        mock_db_client = Mock()
        cached_payload = {
            "word": "隐秘",
            "pinyin": "yǐn mì",
            "part_of_speech": "Adjective",
            "character_breakdown": "隐 = hidden, 秘 = secret",
            "detailed_explanation_english": "hidden, secret, covert",
            "detailed_explanation_spanish": "oculto, secreto",
            "synonyms": ["秘密"],
            "antonyms": ["公开"],
            "collocations": ["隐秘组织"],
            "edge_case_notes": "",
            "sentences": [
                {
                    "target_language_highlighted": "他加入了<b>隐秘</b>组织。",
                    "target_language_cloze": "他加入了___组织。",
                    "sentence_pinyin": "tā jiā rù le yǐn mì zǔ zhī",
                    "translation_english": "He joined a secret organization.",
                    "translation_spanish": "Se unió a una organización secreta.",
                }
            ],
        }
        mock_db_client.find_record.return_value = {
            "word": "cache-key::隐秘",
            "improved_meaning": json.dumps(cached_payload, ensure_ascii=False),
            "example_sentences": json.dumps(cached_payload["sentences"], ensure_ascii=False),
            "sentence_1": "他加入了<b>隐秘</b>组织。",
            "meaning_english": "hidden",
            "meaning_spanish": "oculto",
        }

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                with patch.object(transformation, "_generate_structured_output") as mock_generate:
                    result = transformation.process_word("隐秘")
                    assert result is not None
                    assert result["meaning_english"] == "hidden, secret, covert"
                    assert result["sentence_1"] == "他加入了<b>隐秘</b>组织。"
                    assert result["sentence_1_tts_clean"] == "他加入了隐秘组织。"
                    mock_generate.assert_not_called()

    def test_cache_miss_generates_dynamic_sentences_and_saves(self, mock_settings):
        mock_db_client = Mock()
        mock_db_client.find_record.return_value = None

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)

                payload = LLMWordPayload(
                    word="隐秘",
                    pinyin="yǐn mì",
                    part_of_speech="Adjective",
                    character_breakdown="隐 = hidden, 秘 = secret",
                    detailed_explanation_english="hidden, secret, covert",
                    detailed_explanation_spanish="oculto, secreto, encubierto",
                    synonyms=["秘密", "隐蔽"],
                    antonyms=["公开"],
                    collocations=["隐秘组织", "隐秘行动"],
                    edge_case_notes="Often carries a mysterious tone in fiction.",
                    sentences=[
                        SentencePayload(
                            target_language_highlighted="在血月下，他听见<b>隐秘</b>仪式的低语。",
                            tts_clean_sentence="在血月下，他听见隐秘仪式的低语。",
                            target_language_cloze="在血月下，他听见___仪式的低语。",
                            sentence_pinyin="zài xuè yuè xià, tā tīng jiàn yǐn mì yí shì de dī yǔ",
                            translation_english="Under the crimson moon, he heard whispers of a secret ritual.",
                            translation_spanish="Bajo la luna carmesí, oyó susurros de un ritual secreto.",
                        ),
                        SentencePayload(
                            target_language_highlighted="侦探发现了教会档案里的<b>隐秘</b>线索。",
                            target_language_cloze="侦探发现了教会档案里的___线索。",
                            sentence_pinyin="zhēn tàn fā xiàn le jiào huì dàng àn lǐ de yǐn mì xiàn suǒ",
                            translation_english="The detective found hidden clues in the church archives.",
                            translation_spanish="El detective encontró pistas ocultas en los archivos de la iglesia.",
                        ),
                        SentencePayload(
                            target_language_highlighted="那瓶魔药揭开了他心中的<b>隐秘</b>恐惧。",
                            target_language_cloze="那瓶魔药揭开了他心中的___恐惧。",
                            sentence_pinyin="nà píng mó yào jiē kāi le tā xīn zhōng de yǐn mì kǒng jù",
                            translation_english="That potion uncovered his hidden fear.",
                            translation_spanish="Esa poción reveló su miedo oculto.",
                        ),
                        SentencePayload(
                            target_language_highlighted="组织用暗号传递<b>隐秘</b>命令。",
                            target_language_cloze="组织用暗号传递___命令。",
                            sentence_pinyin="zǔ zhī yòng àn hào chuán dì yǐn mì mìng lìng",
                            translation_english="The organization used code words to pass covert orders.",
                            translation_spanish="La organización usó claves para transmitir órdenes encubiertas.",
                        ),
                    ],
                )

                with patch.object(
                    transformation,
                    "_generate_structured_output",
                    return_value=payload,
                ):
                    result = transformation.process_word("隐秘")
                    assert result is not None
                    assert result["word"] == "隐秘"
                    assert result["meaning_english"] == "hidden, secret, covert"
                    assert result["sentence_1"] is not None
                    assert result["sentence_1_tts_clean"] == "在血月下，他听见隐秘仪式的低语。"
                    assert result["sentence_4"] is not None
                    assert result["sentence_4_tts_clean"] == "组织用暗号传递隐秘命令。"
                    assert result["sentence_4_translation_english"] is not None
                    assert result["sentences_json"]
                    mock_db_client.insert_record.assert_called_once()

    def test_sp_russian_payload_maps_tts_clean_sentences(self, mock_settings):
        mock_db_client = Mock()
        mock_db_client.find_record.return_value = None
        mock_settings.llm_profile_id = "sp_russian"

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)

                payload = SPRussianWordPayload(
                    word="набережная",
                    word_with_stress="набережна́я",
                    romanization="naberezhnáya",
                    part_of_speech="Noun (Feminine)",
                    aspect_pair="",
                    morphological_breakdown="на- + берег + -н- + -ая",
                    register="Standard",
                    grammar_formula="",
                    detailed_explanation_english="riverside embankment",
                    detailed_explanation_spanish="malecón / paseo junto al río",
                    mnemonic_hook_spanish="Nave beresina en la bahía.",
                    piter_summer_variant="Meeting point during White Nights.",
                    synonyms=["проме́над"],
                    antonyms=[],
                    collocations=["гуля́ть по набережно́й"],
                    edge_case_notes="Common in urban social planning.",
                    sentences=[
                        SPRussianSentencePayload(
                            target_language_highlighted="В ию́ле мы встре́тились на <b>набережно́й</b> пе́ред клу́бом.",
                            tts_clean_sentence="В июле мы встретились на набережной перед клубом.",
                            target_language_cloze="В ию́ле мы встре́тились на ___ пе́ред клу́бом.",
                            sentence_romanization="V iyúle my vstrétilis' na naberezhnóy pered klúbom.",
                            translation_english="In July we met on the embankment before the club.",
                            translation_spanish="En julio nos encontramos en la ribera antes del club.",
                        )
                    ],
                )

                with patch.object(
                    transformation,
                    "_generate_structured_output",
                    return_value=payload,
                ):
                    result = transformation.process_word("набережная")
                    assert result is not None
                    assert result["word_with_stress"] == "набережна́я"
                    assert result["pinyin"] is None
                    assert result["translation"] is None
                    assert result["sentence_1_tts_clean"] == (
                        "В июле мы встретились на набережной перед клубом."
                    )
                    assert result["sentence_1_romanization"] is not None

    def test_process_word_handles_generation_error(self, mock_settings):
        mock_db_client = Mock()
        mock_db_client.find_record.return_value = None

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                with patch.object(
                    transformation,
                    "_generate_structured_output",
                    side_effect=RuntimeError("boom"),
                ):
                    assert transformation.process_word("隐秘") is None


class TestLLMTransformationApply:
    def test_apply_requires_word_column(self, mock_settings):
        mock_db_client = Mock()

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                df = pd.DataFrame({"other_column": ["test"]})
                result = transformation.apply(df)
                assert result.equals(df)

    def test_apply_with_no_successful_results_returns_original(self, mock_settings):
        mock_db_client = Mock()

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)
                transformation.process_word = Mock(return_value=None)
                df = pd.DataFrame({"word": ["你好", "谢谢"]})
                result = transformation.apply(df)
                assert result.equals(df)

    def test_apply_with_partial_results_merges_output(self, mock_settings):
        mock_db_client = Mock()

        with patch(
            "ankineitor.pipeline.llm_transformation.get_settings",
            return_value=mock_settings,
        ):
            with patch.object(
                LLMTransformation, "_build_genai_client", return_value=Mock()
            ):
                transformation = LLMTransformation(db_client=mock_db_client)

                def mock_process(word):
                    if word == "你好":
                        return {
                            "word": "你好",
                            "sentence_1": "你好，世界。",
                            "sentence_1_cloze": "___，世界。",
                            "meaning_english": "hello",
                            "sentences_json": "[]",
                        }
                    return None

                transformation.process_word = mock_process
                df = pd.DataFrame({"word": ["你好", "谢谢"]})
                result = transformation.apply(df)
                assert len(result) == 2
                assert "meaning_english" in result.columns
                assert "sentence_1_cloze" in result.columns
                assert (
                    result.loc[result["word"] == "你好", "meaning_english"].iloc[0]
                    == "hello"
                )
