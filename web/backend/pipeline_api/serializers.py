from __future__ import annotations

from typing import Any, List

from rest_framework import serializers

from ankineitor.pipeline.llm_profiles import DEFAULT_LLM_PROFILE_ID, get_llm_profile
from ankineitor.security import ValidationError as InputValidationError
from ankineitor.security import validate_word_input

from .models import PipelineResultRow, PipelineRun, PipelineRunEvent


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


class PipelineRunSummarySerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(format="hex_verbose")
    event_count = serializers.SerializerMethodField()

    def get_event_count(self, obj: PipelineRun) -> int:
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
    class Meta:
        model = PipelineResultRow
        fields = ["row_index", "word", "row_data"]


class AddCategorySerializer(serializers.Serializer):
    category = serializers.CharField(max_length=50)


class AnkiDeckGenerateSerializer(serializers.Serializer):
    deck_name = serializers.CharField(max_length=120)
    config = serializers.JSONField()


class FlashcardDatasetFromSavedSerializer(serializers.Serializer):
    profile_id = serializers.CharField(max_length=128)
    file_name = serializers.CharField(max_length=255, required=False, allow_blank=True)


class FlashcardCardQuerySerializer(serializers.Serializer):
    index = serializers.IntegerField(min_value=0, required=False, default=0)
    profile_filter = serializers.CharField(max_length=128, required=False, allow_blank=True)


class WordExtractorAnalyzeSerializer(serializers.Serializer):
    text_input = serializers.CharField(required=False, allow_blank=True, default="")
    selected_hsk_levels = serializers.ListField(
        child=serializers.CharField(max_length=16),
        required=False,
        allow_empty=True,
        default=list,
    )
    min_frequency = serializers.IntegerField(min_value=1, required=False, default=2)
