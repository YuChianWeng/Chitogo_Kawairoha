from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    app_env: str = Field(..., min_length=1)
    host: str = Field(..., min_length=1)
    port: int = Field(..., ge=1, le=65535)
    data_service_base_url: AnyHttpUrl
    place_service_timeout_sec: int = Field(default=3, ge=1)
    llm_provider: Literal["gemini", "anthropic", "openrouter"] = "gemini"
    gemini_api_key: str | None = None
    gemini_model: str = Field(default="gemini-2.5-flash", min_length=1)
    gemini_fallback_model: str = Field(default="gemini-2.5-pro", min_length=1)
    anthropic_api_key: str | None = None
    anthropic_model: str = Field(default="claude-sonnet-4-6", min_length=1)
    anthropic_fallback_model: str = Field(
        default="claude-haiku-4-5-20251001",
        min_length=1,
    )
    openrouter_api_key: str | None = None
    openrouter_model: str = Field(default="openai/gpt-4.1-mini", min_length=1)
    openrouter_fallback_model: str = Field(
        default="openai/gpt-4.1",
        min_length=1,
    )
    openrouter_base_url: AnyHttpUrl = Field(
        default="https://openrouter.ai/api/v1",
    )
    google_maps_api_key: str = Field(..., min_length=1)
    route_provider: Literal["google_maps", "fallback"] = "google_maps"
    route_service_timeout_sec: int = Field(default=3, ge=1)
    cors_allow_origins_raw: str = Field(
        ...,
        alias="CORS_ALLOW_ORIGINS",
        min_length=1,
    )
    session_ttl_minutes: int = Field(default=30, ge=1)
    agent_loop_max_iterations: int = Field(default=6, ge=1)
    request_timeout_s: int = Field(default=2, ge=1)
    default_start_time: str = Field(default="10:00", min_length=5, max_length=5)
    trace_store_max_items: int = Field(default=200, ge=1, le=1000)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    cwa_api_key: str | None = None
    cwa_weather_timeout_sec: int = Field(default=3, ge=1)
    hf_api_key: str | None = None
    hf_endpoint_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        enable_decoding=False,
        populate_by_name=True,
    )

    @property
    def cors_allow_origins(self) -> list[str]:
        return [
            item.strip()
            for item in self.cors_allow_origins_raw.split(",")
            if item and item.strip()
        ]

    @property
    def place_service_base_url(self) -> str:
        return str(self.data_service_base_url).rstrip("/")

    @field_validator("cors_allow_origins_raw")
    @classmethod
    def validate_cors_allow_origins(cls, value: str) -> str:
        origins = [item.strip() for item in value.split(",") if item.strip()]
        if not origins:
            raise ValueError("CORS_ALLOW_ORIGINS must contain at least one origin")
        return value

    @field_validator(
        "gemini_api_key",
        "anthropic_api_key",
        "openrouter_api_key",
        "google_maps_api_key",
    )
    @classmethod
    def validate_secret_values(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            raise ValueError(f"{info.field_name.upper()} must not be empty")
        return trimmed

    @field_validator("app_env", "host")
    @classmethod
    def validate_non_empty_strings(cls, value: str, info: ValidationInfo) -> str:
        trimmed = value.strip()
        if not trimmed:
            env_name = info.field_name.upper()
            raise ValueError(f"{env_name} must not be empty")
        return trimmed

    @field_validator("default_start_time")
    @classmethod
    def validate_default_start_time(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError as exc:
            raise ValueError("DEFAULT_START_TIME must use HH:MM format") from exc
        return value

    @model_validator(mode="after")
    def validate_selected_provider(self) -> Settings:
        if self.llm_provider == "gemini" and not self.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic")
        if self.llm_provider == "openrouter" and not self.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is required when LLM_PROVIDER=openrouter")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance."""
    return Settings()


def clear_settings_cache() -> None:
    """Reset the cached settings instance for tests."""
    get_settings.cache_clear()
