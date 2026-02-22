"""Shared LLM auth/token helpers used by Gemini/Vertex transformations."""

from typing import Optional


DEFAULT_TEXT_MODEL = "gemini-3.1-pro-preview"


def normalize_token(raw_token: Optional[str]) -> Optional[str]:
    """Trim token and remove optional Authorization bearer prefix."""
    if raw_token is None:
        return None
    token = raw_token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token or None


def looks_like_oauth_access_token(token: str) -> bool:
    return token.startswith("ya29.")


def looks_like_vertex_api_key(token: str) -> bool:
    return token.startswith("AQ.")


def resolve_token_auth_mode(raw_token: Optional[str]) -> Optional[str]:
    """
    Resolve auth mode from token shape.

    Returns one of:
    - ``vertex_oauth_token``
    - ``vertex_api_key``
    - ``gemini_api_key``
    """
    token = normalize_token(raw_token)
    if not token:
        return None
    if looks_like_oauth_access_token(token):
        return "vertex_oauth_token"
    if looks_like_vertex_api_key(token):
        return "vertex_api_key"
    return "gemini_api_key"


def resolve_model_name(model_name: Optional[str], default: str = DEFAULT_TEXT_MODEL) -> str:
    """Normalize optional ``vertex_ai/`` prefixes and return a non-empty model id."""
    cleaned = (model_name or "").strip()
    for prefix in ("vertex_ai/", "vertexai/"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    return cleaned or default
