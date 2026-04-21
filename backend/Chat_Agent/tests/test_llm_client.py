from __future__ import annotations

import os
import unittest
from unittest.mock import patch

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
                "DATA_SERVICE_BASE_URL": "http://localhost:8000",
                "GEMINI_API_KEY": "gemini-test-key",
                "GOOGLE_MAPS_API_KEY": "gmaps-key",
                "CORS_ALLOW_ORIGINS": "http://localhost:5173",
                "LOG_LEVEL": "INFO",
            }
        )
        env.pop("LLM_PROVIDER", None)

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

