"""Foundation tests verifying project configuration and versioning."""

import ai_search_journey
from ai_search_journey.config import Settings


def test_package_version() -> None:
    """Verify package version is defined."""
    assert ai_search_journey.__version__ == "2.0.0"


def test_settings_defaults() -> None:
    """Verify default configuration settings."""
    settings = Settings()
    assert settings.gemini_model == "gemini-3.6-flash"
    assert settings.log_level == "INFO"
