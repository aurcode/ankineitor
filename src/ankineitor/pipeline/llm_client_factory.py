"""Shared GenAI client factory for Gemini/Vertex authentication modes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import google.auth as google_auth
from google import genai
from google.oauth2 import credentials as oauth_credentials
from google.oauth2 import service_account

from ..security.exceptions import ValidationError
from .llm_auth import normalize_token, resolve_token_auth_mode


@dataclass(frozen=True)
class GenAIClientConfig:
    api_token: Optional[str]
    project_id: Optional[str]
    location: str
    credentials_path: Optional[str] = None


def resolve_vertex_credentials(config: GenAIClientConfig) -> tuple[object, str]:
    if config.credentials_path:
        path = Path(config.credentials_path)
        if path.exists():
            credentials = service_account.Credentials.from_service_account_file(
                str(path),
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            project_id = config.project_id or credentials.project_id
            if not project_id:
                raise ValidationError(
                    "Vertex project ID is required when using service account credentials."
                )
            return credentials, project_id

    try:
        credentials, detected_project_id = google_auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
    except Exception as exc:
        raise ValidationError(
            "Vertex credentials not found. Set BQ_CREDENTIALS_PATH/VERTEX_CREDENTIALS_PATH "
            "or provide LLM_API_TOKEN."
        ) from exc

    project_id = config.project_id or detected_project_id
    if not project_id:
        raise ValidationError(
            "Vertex project ID is required when using ADC credentials."
        )
    return credentials, project_id


def build_genai_client(config: GenAIClientConfig) -> genai.Client:
    api_token = normalize_token(config.api_token)
    if api_token:
        mode = resolve_token_auth_mode(api_token)

        if mode == "vertex_oauth_token":
            if not config.project_id:
                raise ValidationError(
                    "GCP_PROJECT_ID is required when using OAuth access tokens for Vertex."
                )
            credentials = oauth_credentials.Credentials(
                token=api_token,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            return genai.Client(
                vertexai=True,
                credentials=credentials,
                project=config.project_id,
                location=config.location,
            )

        if mode == "vertex_api_key":
            return genai.Client(vertexai=True, api_key=api_token)

        return genai.Client(api_key=api_token)

    credentials, project_id = resolve_vertex_credentials(config)
    return genai.Client(
        vertexai=True,
        credentials=credentials,
        project=project_id,
        location=config.location,
    )
