
def test_app_import_success() -> None:
    """Smoke test to ensure the Streamlit app and V3/V4 UI modules import without errors."""
    import ai_search_journey.app
    assert ai_search_journey.app is not None
