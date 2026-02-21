"""Unit tests for core pipeline transformations."""

import pandas as pd

from ankineitor.pipeline.transformations import PinyinTransformation, AudioTransformation


def test_pinyin_transformation_only_generates_for_chinese_words():
    transform = PinyinTransformation()
    df = pd.DataFrame({"word": ["你好", "hola", "hello", "数据"]})

    result = transform.apply(df)

    assert "pinyin" in result.columns
    assert isinstance(result.loc[0, "pinyin"], str)
    assert result.loc[0, "pinyin"].strip() != ""
    assert result.loc[1, "pinyin"] is None
    assert result.loc[2, "pinyin"] is None
    assert isinstance(result.loc[3, "pinyin"], str)
    assert result.loc[3, "pinyin"].strip() != ""


def test_pinyin_transformation_disabled_for_non_chinese_source_language():
    transform = PinyinTransformation(source_language="Spanish")
    df = pd.DataFrame({"word": ["你好", "数据"]})

    result = transform.apply(df)

    assert result["pinyin"].isna().all()


def test_audio_transformation_uses_source_language_tts_code():
    class StubAudioCreator:
        def __init__(self):
            self.last_language = None

        def resolve_tts_language(self, source_language):
            return "es"

        def create_audios_for_series(self, texts, language=None):
            self.last_language = language
            return texts.map(lambda _: "/tmp/fake.mp3")

    creator = StubAudioCreator()
    transform = AudioTransformation(audio_creator=creator, source_language="Spanish")
    df = pd.DataFrame({"word": ["hola"]})

    result = transform.apply(df)

    assert creator.last_language == "es"
    assert result.loc[0, "audio"] == "/tmp/fake.mp3"
