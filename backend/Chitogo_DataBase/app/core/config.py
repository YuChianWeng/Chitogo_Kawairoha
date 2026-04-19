from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://chitogo_user:kawairoha@localhost:5432/chitogo"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
