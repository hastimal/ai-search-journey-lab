
def test_app_import_success() -> None:
    """Smoke test to ensure the Streamlit app and V3/V4 UI modules import without errors."""
    import ai_search_journey.app

    assert ai_search_journey.app is not None


def test_quick_demo_presets() -> None:
    """Verify quick demo presets are accurately defined and include the UH preset."""
    from ai_search_journey.app import (
        DEFAULT_COFFEE_QUERY,
        DEFAULT_DENTIST_QUERY,
        DEFAULT_INDIAN_QUERY,
    )

    assert "Geekdom San Antonio" in DEFAULT_COFFEE_QUERY
    assert "Trinity University" in DEFAULT_INDIAN_QUERY
    assert (
        DEFAULT_DENTIST_QUERY
        == "Find three pediatric dentists near the University of Houston "
        "for a child anxious about dental visits."
    )
