"""Configuration management for AI Search Journey."""

from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3.6-flash"

    google_maps_api_key: Optional[str] = None

    log_level: str = "INFO"

    @field_validator("gemini_api_key", "google_maps_api_key", mode="before")
    @classmethod
    def clean_quotes(cls, v: Optional[str]) -> Optional[str]:
        """Strip matching leading/trailing single or double quotes if present."""
        if v is None:
            return None
        s = str(v).strip()
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            return s[1:-1].strip()
        return s


settings = Settings()
