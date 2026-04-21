from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY = 1.0
_OPENROUTER_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

from app.core.config import get_settings

_client: Any | None = None
_client_provider: str | None = None


def _build_gemini_client(api_key: str) -> Any:
    from google import genai

    return genai.Client(api_key=api_key)


def _build_anthropic_client(api_key: str) -> Any:
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=api_key)


def _build_openrouter_client(api_key: str, base_url: str) -> Any:
    return {
        "api_key": api_key,
        "base_url": base_url.rstrip("/"),
    }


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
        if settings.llm_provider == "anthropic":
            return settings.anthropic_model
        return settings.openrouter_model

    @property
    def fallback_model(self) -> str:
        settings = get_settings()
        if settings.llm_provider == "gemini":
            return settings.gemini_fallback_model
        if settings.llm_provider == "anthropic":
            return settings.anthropic_fallback_model
        return settings.openrouter_fallback_model

    def get_client(self) -> Any:
        global _client, _client_provider

        settings = get_settings()
        if _client is None or _client_provider != settings.llm_provider:
            if settings.llm_provider == "gemini":
                _client = _build_gemini_client(settings.gemini_api_key or "")
            elif settings.llm_provider == "anthropic":
                _client = _build_anthropic_client(settings.anthropic_api_key or "")
            else:
                _client = _build_openrouter_client(
                    settings.openrouter_api_key or "",
                    str(settings.openrouter_base_url),
                )
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

        last_exc: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                if settings.llm_provider == "gemini":
                    return await asyncio.to_thread(
                        self._generate_gemini_text,
                        prompt,
                        model_name,
                        system_prompt,
                    )
                if settings.llm_provider == "anthropic":
                    return await self._generate_anthropic_text(prompt, model_name, system_prompt)
                return await self._generate_openrouter_text(prompt, model_name, system_prompt)
            except Exception as exc:
                last_exc = exc
                status = getattr(exc, "status_code", None)
                is_overload = status == 503 or "503" in str(exc) or "UNAVAILABLE" in str(exc)
                if is_overload and attempt < _RETRY_ATTEMPTS - 1:
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "LLM 503 overload, retrying in %.1fs (attempt %d/%d)",
                        delay, attempt + 1, _RETRY_ATTEMPTS,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise
        raise last_exc  # type: ignore[misc]

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

    async def _generate_openrouter_text(
        self,
        prompt: str,
        model_name: str,
        system_prompt: str | None,
    ) -> str:
        client = self.get_client()
        if not isinstance(client, dict):
            raise ValueError("OpenRouter client was not initialized")

        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        async with httpx.AsyncClient(timeout=_OPENROUTER_TIMEOUT) as http_client:
            response = await http_client.post(
                f"{client['base_url']}/chat/completions",
                headers={
                    "Authorization": f"Bearer {client['api_key']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_name,
                    "messages": messages,
                },
            )
        response.raise_for_status()

        payload = response.json()
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError("OpenRouter response did not contain choices")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ValueError("OpenRouter response did not contain a message")
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            text_parts = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            ]
            joined = "\n".join(part for part in text_parts if part)
            if joined.strip():
                return joined
        raise ValueError("OpenRouter response did not contain text output")

    def reset(self) -> None:
        global _client, _client_provider
        _client = None
        _client_provider = None


llm_client = LLMClient()

__all__ = ["LLMClient", "llm_client"]
