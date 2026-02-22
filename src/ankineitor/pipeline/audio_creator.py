import base64
import hashlib
import json
import os
import re
from typing import Optional
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

import pandas as pd
from loguru import logger
from tqdm import tqdm

from ..config import get_settings


LANGUAGE_TO_TTS_CODE = {
    "english": "en",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "portuguese": "pt",
    "italian": "it",
    "chinesesimplified": "zh-CN",
    "simplifiedchinese": "zh-CN",
    "chinese": "zh-CN",
    "japanese": "ja",
    "korean": "ko",
    "hindi": "hi",
    "arabic": "ar",
    "russian": "ru",
    "turkish": "tr",
    "vietnamese": "vi",
    "indonesian": "id",
}

TTS_CODE_TO_MINIMAX_LANGUAGE = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "it": "Italian",
    "zhcn": "Chinese",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "hi": "Hindi",
    "ar": "Arabic",
    "ru": "Russian",
    "tr": "Turkish",
    "vi": "Vietnamese",
    "id": "Indonesian",
}

MINIMAX_DEFAULT_MODEL = "speech-2.8-hd"
MINIMAX_DEFAULT_BASE_URL = "https://api.minimaxi.com"
MINIMAX_DEFAULT_VOICE_ID = "Chinese (Mandarin)_Mature_Woman"
MINIMAX_DEFAULT_TIMEOUT_SECONDS = 60


def _normalize_language_name(value: Optional[str]) -> str:
    if not value:
        return ""
    cleaned = str(value).strip().lower()
    return re.sub(r"[\s_\-()]+", "", cleaned)


def _normalize_tts_code(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"[\s_\-()]+", "", str(value).strip().lower())


