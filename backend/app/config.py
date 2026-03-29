from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_path: str = "./taipei.db"
    openweather_api_key: str = ""
    mock_weather: str = ""
    use_llm: bool = False
    weather_cache_ttl_minutes: int = 30

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
