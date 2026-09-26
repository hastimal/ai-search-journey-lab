"""Tests for Observability [V5] Streamlit UI rendering."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ai_search_journey.telemetry import TelemetryStore, init_telemetry, trace_span
from ai_search_journey.ui_observability import render_observability_tab


@pytest.fixture(autouse=True)
def clean_telemetry_store():
    store = init_telemetry(max_runs=10)
    store.clear()
    yield store
    store.clear()


def test_render_observability_tab_empty(clean_telemetry_store: TelemetryStore):
    """Verify render_observability_tab shows info banner and Grafana links when no runs exist."""
    def mock_columns(spec, **kwargs):
        n = spec if isinstance(spec, int) else len(spec)
        return [MagicMock() for _ in range(n)]

    with patch("streamlit.info") as mock_info, \
         patch("streamlit.header") as mock_header, \
         patch("streamlit.columns", side_effect=mock_columns), \
         patch("streamlit.link_button") as mock_link_btn:
        render_observability_tab()
        mock_header.assert_called_with("Observability [V5]")
        assert any("No journey traces recorded yet" in str(c) for c in mock_info.call_args_list)
        assert mock_link_btn.called
        button_labels = [c[0][0] for c in mock_link_btn.call_args_list]
        assert any("Grafana AgentOps Dashboard" in lbl for lbl in button_labels)
        assert any("Tempo Explore" in lbl for lbl in button_labels)


def test_render_observability_tab_with_runs(clean_telemetry_store: TelemetryStore):
    """Verify render_observability_tab formats run metrics and span expanders."""
    # Create sample spans
    with trace_span("journey.execution", run_id="run_ui_test", attributes={"attr1": "val1"}):
        with trace_span(
            "journey.intent_parsing", run_id="run_ui_test", attributes={"category": "cafe"}
        ):
            pass

    def mock_columns(spec, **kwargs):
        n = spec if isinstance(spec, int) else len(spec)
        return [MagicMock() for _ in range(n)]

    with patch("streamlit.header"), \
         patch("streamlit.info") as mock_info, \
         patch("streamlit.write"), \
         patch("streamlit.selectbox", side_effect=[0, 0]) as mock_sb, \
         patch("streamlit.columns", side_effect=mock_columns), \
         patch("streamlit.expander", return_value=MagicMock()), \
         patch("streamlit.table"):

        render_observability_tab()
        # Verify privacy banner wording
        banner_texts = [str(c[0][0]) for c in mock_info.call_args_list]
        assert any(
            "Local Telemetry & Privacy Guard" in t and "Raw prompts, credentials" in t
            for t in banner_texts
        )
        assert mock_sb.called


def test_render_observability_tab_stage_filtering(clean_telemetry_store: TelemetryStore):
    """Verify stage filter correctly isolates V3 runs from V1 runs."""
    # Add a V1 run and a V3 run
    with trace_span("journey.execution", run_id="v1_run", attributes={"workflow.stage": "v1"}):
        pass
    with trace_span(
        "visibility.scan_execution", run_id="v3_run", attributes={"visibility.scan_id": "v3_run"}
    ):
        pass

    def mock_columns(spec, **kwargs):
        n = spec if isinstance(spec, int) else len(spec)
        return [MagicMock() for _ in range(n)]

    with patch("streamlit.header"), \
         patch("streamlit.info"), \
         patch("streamlit.write"), \
         patch("streamlit.selectbox", side_effect=["V3 Visibility Scan", 0]) as mock_sb, \
         patch("streamlit.columns", side_effect=mock_columns), \
         patch("streamlit.expander", return_value=MagicMock()), \
         patch("streamlit.table"):

        render_observability_tab()
        # The selectbox for runs should be called with key keyed to v3
        sb_calls = mock_sb.call_args_list
        assert any(c[1].get("key") == "v5_selected_run_idx_v3" for c in sb_calls)
