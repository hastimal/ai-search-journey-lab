"""Tests for V4 AI Visibility Agent UI."""

from unittest import mock

import pytest
import streamlit as st

from ai_search_journey.visibility.ui_v4 import check_readiness, render_visibility_agent_tab


@pytest.fixture(autouse=True)
def clear_st_state():
    st.session_state.clear()
    yield
    st.session_state.clear()

def test_canonical_bigquery_settings_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """canonical BigQuery settings accepted;"""
    monkeypatch.setattr(
        "ai_search_journey.visibility.ui_v4._get_bigquery_module", lambda: mock.MagicMock()
    )
    monkeypatch.setattr("ai_search_journey.config.settings.gemini_api_key", "valid-key")
    monkeypatch.setattr("ai_search_journey.config.settings.bigquery_project", "valid-project")
    monkeypatch.setattr("ai_search_journey.config.settings.bigquery_dataset", "valid-dataset")
    monkeypatch.setattr("ai_search_journey.config.settings.bigquery_location", "US")

    is_ready, msg = check_readiness()
    assert is_ready
    assert msg == ""

def test_missing_bigquery_settings_disables_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    """missing BigQuery project/dataset/location disables chat;"""
    monkeypatch.setattr(
        "ai_search_journey.visibility.ui_v4._get_bigquery_module", lambda: mock.MagicMock()
    )
    monkeypatch.setattr("ai_search_journey.config.settings.gemini_api_key", "valid-key")

    # Missing project
    monkeypatch.setattr("ai_search_journey.config.settings.bigquery_project", "")
    is_ready, msg = check_readiness()
    assert not is_ready
    assert "BIGQUERY_PROJECT" in msg

    # Missing dataset
    monkeypatch.setattr("ai_search_journey.config.settings.bigquery_project", "valid-project")
    monkeypatch.setattr(
        "ai_search_journey.config.settings.bigquery_dataset", ""
    )
    is_ready, msg = check_readiness()
    assert not is_ready
    assert "BIGQUERY_DATASET" in msg

    # Missing location
    monkeypatch.setattr("ai_search_journey.config.settings.bigquery_dataset", "valid-dataset")
    monkeypatch.setattr("ai_search_journey.config.settings.bigquery_location", "")
    is_ready, msg = check_readiness()
    assert not is_ready
    assert "BIGQUERY_LOCATION" in msg

