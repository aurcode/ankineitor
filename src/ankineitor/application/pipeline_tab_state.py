"""Application helpers for pipeline tab session/profile selection state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, MutableMapping, Optional, Sequence


DEFAULT_PIPELINE_WORD_INPUT = "你好\n谢谢\n熊猫\n数据"


@dataclass(frozen=True)
class PipelineSessionKeys:
    """Canonical keys used by the pipeline Streamlit tab session state."""

    profile_transform_selections: str = "pipeline_selected_transform_names_by_profile"
    selected_transform_widget: str = "pipeline_selected_transform_names"
    transform_selector_profile: str = "pipeline_transform_selector_profile_id"
    word_input: str = "pipeline_word_input"
    category_name: str = "pipeline_category_name"


PIPELINE_SESSION_KEYS = PipelineSessionKeys()


@dataclass
class ProfileTransformState:
    """Resolved state for profile-aware transform selection widgets."""

    profile_transform_map: Dict[str, List[str]]
    widget_selection: List[str]
    active_profile_id: str


class PipelineTabStateService:
    """Encapsulates non-UI session state rules for the pipeline tab."""

    def initialize_session_defaults(
        self,
        session_state: MutableMapping[str, Any],
    ) -> None:
        keys = PIPELINE_SESSION_KEYS
        if keys.profile_transform_selections not in session_state or not isinstance(
            session_state.get(keys.profile_transform_selections), dict
        ):
            session_state[keys.profile_transform_selections] = {}

        if keys.word_input not in session_state:
            session_state[keys.word_input] = DEFAULT_PIPELINE_WORD_INPUT

        if keys.category_name not in session_state:
            session_state[keys.category_name] = ""

    @staticmethod
    def _sanitize_profile_transform_map(
        raw_map: Any,
        valid_profile_ids: Sequence[str],
    ) -> Dict[str, List[str]]:
        if not isinstance(raw_map, Mapping):
            return {}

        valid_ids = set(valid_profile_ids)
        sanitized: Dict[str, List[str]] = {}
        for profile_id, selected_names in raw_map.items():
            if profile_id not in valid_ids:
                continue
            if not isinstance(selected_names, list):
                sanitized[profile_id] = []
                continue
            sanitized[profile_id] = [str(name) for name in selected_names]
        return sanitized

    @staticmethod
    def _filter_available_names(
        selected_names: Any,
        available_transform_names: Sequence[str],
    ) -> List[str]:
        if not isinstance(selected_names, list):
            return []
        available_set = set(available_transform_names)
        return [str(name) for name in selected_names if str(name) in available_set]

    def resolve_profile_transform_state(
        self,
        *,
        raw_profile_transform_map: Any,
        valid_profile_ids: Sequence[str],
        selected_profile_id: str,
        active_selector_profile: Optional[str],
        current_widget_selection: Any,
        available_transform_names: Sequence[str],
        default_selection: Sequence[str],
    ) -> ProfileTransformState:
        profile_transform_map = self._sanitize_profile_transform_map(
            raw_map=raw_profile_transform_map,
            valid_profile_ids=valid_profile_ids,
        )

        previous_selection = profile_transform_map.get(selected_profile_id, [])
        filtered_previous = self._filter_available_names(
            selected_names=previous_selection,
            available_transform_names=available_transform_names,
        )
        filtered_current = self._filter_available_names(
            selected_names=current_widget_selection,
            available_transform_names=available_transform_names,
        )
        filtered_default = self._filter_available_names(
            selected_names=list(default_selection),
            available_transform_names=available_transform_names,
        )

        if active_selector_profile != selected_profile_id:
            widget_selection = filtered_previous or filtered_default
        else:
            widget_selection = filtered_current

        return ProfileTransformState(
            profile_transform_map=profile_transform_map,
            widget_selection=widget_selection,
            active_profile_id=selected_profile_id,
        )
