from __future__ import annotations

from typing import Any, List

from rest_framework import serializers

from ankineitor.pipeline.llm_profiles import DEFAULT_LLM_PROFILE_ID, get_llm_profile
from ankineitor.security import ValidationError as InputValidationError
from ankineitor.security import validate_word_input

from .models import BackgroundJob, BackgroundJobEvent, PipelineResultRow, PipelineRun, PipelineRunEvent

HIDDEN_RESULT_COLUMNS = {"pinyin", "translation"}


class PipelineRunCreateSerializer(serializers.Serializer):
    profile_id = serializers.CharField(required=False, default=DEFAULT_LLM_PROFILE_ID, max_length=128)
    transform_names = serializers.ListField(
        child=serializers.CharField(max_length=128),
        required=False,
        allow_empty=True,
    )
    words = serializers.JSONField(required=True)

    def validate_profile_id(self, value: str) -> str:
        profile = get_llm_profile(value)
        if profile.profile_id != value and value != DEFAULT_LLM_PROFILE_ID:
            raise serializers.ValidationError(f"Unknown profile_id '{value}'.")
        return profile.profile_id

    def validate_words(self, value: Any) -> List[str]:
        try:
            words = validate_word_input(value)
        except InputValidationError as exc:
            raise serializers.ValidationError(str(exc))
        except Exception as exc:
            raise serializers.ValidationError(str(exc))

        if len(words) > 1000:
            raise serializers.ValidationError(
                f"Maximum 1000 words per run. Received {len(words)} words."
            )
        return words


class PipelineRunRerunBlockSerializer(serializers.Serializer):
    transform_name = serializers.CharField(max_length=128)


class PipelineRunSummarySerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(format="hex_verbose")
    event_count = serializers.SerializerMethodField()

    def get_event_count(self, obj: PipelineRun) -> int:
        annotated_event_count = getattr(obj, "event_count", None)
        if annotated_event_count is not None:
            try:
                return int(annotated_event_count)
            except Exception:
                pass
        return obj.events.count()

    class Meta:
        model = PipelineRun
        fields = [
            "id",
            "status",
            "profile_id",
            "source_language",
            "selected_transform_names",
            "ordered_transform_names",
            "total_input_words",
            "error_message",
            "csv_output_path",
            "csv_download_name",
            "total_duration_seconds",
            "counters",
            "slowest_steps",
            "created_at",
            "started_at",
            "completed_at",
            "event_count",
        ]


class PipelineRunEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = PipelineRunEvent
        fields = [
            "id",
            "run",
            "sequence",
            "event_type",
            "stage",
            "transform_name",
            "payload",
            "created_at",
        ]


class PipelineResultRowSerializer(serializers.ModelSerializer):
    row_data = serializers.SerializerMethodField()

    def get_row_data(self, obj: PipelineResultRow) -> dict:
        payload = {
            str(key): value
            for key, value in dict(obj.row_data or {}).items()
            if str(key) not in HIDDEN_RESULT_COLUMNS
        }
        existing_timestamp = str(payload.get("timestamp", "") or "").strip()
        if not existing_timestamp and obj.created_at:
            payload["timestamp"] = obj.created_at.isoformat()
        return payload

    class Meta:
        model = PipelineResultRow
        fields = ["row_index", "word", "row_data"]


class BackgroundJobSummarySerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(format="hex_verbose")

    class Meta:
        model = BackgroundJob
        fields = [
            "id",
            "job_type",
            "status",
            "progress_ratio",
            "status_text",
            "result_payload",
            "csv_output_path",
            "csv_download_name",
            "celery_task_id",
            "error_message",
            "created_at",
            "started_at",
            "completed_at",
        ]


class BackgroundJobEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = BackgroundJobEvent
        fields = [
            "id",
            "job",
            "sequence",
            "event_type",
            "payload",
            "created_at",
        ]


class AddCategorySerializer(serializers.Serializer):
    category = serializers.CharField(max_length=50)


class AuthTokenRequestSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(max_length=128, trim_whitespace=False)


class AnkiDeckGenerateSerializer(serializers.Serializer):
    deck_name = serializers.CharField(max_length=120)
    config = serializers.JSONField()


class FlashcardDatasetFromSavedSerializer(serializers.Serializer):
    profile_id = serializers.CharField(max_length=128)
    file_name = serializers.CharField(max_length=255, required=False, allow_blank=True)


class FlashcardCardQuerySerializer(serializers.Serializer):
    index = serializers.IntegerField(min_value=0, required=False, default=0)
    profile_filter = serializers.CharField(max_length=128, required=False, allow_blank=True)


class FlashcardCardUpdateSerializer(serializers.Serializer):
    index = serializers.IntegerField(min_value=0, required=False, default=0)
    profile_filter = serializers.CharField(max_length=128, required=False, allow_blank=True)
    updates = serializers.DictField(required=True)

    def validate_updates(self, value: Any) -> dict:
        if not isinstance(value, dict):
            raise serializers.ValidationError("updates must be an object.")
        if not value:
            raise serializers.ValidationError("Provide at least one field in updates.")
        if len(value) > 200:
            raise serializers.ValidationError("Too many updated fields (max 200).")

        normalized: dict = {}
        for raw_key, raw_item in value.items():
            key = str(raw_key or "").strip()
            if not key:
                continue
            if len(key) > 128:
                raise serializers.ValidationError(f"Field name '{key}' is too long (max 128).")
            normalized[key] = raw_item

        if not normalized:
            raise serializers.ValidationError("Provide at least one valid field key.")
        return normalized


class FlashcardCardRerunSerializer(serializers.Serializer):
    index = serializers.IntegerField(min_value=0, required=False, default=0)
    profile_filter = serializers.CharField(max_length=128, required=False, allow_blank=True)
    mode = serializers.ChoiceField(choices=["full", "image"], required=False, default="full")


class GeneratedRowListQuerySerializer(serializers.Serializer):
    search = serializers.CharField(max_length=256, required=False, allow_blank=True)
    profile_id = serializers.CharField(max_length=128, required=False, allow_blank=True)
    run_id = serializers.UUIDField(required=False)


class GeneratedRowUpdateSerializer(serializers.Serializer):
    updates = serializers.DictField(required=True)

    def validate_updates(self, value: Any) -> dict:
        if not isinstance(value, dict):
            raise serializers.ValidationError("updates must be an object.")
        if not value:
            raise serializers.ValidationError("Provide at least one field in updates.")
        if len(value) > 200:
            raise serializers.ValidationError("Too many updated fields (max 200).")

        normalized: dict = {}
        for raw_key, raw_item in value.items():
            key = str(raw_key or "").strip()
            if not key:
                continue
            if len(key) > 128:
                raise serializers.ValidationError(f"Field name '{key}' is too long (max 128).")
            normalized[key] = raw_item

        if not normalized:
            raise serializers.ValidationError("Provide at least one valid field key.")
        return normalized


class GeneratedRowRerunSerializer(serializers.Serializer):
    process = serializers.ChoiceField(
        choices=[
            "full",
            "meaning_sentences",
            "audio_word",
            "audio_sentences",
            "image_prompt",
            "image_renderer",
            "image",
        ],
        required=False,
        default="full",
    )


class WordExtractorAnalyzeSerializer(serializers.Serializer):
    text_input = serializers.CharField(required=False, allow_blank=True, default="")
    selected_hsk_levels = serializers.ListField(
        child=serializers.CharField(max_length=16),
        required=False,
        allow_empty=True,
        default=list,
    )
    min_frequency = serializers.IntegerField(min_value=1, required=False, default=2)
