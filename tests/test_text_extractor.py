"""Unit tests for text extraction and segmentation logic."""

from typing import List, Tuple

import pytest

from ankineitor.pipeline import text_extractor as text_extractor_module
from ankineitor.pipeline.text_extractor import TextExtractor


class FakeElement:
    """Minimal stand-in for unstructured elements."""

    category = "Text"

    def __init__(self, text: str):
        self.text = text


class FakeHeader(FakeElement):
    """Header-like element that should be filtered."""

    category = "Header"


class FakeFooter(FakeElement):
    """Footer-like element that should be filtered."""

    category = "Footer"


class FakePageNumber(FakeElement):
    """Page number-like element that should be filtered."""

    category = "PageNumber"


class FakePosSeg:
    """Fake POS segmenter to validate fallback behavior."""

    def __init__(self, fallback_tokens: List[Tuple[str, str]]):
        self.calls = []
        self.fallback_tokens = fallback_tokens

    def cut(self, text: str, use_paddle: bool = False):  # noqa: ARG002
        self.calls.append(use_paddle)
        if use_paddle:
            raise RuntimeError("paddle mode unavailable")
        return self.fallback_tokens


class TestTextExtractor:
    """Tests for extraction and Chinese segmentation behavior."""

    def test_extract_content_preserves_duplicate_phrases(self, monkeypatch):
        monkeypatch.setattr(text_extractor_module, "UNSTRUCTURED_AVAILABLE", True)
        monkeypatch.setattr(text_extractor_module, "Header", FakeHeader)
        monkeypatch.setattr(text_extractor_module, "Footer", FakeFooter)
        monkeypatch.setattr(text_extractor_module, "PageNumber", FakePageNumber)

        def fake_partition(**kwargs):  # noqa: ARG001
            return [
                FakeHeader("页眉内容"),
                FakeElement("你好世界"),
                FakeElement("你好世界"),
                FakeFooter("页脚内容"),
                FakePageNumber("第1页"),
                FakeElement("再见朋友"),
            ]

        monkeypatch.setattr(text_extractor_module, "partition", fake_partition)

        extractor = TextExtractor({"source.txt": "dummy".encode("utf-8")})
        extractor.extract_content(min_phrase_len=2)

        assert extractor.phrases.count("你好世界") == 2
        assert "页眉内容" not in extractor.phrases
        assert "页脚内容" not in extractor.phrases
        assert "第1页" not in extractor.phrases

    def test_separated_characters_falls_back_when_paddle_fails(self, monkeypatch):
        fake_posseg = FakePosSeg(
            fallback_tokens=[
                ("你好", "n"),
                ("。", "x"),
                ("你好", "v"),
                ("谢谢", "n"),
                ("，", "x"),
            ]
        )

        monkeypatch.setattr(text_extractor_module, "JIEBA_AVAILABLE", True)
        monkeypatch.setattr(text_extractor_module, "pseg", fake_posseg)

        extractor = TextExtractor({"pasted_text.txt": "你好谢谢".encode("utf-8")})
        extractor.text = "你好。你好，谢谢"
        df = extractor.separated_chinese_characters()

        assert fake_posseg.calls == [True, False]
        assert set(df["word"].tolist()) == {"你好", "谢谢"}
        assert int(df.loc[df["word"] == "你好", "frequency"].iloc[0]) == 2
        assert df.loc[df["word"] == "你好", "part"].iloc[0] == "n, v"

    def test_extract_content_requires_unstructured_for_file_upload(self, monkeypatch):
        monkeypatch.setattr(text_extractor_module, "UNSTRUCTURED_AVAILABLE", False)
        monkeypatch.setattr(text_extractor_module, "partition", None)

        extractor = TextExtractor({"source.txt": "你好世界".encode("utf-8")})

        with pytest.raises(RuntimeError, match="requires the 'unstructured' package"):
            extractor.extract_content()

    def test_separated_characters_requires_jieba(self, monkeypatch):
        monkeypatch.setattr(text_extractor_module, "JIEBA_AVAILABLE", False)
        monkeypatch.setattr(text_extractor_module, "pseg", None)

        extractor = TextExtractor({"pasted_text.txt": "你好世界".encode("utf-8")})
        extractor.text = "你好世界"

        with pytest.raises(RuntimeError, match="requires the 'jieba' package"):
            extractor.separated_chinese_characters()
