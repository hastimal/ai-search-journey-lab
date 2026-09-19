"""Unit tests for Gemini + Google Search Grounding module."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_search_journey.config import settings
from ai_search_journey.models import FanoutQuery, ToolName
from ai_search_journey.search import search_web


@pytest.mark.asyncio
async def test_search_web_accepts_google_search_and_extracts_all_metadata() -> None:
    """Verify GOOGLE_SEARCH task executes, calls Gemini with grounding tool, and extracts fields."""
    task = FanoutQuery(
        goal="Assess quiet atmosphere and work environment",
        query="quiet coffee shops to work late near Geekdom San Antonio",
        tool=ToolName.GOOGLE_SEARCH,
        reason="Check if seating exists for 6 people and atmosphere is quiet.",
    )

    # Mock chunk 0
    chunk0 = MagicMock()
    chunk0.web = MagicMock()
    chunk0.web.title = "Top Work Coffee Spots in SA"
    chunk0.web.uri = "https://example.com/work-spots"

    # Mock chunk 1 (duplicate URL to test deduplication)
    chunk1 = MagicMock()
    chunk1.web = MagicMock()
    chunk1.web.title = "Top Work Coffee Spots in SA"
    chunk1.web.uri = "https://example.com/work-spots"

    # Mock chunk 2
    chunk2 = MagicMock()
    chunk2.web = MagicMock()
    chunk2.web.title = "San Antonio Coffee Guide"
    chunk2.web.uri = "https://example.com/guide"

    # Mock support 0
    sup0 = MagicMock()
    sup0.grounding_chunk_indices = [0]
    sup0.segment = MagicMock()
    sup0.segment.start_index = 0
    sup0.segment.end_index = 45
    sup0.segment.text = "Commonwealth Coffeehouse has large group tables."

    mock_grounding_metadata = MagicMock()
    mock_grounding_metadata.web_search_queries = [
        "quiet coffee shops near Geekdom San Antonio",
        "coffee shops San Antonio group seating 6",
    ]
    mock_grounding_metadata.grounding_chunks = [chunk0, chunk1, chunk2]
    mock_grounding_metadata.grounding_supports = [sup0]

    mock_candidate = MagicMock()
    mock_candidate.grounding_metadata = mock_grounding_metadata

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_response.text = (
        "Commonwealth Coffeehouse has large group tables. It offers quiet study areas."
    )

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    result = await search_web(task, client=mock_client)

    assert result.planner_query == task.query
    assert result.grounded_text == mock_response.text
    assert result.executed_search_queries == [
        "quiet coffee shops near Geekdom San Antonio",
        "coffee shops San Antonio group seating 6",
    ]
    # Verify deduplication of source URLs
    assert len(result.sources) == 2
    assert result.sources[0].title == "Top Work Coffee Spots in SA"
    assert result.sources[0].url == "https://example.com/work-spots"
    assert result.sources[1].title == "San Antonio Coffee Guide"
    assert result.sources[1].url == "https://example.com/guide"

    # Verify citation support
    assert len(result.citations) == 1
    assert result.citations[0].start_index == 0
    assert result.citations[0].end_index == 45
    assert result.citations[0].source_indices == [0]
    assert (
        result.citations[0].cited_text
        == "Commonwealth Coffeehouse has large group tables."
    )

    # Verify generate_content call arguments
    mock_client.aio.models.generate_content.assert_called_once()
    call_args = mock_client.aio.models.generate_content.call_args
    assert "quiet coffee shops to work late near Geekdom San Antonio" in call_args[1]["contents"]
    assert "Goal: Assess quiet atmosphere" in call_args[1]["contents"]
    assert len(call_args[1]["config"].tools) == 1


@pytest.mark.asyncio
async def test_search_web_rejects_google_places_task() -> None:
    """Verify tasks with tool != GOOGLE_SEARCH are rejected with ValueError."""
    task = FanoutQuery(
        goal="Find places",
        query="coffee shops",
        tool=ToolName.GOOGLE_PLACES,
    )

    with pytest.raises(ValueError, match="Invalid tool for search_web"):
        await search_web(task)


@pytest.mark.asyncio
async def test_search_web_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify missing GEMINI_API_KEY raises ValueError."""
    monkeypatch.setattr(settings, "gemini_api_key", None)

    task = FanoutQuery(
        goal="Check web",
        query="quiet spots",
        tool=ToolName.GOOGLE_SEARCH,
    )

    with pytest.raises(
        ValueError, match="GEMINI_API_KEY environment variable is not configured"
    ):
        await search_web(task)


@pytest.mark.asyncio
async def test_search_web_empty_response_handling() -> None:
    """Verify empty/missing candidates in response raises RuntimeError."""
    task = FanoutQuery(
        goal="Check web",
        query="quiet spots",
        tool=ToolName.GOOGLE_SEARCH,
    )

    mock_response = MagicMock()
    mock_response.candidates = []

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with pytest.raises(
        RuntimeError, match="Gemini Google Search grounding returned an empty response"
    ):
        await search_web(task, client=mock_client)


@pytest.mark.asyncio
async def test_search_web_missing_grounding_metadata_handled_cleanly() -> None:
    """Verify response with None grounding_metadata produces empty collections without failing."""
    task = FanoutQuery(
        goal="Check web",
        query="quiet spots",
        tool=ToolName.GOOGLE_SEARCH,
    )

    mock_candidate = MagicMock()
    mock_candidate.grounding_metadata = None

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_response.text = "Some factual text without grounding metadata."

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    result = await search_web(task, client=mock_client)

    assert result.grounded_text == "Some factual text without grounding metadata."
    assert result.executed_search_queries == []
    assert result.sources == []
    assert result.citations == []


@pytest.mark.asyncio
async def test_search_web_empty_web_queries_and_sources() -> None:
    """Verify empty executed search queries and chunks are cleanly handled without fake data."""
    task = FanoutQuery(
        goal="Check web",
        query="quiet spots",
        tool=ToolName.GOOGLE_SEARCH,
    )

    mock_grounding_metadata = MagicMock()
    mock_grounding_metadata.web_search_queries = None
    mock_grounding_metadata.grounding_chunks = []
    mock_grounding_metadata.grounding_supports = []

    mock_candidate = MagicMock()
    mock_candidate.grounding_metadata = mock_grounding_metadata

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_response.text = "Result with empty arrays."

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    result = await search_web(task, client=mock_client)

    assert result.executed_search_queries == []
    assert result.sources == []
    assert result.citations == []
