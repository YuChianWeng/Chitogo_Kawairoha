from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from app.core.config import Settings, clear_settings_cache


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
                Settings()

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
            settings = Settings()

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
                Settings()

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
                Settings()

        self.assertIn("ANTHROPIC_API_KEY is required", str(exc_info.exception))