def test_missing_gemini_config_disables_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gemini configuration missing disables chat;"""
    monkeypatch.setattr(
        "ai_search_journey.visibility.ui_v4._get_bigquery_module", lambda: mock.MagicMock()
    )
    monkeypatch.setattr("ai_search_journey.config.settings.gemini_api_key", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")

    is_ready, msg = check_readiness()
    assert not is_ready
    assert "GEMINI_API_KEY" in msg

def test_missing_bigquery_dependency_disables_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    """BigQuery dependency missing disables chat;"""
    monkeypatch.setattr("ai_search_journey.visibility.ui_v4._get_bigquery_module", lambda: None)

    is_ready, msg = check_readiness()
    assert not is_ready
    assert "google-cloud-bigquery" in msg

def test_chat_submission_calls_only_fake_v4_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """chat submission calls only injected fake V4 agent; no legacy execution"""
    monkeypatch.setattr(
        "ai_search_journey.visibility.ui_v4.check_readiness", lambda: (True, "")
    )

    fake_agent_instance = mock.MagicMock()
    fake_agent_instance.run.return_value = "Fake analysis result"
    fake_agent_class = mock.MagicMock(return_value=fake_agent_instance)

    monkeypatch.setitem(
        __import__('sys').modules,
        'ai_search_journey.visibility.v4_agent',
        mock.MagicMock(VisibilityAnalyticsAgent=fake_agent_class)
    )

    with mock.patch("streamlit.chat_input", return_value="What is our trend?"), \
         mock.patch("streamlit.columns") as mock_cols_func, \
         mock.patch("streamlit.status") as mock_status:

        mock_status.return_value.__enter__.return_value = mock.MagicMock()
        mock_col = mock.MagicMock()
        mock_col.button.return_value = False
        mock_cols_func.return_value = [mock_col] * 4

        render_visibility_agent_tab()

        fake_agent_instance.run.assert_called_once_with("What is our trend?")

        assert len(st.session_state["v4_chat_history"]) == 2
        assert st.session_state["v4_chat_history"][0]["role"] == "user"
        assert st.session_state["v4_chat_history"][0]["content"] == "What is our trend?"
        assert st.session_state["v4_chat_history"][1]["role"] == "assistant"
        assert st.session_state["v4_chat_history"][1]["content"] == "Fake analysis result"
        assert st.session_state["v4_chat_history"][1].get("sources_used") is True

def test_empty_history_result_is_rendered_honestly(monkeypatch: pytest.MonkeyPatch) -> None:
    """empty-history result is rendered honestly;"""
    monkeypatch.setattr(
        "ai_search_journey.visibility.ui_v4.check_readiness", lambda: (True, "")
    )

    fake_agent_instance = mock.MagicMock()
    fake_agent_instance.run.return_value = "The history is empty."
    fake_agent_class = mock.MagicMock(return_value=fake_agent_instance)

    monkeypatch.setitem(
        __import__('sys').modules,
        'ai_search_journey.visibility.v4_agent',
        mock.MagicMock(VisibilityAnalyticsAgent=fake_agent_class)
    )

    with mock.patch("streamlit.chat_input", return_value="Compare brands"):
        mock_col = mock.MagicMock()
        mock_col.button.return_value = False
        with mock.patch("streamlit.columns", return_value=[mock_col] * 4), \
             mock.patch("streamlit.status") as mock_status:
            mock_status.return_value.__enter__.return_value = mock.MagicMock()
            render_visibility_agent_tab()

            assert len(st.session_state["v4_chat_history"]) == 2
            assert st.session_state["v4_chat_history"][1]["content"] == "The history is empty."

def test_agent_error_is_shown_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    """agent error is shown safely;"""
    monkeypatch.setattr(
        "ai_search_journey.visibility.ui_v4.check_readiness", lambda: (True, "")
    )

    fake_agent_instance = mock.MagicMock()
    fake_agent_instance.run.side_effect = RuntimeError("BigQuery connection timeout")
    fake_agent_class = mock.MagicMock(return_value=fake_agent_instance)

    monkeypatch.setitem(
        __import__('sys').modules,
        'ai_search_journey.visibility.v4_agent',
        mock.MagicMock(VisibilityAnalyticsAgent=fake_agent_class)
    )

    with mock.patch("streamlit.chat_input", return_value="Fail please"), \
         mock.patch("streamlit.error") as mock_st_error:

        mock_col = mock.MagicMock()
        mock_col.button.return_value = False
        with mock.patch("streamlit.columns", return_value=[mock_col] * 4), \
             mock.patch("streamlit.status") as mock_status:
            mock_status.return_value.__enter__.return_value = mock.MagicMock()
            render_visibility_agent_tab()

            mock_st_error.assert_called_with(
                "The agent encountered an error while processing the request."
            )
            assert (
                st.session_state["v4_chat_history"][-1]["content"]
                == "⚠️ Error processing request."
            )
            assert st.session_state["v4_chat_history"][-1].get("sources_used") is False

def test_no_legacy_execution_functions_invoked(monkeypatch: pytest.MonkeyPatch) -> None:
    """no V1/V2/V3 scan, search, Places, fan-out, or runner function is invoked."""
    monkeypatch.setattr(
        "ai_search_journey.visibility.ui_v4.check_readiness", lambda: (True, "")
    )

    fake_agent_instance = mock.MagicMock()
    fake_agent_instance.run.return_value = "Result"
    fake_agent_class = mock.MagicMock(return_value=fake_agent_instance)

    monkeypatch.setitem(
        __import__('sys').modules,
        'ai_search_journey.visibility.v4_agent',
        mock.MagicMock(VisibilityAnalyticsAgent=fake_agent_class)
    )

    mock_fail = mock.MagicMock(side_effect=AssertionError("Should not be called"))
    monkeypatch.setattr(
        "ai_search_journey.visibility.runner.run_visibility_scan", mock_fail, raising=False
    )
    monkeypatch.setattr("ai_search_journey.fanout.fan_out_query", mock_fail, raising=False)
    monkeypatch.setattr("ai_search_journey.search.run_google_search", mock_fail, raising=False)
    monkeypatch.setattr("ai_search_journey.places.search_places", mock_fail, raising=False)

    with mock.patch("streamlit.chat_input", return_value="Test no legacy execution"):
        mock_col = mock.MagicMock()
        mock_col.button.return_value = False
        with mock.patch("streamlit.columns", return_value=[mock_col] * 4), \
             mock.patch("streamlit.status") as mock_status:
            mock_status.return_value.__enter__.return_value = mock.MagicMock()
            render_visibility_agent_tab()


def test_model_unavailable_error_is_shown_safely(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gemini 404 / model unavailable error produces clear UI guidance."""
    monkeypatch.setattr(
        "ai_search_journey.visibility.ui_v4.check_readiness", lambda: (True, "")
    )

    fake_agent_instance = mock.MagicMock()
    fake_agent_instance.run.side_effect = RuntimeError(
        "404 models/gemini-not-found is not found for API version v1beta"
    )
    fake_agent_class = mock.MagicMock(return_value=fake_agent_instance)

    monkeypatch.setitem(
        __import__("sys").modules,
        "ai_search_journey.visibility.v4_agent",
        mock.MagicMock(VisibilityAnalyticsAgent=fake_agent_class),
    )

    with mock.patch("streamlit.chat_input", return_value="Test model 404"), \
         mock.patch("streamlit.error") as mock_st_error:

        mock_col = mock.MagicMock()
        mock_col.button.return_value = False
        with mock.patch("streamlit.columns", return_value=[mock_col] * 4), \
             mock.patch("streamlit.status") as mock_status:
            mock_status.return_value.__enter__.return_value = mock.MagicMock()
            render_visibility_agent_tab()

            mock_st_error.assert_called_with(
                "Configured Gemini model is unavailable. Update GEMINI_MODEL and restart the app."
            )
            assert (
                st.session_state["v4_chat_history"][-1]["content"]
                == "⚠️ Error processing request."
            )


