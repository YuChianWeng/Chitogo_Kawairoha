from __future__ import annotations

import asyncio
import json
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


def _extract_json_string(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1] == "```":
            stripped = "\n".join(lines[1:-1]).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("LLM response did not contain a JSON object")
    return stripped[start : end + 1]


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

    async def generate_text(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> str:
        settings = get_settings()
        model_name = model or self.default_model

        if settings.llm_provider == "gemini":
            return await asyncio.to_thread(
                self._generate_gemini_text,
                prompt,
                model_name,
                system_prompt,
            )
        return await self._generate_anthropic_text(prompt, model_name, system_prompt)

    async def generate_json(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        response_text = await self.generate_text(
            prompt,
            model=model,
            system_prompt=system_prompt,
        )
        return json.loads(_extract_json_string(response_text))

    def _generate_gemini_text(
        self,
        prompt: str,
        model_name: str,
        system_prompt: str | None,
    ) -> str:
        client = self.get_client()
        full_prompt = prompt if not system_prompt else f"{system_prompt}\n\n{prompt}"
        response = client.models.generate_content(
            model=model_name,
            contents=full_prompt,
        )
        text = getattr(response, "text", None)
        if not text:
            raise ValueError("Gemini response did not contain text output")
        return text

    async def _generate_anthropic_text(
        self,
        prompt: str,
        model_name: str,
        system_prompt: str | None,
    ) -> str:
        client = self.get_client()
        response = await client.messages.create(
            model=model_name,
            max_tokens=512,
            system=system_prompt or "",
            messages=[{"role": "user", "content": prompt}],
        )
        text_parts = [
            block.text
            for block in getattr(response, "content", [])
            if getattr(block, "type", None) == "text" and getattr(block, "text", None)
        ]
        if not text_parts:
            raise ValueError("Anthropic response did not contain text output")
        return "\n".join(text_parts)

    def reset(self) -> None:
        global _client, _client_provider
        _client = None
        _client_provider = None


llm_client = LLMClient()

__all__ = ["LLMClient", "llm_client"]
