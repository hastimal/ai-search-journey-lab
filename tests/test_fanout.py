"""Unit tests for dynamic query fan-out planner."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_search_journey.config import settings
from ai_search_journey.fanout import GeminiFanoutItem, GeminiFanoutResponse, generate_fanout
from ai_search_journey.models import SearchIntent, ToolName


@pytest.mark.asyncio
async def test_generate_fanout_simple_intent_fewer_queries() -> None:
    """Verify simple intent returns a concise plan with fewer queries."""
    intent = SearchIntent(category="coffee shop")

    mock_raw = GeminiFanoutResponse(
        queries=[
            GeminiFanoutItem(
                goal="Discover coffee shops",
                query="coffee shop",
                tool="google_places",
            ),
        ]
    )

    mock_response = MagicMock()
    mock_response.parsed = mock_raw

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    queries = await generate_fanout(intent, client=mock_client)
    assert len(queries) == 1
    assert queries[0].tool == ToolName.GOOGLE_PLACES


@pytest.mark.asyncio
async def test_generate_fanout_multi_constraint_distinct_tasks() -> None:
    """Verify multi-constraint intent produces 4-5 distinct retrieval tasks."""
    intent = SearchIntent(
        category="coffee shop",
        reference_location="Geekdom San Antonio",
        group_size=6,
        open_after="20:00",
        hard_constraints=["open after 20:00", "fits group of 6"],
        preferences=["quiet", "work-friendly"],
    )

    mock_raw = GeminiFanoutResponse(
        queries=[
            GeminiFanoutItem(
                goal="Discover candidate coffee shops near Geekdom",
                query="coffee shop near Geekdom San Antonio",
                tool="google_places",
                reason="Locate candidate places nearby",
            ),
            GeminiFanoutItem(
                goal="Verify late operating hours past 8 PM",
                query="coffee shop near Geekdom San Antonio opening hours",
                tool="google_places",
                reason="Verify operating hours constraint",
            ),
            GeminiFanoutItem(
                goal="Assess quiet work atmosphere evidence",
                query="quiet work friendly coffee shop near Geekdom San Antonio reviews",
                tool="google_search",
                reason="Check qualitative work atmosphere",
            ),
            GeminiFanoutItem(
                goal="Verify seating suitability for group of 6",
                query="coffee shop near Geekdom San Antonio group seating 6 people",
                tool="google_search",
                reason="Check group seating capacity evidence",
            ),
        ]
    )

    mock_response = MagicMock()
    mock_response.parsed = mock_raw

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    queries = await generate_fanout(intent, client=mock_client)
    assert len(queries) == 4
    assert any(q.tool == ToolName.GOOGLE_PLACES for q in queries)
    assert any(q.tool == ToolName.GOOGLE_SEARCH for q in queries)


@pytest.mark.asyncio
async def test_generate_fanout_preserves_group_size_and_semantics() -> None:
    """Verify group size preservation and semantic fidelity in fan-out queries."""
    intent = SearchIntent(
        category="coffee shop",
        reference_location="Geekdom San Antonio",
        group_size=6,
        preferences=["quiet", "work-friendly"],
    )

    mock_raw = GeminiFanoutResponse(
        queries=[
            GeminiFanoutItem(
                goal="Find coffee shops near Geekdom",
                query="coffee shop near Geekdom San Antonio",
                tool="google_places",
            ),
            GeminiFanoutItem(
                goal="Verify quiet work environment for group of 6",
                query="quiet coffee shop for 6 people work near Geekdom San Antonio",
                tool="google_search",
            ),
        ]
    )

    mock_response = MagicMock()
    mock_response.parsed = mock_raw

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    queries = await generate_fanout(intent, client=mock_client)

    search_query = [q for q in queries if q.tool == ToolName.GOOGLE_SEARCH][0]
    assert "study" not in search_query.query.lower()
    assert "6" in search_query.query or "group" in search_query.query.lower()


@pytest.mark.asyncio
async def test_generate_fanout_deduplication() -> None:
    """Verify duplicate queries with the same tool are removed."""
    intent = SearchIntent(category="coffee shop")

    mock_raw = GeminiFanoutResponse(
        queries=[
            GeminiFanoutItem(
                goal="Task 1",
                query="coffee shop San Antonio",
                tool="google_places",
            ),
            GeminiFanoutItem(
                goal="Task 1 Duplicate",
                query="coffee shop San Antonio ",  # extra space normalized
                tool="google_places",
            ),
            GeminiFanoutItem(
                goal="Task 2",
                query="coffee shop San Antonio",
                tool="google_search",  # different tool, kept
            ),
        ]
    )

    mock_response = MagicMock()
    mock_response.parsed = mock_raw

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    queries = await generate_fanout(intent, client=mock_client)
    assert len(queries) == 2


@pytest.mark.asyncio
async def test_generate_fanout_max_queries_limit() -> None:
    """Verify fan-out query count is capped at max_queries."""
    intent = SearchIntent(category="coffee shop")

    raw_items = [
        GeminiFanoutItem(goal=f"Goal {i}", query=f"query {i}", tool="google_places")
        for i in range(10)
    ]
    mock_raw = GeminiFanoutResponse(queries=raw_items)

    mock_response = MagicMock()
    mock_response.parsed = mock_raw

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    queries = await generate_fanout(intent, client=mock_client, max_queries=4)
    assert len(queries) == 4


@pytest.mark.asyncio
async def test_generate_fanout_invalid_max_queries() -> None:
    """Verify max_queries <= 0 raises ValueError."""
    intent = SearchIntent(category="coffee shop")
    with pytest.raises(ValueError, match="max_queries must be greater than 0"):
        await generate_fanout(intent, max_queries=0)


@pytest.mark.asyncio
async def test_generate_fanout_empty_response_handling() -> None:
    """Verify empty response raises RuntimeError."""
    intent = SearchIntent(category="coffee shop")
    mock_raw = GeminiFanoutResponse(queries=[])

    mock_response = MagicMock()
    mock_response.parsed = mock_raw

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    with pytest.raises(RuntimeError, match="empty or unparseable"):
        await generate_fanout(intent, client=mock_client)


@pytest.mark.asyncio
@pytest.mark.skipif(not settings.gemini_api_key, reason="Real GEMINI_API_KEY not configured")
async def test_generate_fanout_real_gemini_integration() -> None:
    """Optional integration test executing against real Gemini API when key is set."""
    intent = SearchIntent(
        category="coffee shop",
        reference_location="Geekdom San Antonio",
        group_size=6,
        open_after="20:00",
        hard_constraints=["open after 20:00"],
        preferences=["quiet"],
    )
    queries = await generate_fanout(intent)
    assert len(queries) > 0
    assert any(q.tool == ToolName.GOOGLE_PLACES for q in queries)
