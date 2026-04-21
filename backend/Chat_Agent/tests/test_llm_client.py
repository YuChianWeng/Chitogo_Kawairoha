from __future__ import annotations

import os
import unittest
from unittest.mock import AsyncMock, patch

from app.core.config import clear_settings_cache
from app.llm.client import llm_client


class LLMClientTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_settings_cache()
        llm_client.reset()

    def tearDown(self) -> None:
        clear_settings_cache()
        llm_client.reset()

    def test_provider_defaults_to_gemini(self) -> None:
        env = dict(os.environ)
        env.update(
            {
                "APP_ENV": "test",
                "HOST": "127.0.0.1",
                "PORT": "8100",
                "LLM_PROVIDER": "gemini",
                "DATA_SERVICE_BASE_URL": "http://localhost:8000",
                "GEMINI_API_KEY": "gemini-test-key",
                "GEMINI_MODEL": "gemini-2.5-flash",
                "GEMINI_FALLBACK_MODEL": "gemini-2.5-pro",
                "GOOGLE_MAPS_API_KEY": "gmaps-key",
                "CORS_ALLOW_ORIGINS": "http://localhost:5173",
                "LOG_LEVEL": "INFO",
            }
        )
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(llm_client.provider, "gemini")
            self.assertEqual(llm_client.default_model, "gemini-2.5-flash")
            self.assertEqual(llm_client.fallback_model, "gemini-2.5-pro")

    def test_client_initializes_gemini_by_default(self) -> None:
        env = dict(os.environ)
        env.update(
            {
                "APP_ENV": "test",
                "HOST": "127.0.0.1",
                "PORT": "8100",
                "LLM_PROVIDER": "gemini",
                "DATA_SERVICE_BASE_URL": "http://localhost:8000",
                "GEMINI_API_KEY": "gemini-test-key",
                "GOOGLE_MAPS_API_KEY": "gmaps-key",
                "CORS_ALLOW_ORIGINS": "http://localhost:5173",
                "LOG_LEVEL": "INFO",
            }
        )

        gemini_stub = object()
        with patch.dict(os.environ, env, clear=True):
            with patch(
                "app.llm.client._build_gemini_client",
                return_value=gemini_stub,
            ) as build_gemini:
                with patch("app.llm.client._build_anthropic_client") as build_anthropic:
                    client = llm_client.get_client()

        self.assertIs(client, gemini_stub)
        build_gemini.assert_called_once_with("gemini-test-key")
        build_anthropic.assert_not_called()

    def test_provider_supports_openrouter(self) -> None:
        env = dict(os.environ)
        env.update(
            {
                "APP_ENV": "test",
                "HOST": "127.0.0.1",
                "PORT": "8100",
                "LLM_PROVIDER": "openrouter",
                "DATA_SERVICE_BASE_URL": "http://localhost:8000",
                "OPENROUTER_API_KEY": "openrouter-test-key",
                "OPENROUTER_MODEL": "openai/gpt-4.1-mini",
                "OPENROUTER_FALLBACK_MODEL": "openai/gpt-4.1",
                "GOOGLE_MAPS_API_KEY": "gmaps-key",
                "CORS_ALLOW_ORIGINS": "http://localhost:5173",
                "LOG_LEVEL": "INFO",
            }
        )
        env.pop("GEMINI_API_KEY", None)
        env.pop("ANTHROPIC_API_KEY", None)

        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(llm_client.provider, "openrouter")
            self.assertEqual(llm_client.default_model, "openai/gpt-4.1-mini")
            self.assertEqual(llm_client.fallback_model, "openai/gpt-4.1")

    def test_client_initializes_openrouter(self) -> None:
        env = dict(os.environ)
        env.update(
            {
                "APP_ENV": "test",
                "HOST": "127.0.0.1",
                "PORT": "8100",
                "LLM_PROVIDER": "openrouter",
                "DATA_SERVICE_BASE_URL": "http://localhost:8000",
                "OPENROUTER_API_KEY": "openrouter-test-key",
                "OPENROUTER_MODEL": "openai/gpt-4.1-mini",
                "OPENROUTER_FALLBACK_MODEL": "openai/gpt-4.1",
                "GOOGLE_MAPS_API_KEY": "gmaps-key",
                "CORS_ALLOW_ORIGINS": "http://localhost:5173",
                "LOG_LEVEL": "INFO",
            }
        )

        openrouter_stub = object()
        with patch.dict(os.environ, env, clear=True):
            with patch(
                "app.llm.client._build_openrouter_client",
                return_value=openrouter_stub,
            ) as build_openrouter:
                with patch("app.llm.client._build_gemini_client") as build_gemini:
                    with patch("app.llm.client._build_anthropic_client") as build_anthropic:
                        client = llm_client.get_client()

        self.assertIs(client, openrouter_stub)
        build_openrouter.assert_called_once_with(
            "openrouter-test-key",
            "https://openrouter.ai/api/v1",
        )
        build_gemini.assert_not_called()
        build_anthropic.assert_not_called()

    def test_generate_text_uses_openrouter_path(self) -> None:
        import asyncio

        env = dict(os.environ)
        env.update(
            {
                "APP_ENV": "test",
                "HOST": "127.0.0.1",
                "PORT": "8100",
                "LLM_PROVIDER": "openrouter",
                "DATA_SERVICE_BASE_URL": "http://localhost:8000",
                "OPENROUTER_API_KEY": "openrouter-test-key",
                "OPENROUTER_MODEL": "openai/gpt-4.1-mini",
                "OPENROUTER_FALLBACK_MODEL": "openai/gpt-4.1",
                "GOOGLE_MAPS_API_KEY": "gmaps-key",
                "CORS_ALLOW_ORIGINS": "http://localhost:5173",
                "LOG_LEVEL": "INFO",
            }
        )

        async def run_test() -> None:
            with patch.dict(os.environ, env, clear=True):
                with patch.object(
                    llm_client,
                    "_generate_openrouter_text",
                    AsyncMock(return_value="hello from openrouter"),
                ) as generate_openrouter:
                    with patch.object(llm_client, "_generate_anthropic_text", AsyncMock()) as generate_anthropic:
                        with patch.object(llm_client, "_generate_gemini_text") as generate_gemini:
                            text = await llm_client.generate_text("hello")

            self.assertEqual(text, "hello from openrouter")
            generate_openrouter.assert_awaited_once()
            generate_anthropic.assert_not_awaited()
            generate_gemini.assert_not_called()

        asyncio.run(run_test())

    def test_generate_openrouter_text_parses_chat_completion(self) -> None:
        import asyncio
        import httpx

        env = dict(os.environ)
        env.update(
            {
                "APP_ENV": "test",
                "HOST": "127.0.0.1",
                "PORT": "8100",
                "LLM_PROVIDER": "openrouter",
                "DATA_SERVICE_BASE_URL": "http://localhost:8000",
                "OPENROUTER_API_KEY": "openrouter-test-key",
                "OPENROUTER_MODEL": "openai/gpt-4.1-mini",
                "OPENROUTER_FALLBACK_MODEL": "openai/gpt-4.1",
                "GOOGLE_MAPS_API_KEY": "gmaps-key",
                "CORS_ALLOW_ORIGINS": "http://localhost:5173",
                "LOG_LEVEL": "INFO",
            }
        )

        async def run_test() -> None:
            request = httpx.Request(
                "POST",
                "https://openrouter.ai/api/v1/chat/completions",
            )
            response = httpx.Response(
                200,
                request=request,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "structured reply",
                            }
                        }
                    ]
                },
            )

            async def fake_post(*args: object, **kwargs: object) -> httpx.Response:
                self.assertEqual(args[0], "https://openrouter.ai/api/v1/chat/completions")
                self.assertEqual(
                    kwargs["headers"]["Authorization"],
                    "Bearer openrouter-test-key",
                )
                self.assertEqual(kwargs["json"]["model"], "openai/gpt-4.1-mini")
                self.assertEqual(
                    kwargs["json"]["messages"],
                    [{"role": "user", "content": "hello"}],
                )
                return response

            with patch.dict(os.environ, env, clear=True):
                with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=fake_post)):
                    text = await llm_client._generate_openrouter_text(
                        "hello",
                        "openai/gpt-4.1-mini",
                        None,
                    )

            self.assertEqual(text, "structured reply")

        asyncio.run(run_test())