class AudioCreator:
    """
    Creates and saves audio files from text strings using MiniMax TTS.

    Caches files based on a hash of text + voice/model/language to avoid re-generation.
    """

    def __init__(self, folder_name: Optional[str] = None, language: str = "zh"):
        default_path = os.getenv("AUDIO_PATH", "./audio")
        self.folder_name = folder_name if folder_name is not None else default_path
        self.language = language
        os.makedirs(self.folder_name, exist_ok=True)

        settings = get_settings()
        env_token = os.getenv("MINIMAX_API_TOKEN")
        self.minimax_api_token = (
            (settings.minimax_api_token or env_token or "").strip() or None
        )
        self.minimax_group_id = (
            (settings.minimax_group_id or os.getenv("MINIMAX_GROUP_ID") or "").strip()
            or None
        )
        self.minimax_model = (
            (settings.minimax_tts_model or MINIMAX_DEFAULT_MODEL).strip()
            or MINIMAX_DEFAULT_MODEL
        )
        self.minimax_voice_id = (
            (settings.minimax_tts_voice_id or os.getenv("MINIMAX_TTS_VOICE_ID") or "").strip()
            or MINIMAX_DEFAULT_VOICE_ID
        )
        self.minimax_base_url = (
            (settings.minimax_tts_base_url or MINIMAX_DEFAULT_BASE_URL).strip().rstrip("/")
            or MINIMAX_DEFAULT_BASE_URL
        )
        self.minimax_timeout_seconds = max(
            1, int(settings.minimax_tts_timeout_seconds or MINIMAX_DEFAULT_TIMEOUT_SECONDS)
        )

        logger.info(f"AudioCreator initialized. Saving files to: {self.folder_name}")

    def resolve_tts_language(self, source_language: Optional[str] = None) -> str:
        """
        Resolve a short TTS language code from a source language label.
        Falls back to the instance default language when unknown.
        """
        normalized = _normalize_language_name(source_language)
        if normalized in LANGUAGE_TO_TTS_CODE:
            return LANGUAGE_TO_TTS_CODE[normalized]
        raw = (source_language or "").strip()
        normalized_code = _normalize_tts_code(raw)
        if normalized_code in TTS_CODE_TO_MINIMAX_LANGUAGE:
            return raw
        return self.language

    def _resolve_minimax_language(self, tts_code: str) -> str:
        normalized = _normalize_tts_code(tts_code)
        return TTS_CODE_TO_MINIMAX_LANGUAGE.get(normalized, "Auto")

    def _get_filename(self, text: str, language: str) -> str:
        signature = "|".join(
            [
                text,
                language,
                self.minimax_model,
                self.minimax_voice_id,
            ]
        )
        hash_id = hashlib.sha256(signature.encode("utf-8")).hexdigest()
        return f"{hash_id[:20]}-{language}.mp3"

    def _build_request_url(self) -> str:
        base_url = f"{self.minimax_base_url}/v1/t2a_v2"
        if not self.minimax_group_id:
            return base_url
        query = urllib_parse.urlencode({"GroupId": self.minimax_group_id})
        return f"{base_url}?{query}"

    def _build_payload(self, text: str, tts_code: str) -> dict:
        language_boost = self._resolve_minimax_language(tts_code)
        return {
            "model": self.minimax_model,
            "text": text,
            "stream": False,
            "voice_setting": {
                "voice_id": self.minimax_voice_id,
                "speed": 1.0,
                "vol": 1.0,
                "pitch": 0,
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1,
            },
            "language_boost": language_boost,
        }

    def _decode_audio_from_json(self, payload: dict) -> bytes:
        base_resp = payload.get("base_resp")
        if isinstance(base_resp, dict):
            status_code = base_resp.get("status_code")
            if status_code not in (0, None):
                status_msg = base_resp.get("status_msg") or "unknown error"
                raise RuntimeError(f"MiniMax API error {status_code}: {status_msg}")

        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("MiniMax response missing 'data' object.")

        audio_data = data.get("audio")
        if isinstance(audio_data, str) and audio_data.strip():
            value = audio_data.strip()
            try:
                return bytes.fromhex(value)
            except ValueError:
                try:
                    return base64.b64decode(value, validate=True)
                except Exception as exc:
                    raise RuntimeError("MiniMax response audio payload is not decodable.") from exc

        audio_url = data.get("audio_url")
        if isinstance(audio_url, str) and audio_url.strip():
            return self._download_binary(audio_url.strip())

        raise RuntimeError("MiniMax response missing audio content.")

    def _download_binary(self, url: str) -> bytes:
        req = urllib_request.Request(url, method="GET")
        with urllib_request.urlopen(req, timeout=self.minimax_timeout_seconds) as response:
            return response.read()

    def _request_tts_audio(self, text: str, tts_code: str) -> bytes:
        if not self.minimax_api_token:
            raise RuntimeError("MINIMAX_API_TOKEN is not configured.")

        url = self._build_request_url()
        payload = self._build_payload(text=text, tts_code=tts_code)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.minimax_api_token}",
        }
        req = urllib_request.Request(url=url, data=body, headers=headers, method="POST")

        try:
            with urllib_request.urlopen(req, timeout=self.minimax_timeout_seconds) as response:
                raw = response.read()
                content_type = str(response.headers.get("Content-Type", "")).lower()
                if "application/json" not in content_type:
                    # Fallback in case API returns binary audio directly.
                    return raw
                payload = json.loads(raw.decode("utf-8"))
                return self._decode_audio_from_json(payload)
        except urllib_error.HTTPError as exc:
            raw_error = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"MiniMax HTTP error {exc.code}: {raw_error[:500]}"
            ) from exc

    def _create_audio(self, text: str, language: Optional[str] = None) -> Optional[str]:
        if not text or not any(ch.isalnum() for ch in text):
            return None

        tts_language = self.resolve_tts_language(language)
        file_name = self._get_filename(text=text, language=tts_language)
        audio_file_path = os.path.join(self.folder_name, file_name)

        if os.path.exists(audio_file_path):
            return audio_file_path

        try:
            audio_bytes = self._request_tts_audio(text=text, tts_code=tts_language)
            with open(audio_file_path, "wb") as f:
                f.write(audio_bytes)
            logger.debug(f"Audio created: {audio_file_path}")
            return audio_file_path
        except Exception as e:
            logger.error(f"Error creating audio for text '{text[:40]}...': {e}")
            return None

    def create_audios_for_series(
        self, texts: pd.Series, language: Optional[str] = None
    ) -> pd.Series:
        logger.info(f"Starting audio file creation for {len(texts)} items...")
        tqdm.pandas(desc="Generating Audio")
        paths = texts.progress_apply(
            lambda text: self._create_audio(text, language=language)
        )
        logger.info("Audio file creation complete.")
        return paths
