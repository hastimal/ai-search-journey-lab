"""Configuration management for AI Search Journey."""

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.5-flash"

    google_maps_api_key: Optional[str] = None

    log_level: str = "INFO"


settings = Settings()
