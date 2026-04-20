from __future__ import annotations

from typing import Any

from app.core.config import get_settings

_client: Any | None = None
_client_provider: str | None = None


def _build_gemini_client(api_key: str) -> Any:
    from google import genai

    return genai.Client(api_key=api_key)


def _build_anthropic_client(api_key: str) -> Any:
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=api_key)


class LLMClient:
    """Lazy provider-aware wrapper for the configured LLM client."""

    @property
    def provider(self) -> str:
        return get_settings().llm_provider

    @property
    def default_model(self) -> str:
        settings = get_settings()
        if settings.llm_provider == "gemini":
            return settings.gemini_model
        return settings.anthropic_model

    @property
    def fallback_model(self) -> str:
        settings = get_settings()
        if settings.llm_provider == "gemini":
            return settings.gemini_fallback_model
        return settings.anthropic_fallback_model

    def get_client(self) -> Any:
        global _client, _client_provider

        settings = get_settings()
        if _client is None or _client_provider != settings.llm_provider:
            if settings.llm_provider == "gemini":
                _client = _build_gemini_client(settings.gemini_api_key or "")
            else:
                _client = _build_anthropic_client(settings.anthropic_api_key or "")
            _client_provider = settings.llm_provider
        return _client

    def reset(self) -> None:
        global _client, _client_provider
        _client = None
        _client_provider = None


llm_client = LLMClient()

__all__ = ["LLMClient", "llm_client"]