def test_empty_state_renders_agent_console(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty state renders the modern AI agent console with rotating copy."""
    monkeypatch.setattr(
        "ai_search_journey.visibility.ui_v4.check_readiness", lambda: (True, "")
    )

    markdown_calls = []

    def mock_markdown(content: str, *args, **kwargs):
        markdown_calls.append(content)

    with mock.patch("streamlit.markdown", side_effect=mock_markdown), \
         mock.patch("streamlit.chat_input", return_value=None), \
         mock.patch("streamlit.columns") as mock_cols_func:

        mock_col = mock.MagicMock()
        mock_col.button.return_value = False
        mock_cols_func.return_value = [mock_col] * 4

        render_visibility_agent_tab()

        all_rendered_md = "".join(markdown_calls)
        assert "v4-agent-console" in all_rendered_md
        assert "AI VISIBILITY CONSOLE [READY]" in all_rendered_md
        assert "Inspecting visibility history…" in all_rendered_md
        assert "Grounded in read-only BigQuery data…" in all_rendered_md
        assert "Ask about citations, competitors, or fan-out gaps." in all_rendered_md


def test_chat_layout_ordering_and_example_prompts_hiding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that messages render before chat_input, and prompt chips hide once active."""
    monkeypatch.setattr(
        "ai_search_journey.visibility.ui_v4.check_readiness", lambda: (True, "")
    )

    fake_agent_instance = mock.MagicMock()
    fake_agent_instance.run.return_value = "Answer before composer"
    fake_agent_class = mock.MagicMock(return_value=fake_agent_instance)

    monkeypatch.setitem(
        __import__("sys").modules,
        "ai_search_journey.visibility.v4_agent",
        mock.MagicMock(VisibilityAnalyticsAgent=fake_agent_class),
    )

    call_order: list[str] = []

    def mock_chat_message(role: str, *args, **kwargs):
        call_order.append(f"chat_message_{role}")
        return mock.MagicMock()

    def mock_chat_input(*args, **kwargs):
        call_order.append("chat_input")
        return "Where are our citations?"

    mock_col = mock.MagicMock()
    mock_col.button.return_value = False

    with mock.patch("streamlit.chat_message", side_effect=mock_chat_message), \
         mock.patch("streamlit.chat_input", side_effect=mock_chat_input), \
         mock.patch("streamlit.columns", return_value=[mock_col] * 4) as mock_cols, \
         mock.patch("streamlit.status") as mock_status:

        mock_status.return_value.__enter__.return_value = mock.MagicMock()

        # 1. First run: empty state -> columns called (chips shown) -> query submitted
        render_visibility_agent_tab()
        assert mock_cols.called
        # Verify call order: chat_input called at bottom after empty container render
        assert "chat_input" in call_order
        assert "chat_message_user" in call_order
        assert "chat_message_assistant" in call_order

        # 2. Second run: conversation history now exists -> columns should NOT be called
        mock_cols.reset_mock()
        call_order.clear()

        def mock_chat_input_idle(*args, **kwargs):
            call_order.append("chat_input")
            return None

        with mock.patch("streamlit.chat_input", side_effect=mock_chat_input_idle):
            render_visibility_agent_tab()

            # Columns for prompt chips should not have been called
            assert not mock_cols.called
            # History rendered before chat_input
            assert call_order == [
                "chat_message_user",
                "chat_message_assistant",
                "chat_input",
            ]
