from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError
from pydantic_settings import SettingsConfigDict

from app.core.config import Settings, clear_settings_cache


class _IsolatedSettings(Settings):
    model_config = SettingsConfigDict(
        env_file=None,
        case_sensitive=False,
        extra="ignore",
        enable_decoding=False,
        populate_by_name=True,
    )


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_settings_cache()

    def tearDown(self) -> None:
        clear_settings_cache()

    def test_settings_fail_when_required_values_are_missing(self) -> None:
        required_env_vars = [
            "APP_ENV",
            "HOST",
            "PORT",
            "DATA_SERVICE_BASE_URL",
            "GEMINI_API_KEY",
            "GOOGLE_MAPS_API_KEY",
            "CORS_ALLOW_ORIGINS",
            "LOG_LEVEL",
        ]
        env = dict(os.environ)
        for name in required_env_vars:
            env.pop(name, None)

        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValidationError) as exc_info:
                _IsolatedSettings()

        message = str(exc_info.exception)
        self.assertIn("app_env", message)
        self.assertIn("data_service_base_url", message)
        self.assertIn("google_maps_api_key", message)

    def test_settings_accept_valid_environment(self) -> None:
        env = dict(os.environ)
        env.update(
            {
                "APP_ENV": "development",
                "HOST": "0.0.0.0",
                "PORT": "8100",
                "DATA_SERVICE_BASE_URL": "http://localhost:8000",
                "GEMINI_API_KEY": "gemini-test-key",
                "GOOGLE_MAPS_API_KEY": "gmaps-key",
                "CORS_ALLOW_ORIGINS": "http://localhost:3000,http://localhost:5173",
                "LOG_LEVEL": "INFO",
            }
        )

        with patch.dict(os.environ, env, clear=True):
            settings = _IsolatedSettings()

        self.assertEqual(settings.app_env, "development")
        self.assertEqual(settings.port, 8100)
        self.assertEqual(str(settings.data_service_base_url), "http://localhost:8000/")
        self.assertEqual(settings.llm_provider, "gemini")
        self.assertEqual(settings.gemini_api_key, "gemini-test-key")
        self.assertEqual(settings.gemini_model, "gemini-2.5-flash")
        self.assertEqual(settings.gemini_fallback_model, "gemini-2.5-pro")
        self.assertEqual(settings.google_maps_api_key, "gmaps-key")
        self.assertEqual(settings.agent_loop_max_iterations, 6)
        self.assertEqual(settings.request_timeout_s, 2)
        self.assertEqual(settings.default_start_time, "10:00")
        self.assertEqual(settings.trace_store_max_items, 200)
        self.assertEqual(
            settings.cors_allow_origins,
            ["http://localhost:3000", "http://localhost:5173"],
        )

    def test_settings_require_gemini_key_when_provider_is_default(self) -> None:
        env = dict(os.environ)
        env.update(
            {
                "APP_ENV": "development",
                "HOST": "0.0.0.0",
                "PORT": "8100",
                "DATA_SERVICE_BASE_URL": "http://localhost:8000",
                "GOOGLE_MAPS_API_KEY": "gmaps-key",
                "CORS_ALLOW_ORIGINS": "http://localhost:3000",
                "LOG_LEVEL": "INFO",
            }
        )
        env.pop("LLM_PROVIDER", None)
        env.pop("GEMINI_API_KEY", None)

        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValidationError) as exc_info:
                _IsolatedSettings()

        self.assertIn("GEMINI_API_KEY is required", str(exc_info.exception))

    def test_settings_require_anthropic_key_when_provider_is_anthropic(self) -> None:
        env = dict(os.environ)
        env.update(
            {
                "APP_ENV": "development",
                "HOST": "0.0.0.0",
                "PORT": "8100",
                "LLM_PROVIDER": "anthropic",
                "DATA_SERVICE_BASE_URL": "http://localhost:8000",
                "GOOGLE_MAPS_API_KEY": "gmaps-key",
                "CORS_ALLOW_ORIGINS": "http://localhost:3000",
                "LOG_LEVEL": "INFO",
            }
        )
        env.pop("GEMINI_API_KEY", None)
        env.pop("ANTHROPIC_API_KEY", None)

        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValidationError) as exc_info:
                _IsolatedSettings()

        self.assertIn("ANTHROPIC_API_KEY is required", str(exc_info.exception))

    def test_settings_accept_openrouter_environment(self) -> None:
        env = dict(os.environ)
        env.update(
            {
                "APP_ENV": "development",
                "HOST": "0.0.0.0",
                "PORT": "8100",
                "LLM_PROVIDER": "openrouter",
                "DATA_SERVICE_BASE_URL": "http://localhost:8000",
                "OPENROUTER_API_KEY": "openrouter-test-key",
                "OPENROUTER_MODEL": "openai/gpt-4.1-mini",
                "OPENROUTER_FALLBACK_MODEL": "openai/gpt-4.1",
                "GOOGLE_MAPS_API_KEY": "gmaps-key",
                "CORS_ALLOW_ORIGINS": "http://localhost:3000",
                "LOG_LEVEL": "INFO",
            }
        )
        env.pop("GEMINI_API_KEY", None)
        env.pop("ANTHROPIC_API_KEY", None)

        with patch.dict(os.environ, env, clear=True):
            settings = _IsolatedSettings()

        self.assertEqual(settings.llm_provider, "openrouter")
        self.assertEqual(settings.openrouter_api_key, "openrouter-test-key")
        self.assertEqual(settings.openrouter_model, "openai/gpt-4.1-mini")
        self.assertEqual(settings.openrouter_fallback_model, "openai/gpt-4.1")
        self.assertEqual(str(settings.openrouter_base_url), "https://openrouter.ai/api/v1")

    def test_settings_require_openrouter_key_when_provider_is_openrouter(self) -> None:
        env = dict(os.environ)
        env.update(
            {
                "APP_ENV": "development",
                "HOST": "0.0.0.0",
                "PORT": "8100",
                "LLM_PROVIDER": "openrouter",
                "DATA_SERVICE_BASE_URL": "http://localhost:8000",
                "GOOGLE_MAPS_API_KEY": "gmaps-key",
                "CORS_ALLOW_ORIGINS": "http://localhost:3000",
                "LOG_LEVEL": "INFO",
            }
        )
        env.pop("GEMINI_API_KEY", None)
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("OPENROUTER_API_KEY", None)

        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(ValidationError) as exc_info:
                _IsolatedSettings()

        self.assertIn("OPENROUTER_API_KEY is required", str(exc_info.exception))
