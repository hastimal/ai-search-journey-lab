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
    """Verify render_observability_tab shows info banner when no runs exist."""
    with patch("streamlit.info") as mock_info, \
         patch("streamlit.header") as mock_header:
        render_observability_tab()
        mock_header.assert_called_with("Observability [V5]")
        assert any("No journey traces recorded yet" in str(c) for c in mock_info.call_args_list)


def test_render_observability_tab_with_runs(clean_telemetry_store: TelemetryStore):
    """Verify render_observability_tab formats run metrics and span expanders."""
    # Create sample spans
    with trace_span("journey.execution", run_id="run_ui_test", attributes={"attr1": "val1"}):
        with trace_span(
            "journey.intent_parsing", run_id="run_ui_test", attributes={"category": "cafe"}
        ):
            pass

    cols_2 = [MagicMock(), MagicMock()]
    cols_4 = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
    with patch("streamlit.header"), \
         patch("streamlit.info"), \
         patch("streamlit.write"), \
         patch("streamlit.selectbox", side_effect=[0, 0]), \
         patch("streamlit.columns", side_effect=[cols_2, cols_4, cols_2]), \
         patch("streamlit.metric") as mock_metric, \
         patch("streamlit.expander", return_value=MagicMock()), \
         patch("streamlit.table"):

        render_observability_tab()
        # Verify metric and table calls
        assert mock_metric.called
