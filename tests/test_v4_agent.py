import sys
from unittest import mock

import pytest

from ai_search_journey.config import settings
from ai_search_journey.visibility.v4_agent import (
    VisibilityAnalyticsAgent,
    create_v4_agent,
)


def test_agent_instructions_safety_rules() -> None:
    """1. V4 agent instructions must enforce read-only safety rules and history discovery."""
    agent = create_v4_agent()
    instruction_str = str(agent.instruction)
    assert "NO INVENTION" in instruction_str
    assert "DISCOVER HISTORY FIRST" in instruction_str
    assert "get_available_history" in instruction_str
    assert "SINGLE SCAN / TREND INFERENCE" in instruction_str
    assert "GROUNDING" in instruction_str
    assert "ISO 8601" in instruction_str


def test_agent_uses_canonical_gemini_model_and_sys_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """V4 agent uses shared settings.gemini_model and sys.executable for MCP."""
    monkeypatch.setattr(settings, "gemini_model", "test-custom-gemini-model")
    agent = create_v4_agent()
    assert agent.model == "test-custom-gemini-model"

    toolset = agent.tools[0]
    # Check connection_params for sys.executable
    server_params = getattr(toolset, "connection_params", None)
    if server_params and hasattr(server_params, "server_params"):
        assert server_params.server_params.command == sys.executable


def test_agent_mcp_connection_timeout_is_configured() -> None:
    """V4 agent configures StdioConnectionParams timeout to 30.0 seconds for Cloud Run."""
    agent = create_v4_agent()
    toolset = agent.tools[0]
    connection_params = getattr(toolset, "connection_params", None)
    assert connection_params is not None
    assert connection_params.timeout == 30.0


def test_mcp_server_exposes_read_only_tools() -> None:
    """2. MCP server exposes the named read-only tools including get_available_history."""
    from ai_search_journey.visibility.mcp_server import (
        analyze_citations,
        compare_brands,
        find_fanout_gaps,
        get_available_history,
        get_brand_trend,
        get_visibility_summary,
    )

    assert get_available_history is not None
    assert get_visibility_summary is not None
    assert get_brand_trend is not None
    assert compare_brands is not None
    assert analyze_citations is not None
    assert find_fanout_gaps is not None


def test_unavailable_bigquery_fails_closed_without_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """V4 fails closed with RuntimeError when BigQuery is unconfigured/unavailable."""
    monkeypatch.setattr(settings, "bigquery_project", None)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("BIGQUERY_PROJECT", raising=False)

    import ai_search_journey.visibility.mcp_server as mcp_mod

    mcp_mod.repo = None  # Reset cached repo
    with pytest.raises(RuntimeError, match="BigQuery repository unavailable"):
        mcp_mod.get_repo()


@pytest.mark.asyncio
async def test_tool_input_validates_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    """3. MCP tool validates ISO 8601 inputs and blocks invalid formats."""
    from ai_search_journey.visibility.mcp_server import get_visibility_summary

    with pytest.raises(ValueError):
        get_visibility_summary(
            start_date="not-a-date",
            end_date="2023-12-31T00:00:00Z",
            brand_id="branda",
        )

    # Valid call with mock BigQuery repository instance injected directly
    mock_bq_repo = mock.MagicMock()
    mock_summary_res = mock.MagicMock()
    mock_summary_res.model_dump.return_value = {
        "brand_id": "brand-a",
        "total_scans": 1,
        "mention_rate": 1.0,
        "recommendation_rate": 0.0,
        "citation_rate": 0.0,
    }
    mock_bq_repo.get_visibility_summary.return_value = mock_summary_res

    import ai_search_journey.visibility.mcp_server as mcp_mod

    monkeypatch.setattr(mcp_mod, "repo", mock_bq_repo)

    res = get_visibility_summary(
        start_date="2023-01-01T00:00:00Z",
        end_date="2023-12-31T00:00:00Z",
        brand_id="brand-a",
    )
    assert isinstance(res, dict)
    assert res["total_scans"] == 1


def test_agent_configured_with_mcp_toolset() -> None:
    """4. ADK agent is configured with the MCP toolset."""
    agent = create_v4_agent()
    assert len(agent.tools) == 1
    toolset = agent.tools[0]
    assert type(toolset).__name__ == "McpToolset"


@mock.patch("google.adk.Runner.run")
def test_agent_run_simulated_empty_history(mock_run: mock.MagicMock) -> None:
    """5. Empty history response is returned properly by the agent wrapper."""
    mock_result = mock.MagicMock()
    mock_result.text = "Based on the tool data, the scan history is empty."
    mock_run.return_value = [mock_result]

    agent_wrapper = VisibilityAnalyticsAgent()
    answer = agent_wrapper.run("What is the visibility of XYZ?")

    assert "history is empty" in answer
    mock_run.assert_called_once()
