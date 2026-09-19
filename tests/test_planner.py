"""Unit tests for Gemini structured intent extraction planner."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from ai_search_journey.config import settings
from ai_search_journey.models import IntentType, SearchIntent
from ai_search_journey.planner import GeminiIntentResponse, extract_intent


def test_gemini_intent_response_conversion_to_search_intent() -> None:
    """Verify valid GeminiIntentResponse converts successfully to canonical SearchIntent."""
    raw = GeminiIntentResponse(
        intent_types=["commercial", "local_discovery"],
        category="coffee shop",
        reference_location="Geekdom San Antonio",
        group_size=6,
        open_after="20:00",
        hard_constraints=["open after 8 PM"],
        preferences=["quiet"],
        requested_result_count=3,
    )
    raw_data = raw.model_dump()
    raw_data["intent_types"] = [IntentType(t) for t in raw_data["intent_types"]]
    intent = SearchIntent.model_validate(raw_data)
    assert IntentType.COMMERCIAL in intent.intent_types
    assert IntentType.LOCAL_DISCOVERY in intent.intent_types
    assert intent.category == "coffee shop"
    assert intent.group_size == 6
    assert intent.requested_result_count == 3


def test_invalid_group_size_zero_rejected_by_search_intent() -> None:
    """Verify group_size=0 in GeminiIntentResponse is rejected during SearchIntent validation."""
    raw = GeminiIntentResponse(category="coffee shop", group_size=0)
    with pytest.raises(ValidationError):
        SearchIntent.model_validate(raw.model_dump())


def test_invalid_requested_result_count_zero_rejected_by_search_intent() -> None:
    """Verify requested_result_count=0 is rejected during SearchIntent validation."""
    raw = GeminiIntentResponse(category="coffee shop", requested_result_count=0)
    with pytest.raises(ValidationError):
        SearchIntent.model_validate(raw.model_dump())


@pytest.mark.asyncio
async def test_extract_intent_informational_mocked() -> None:
    """Verify informational request intent extraction."""
    expected_response = GeminiIntentResponse(
        intent_types=["informational"],
        category=None,
    )

    mock_response = MagicMock()
    mock_response.parsed = expected_response

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    result = await extract_intent("How does RAG work?", client=mock_client)
    assert IntentType.INFORMATIONAL in result.intent_types


@pytest.mark.asyncio
async def test_extract_intent_navigational_mocked() -> None:
    """Verify navigational request intent extraction."""
    expected_response = GeminiIntentResponse(
        intent_types=["navigational"],
        reference_location="Geekdom",
    )

    mock_response = MagicMock()
    mock_response.parsed = expected_response

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    result = await extract_intent("Open the Geekdom website", client=mock_client)
    assert IntentType.NAVIGATIONAL in result.intent_types


@pytest.mark.asyncio
async def test_extract_intent_transactional_local_mocked() -> None:
    """Verify transactional + local discovery intent extraction."""
    expected_response = GeminiIntentResponse(
        intent_types=["transactional", "local_discovery"],
        group_size=8,
        hard_constraints=["reserve table"],
    )

    mock_response = MagicMock()
    mock_response.parsed = expected_response

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    result = await extract_intent("Reserve a table for 8 tonight", client=mock_client)
    assert IntentType.TRANSACTIONAL in result.intent_types
    assert IntentType.LOCAL_DISCOVERY in result.intent_types


@pytest.mark.asyncio
async def test_extract_intent_coffee_shop_mocked() -> None:
    """Verify coffee shop request intent extraction with mocked Gemini response."""
    raw_response = GeminiIntentResponse(
        intent_types=["commercial", "local_discovery"],
        category="coffee shop",
        reference_location="Geekdom San Antonio",
        group_size=6,
        open_after="20:00",
        hard_constraints=["open after 8 PM", "accommodate group of 6"],
        preferences=["quiet", "suitable for working together"],
        requested_result_count=3,
    )

    mock_response = MagicMock()
    mock_response.parsed = raw_response

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    question = (
        "Find a coffee shop near Geekdom San Antonio for 6 people "
        "to work together, preferably quiet, and open after 8 PM."
    )

    result = await extract_intent(question, client=mock_client)

    assert IntentType.COMMERCIAL in result.intent_types
    assert IntentType.LOCAL_DISCOVERY in result.intent_types
    assert result.category == "coffee shop"
    assert result.reference_location == "Geekdom San Antonio"
    assert result.group_size == 6
    assert result.open_after == "20:00"
    assert "quiet" in result.preferences
    assert result.requested_result_count == 3
    mock_client.aio.models.generate_content.assert_called_once()


@pytest.mark.asyncio
async def test_extract_intent_indian_restaurant_mocked() -> None:
    """Verify Indian restaurant request intent extraction with mocked response."""
    raw_response = GeminiIntentResponse(
        intent_types=["commercial", "local_discovery"],
        category="Indian restaurant",
        reference_location="Trinity University",
        group_size=8,
        open_after="21:00",
        hard_constraints=["open after 9 PM", "vegetarian options"],
        preferences=["student friendly"],
        requested_result_count=3,
    )

    mock_response = MagicMock()
    mock_response.parsed = raw_response

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    question = (
        "Find an Indian restaurant near Trinity University for 8 students, "
        "open after 9 PM, with vegetarian options."
    )

    result = await extract_intent(question, client=mock_client)

    assert IntentType.COMMERCIAL in result.intent_types
    assert IntentType.LOCAL_DISCOVERY in result.intent_types
    assert result.category == "Indian restaurant"
    assert result.reference_location == "Trinity University"
    assert result.group_size == 8
    assert result.open_after == "21:00"
    assert "vegetarian options" in result.hard_constraints


@pytest.mark.asyncio
async def test_extract_intent_empty_question_rejected() -> None:
    """Verify empty or whitespace questions are rejected before calling Gemini."""
    with pytest.raises(ValueError, match="empty or whitespace"):
        await extract_intent("")

    with pytest.raises(ValueError, match="empty or whitespace"):
        await extract_intent("   \n\t  ")


@pytest.mark.asyncio
async def test_extract_intent_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify missing API key raises ValueError when no client is supplied."""
    monkeypatch.setattr(settings, "gemini_api_key", None)
    with pytest.raises(ValueError, match="GEMINI_API_KEY environment variable is not configured"):
        await extract_intent("Find a coffee shop near Geekdom")


@pytest.mark.asyncio
async def test_extract_intent_api_failure_handling() -> None:
    """Verify Gemini API exceptions are caught and wrapped in RuntimeError."""
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=Exception("API connection timeout")
    )

    with pytest.raises(RuntimeError, match="Gemini API request failed"):
        await extract_intent("Find a coffee shop", client=mock_client)


@pytest.mark.asyncio
@pytest.mark.skipif(not settings.gemini_api_key, reason="Real GEMINI_API_KEY not configured")
async def test_extract_intent_real_gemini_integration() -> None:
    """Optional integration test executing against real Gemini API when key is set."""
    question = (
        "Find a coffee shop near Geekdom San Antonio for 6 people "
        "to work together, preferably quiet, and open after 8 PM."
    )
    intent = await extract_intent(question)
    assert intent.category is not None
    assert "coffee" in intent.category.lower()
    assert len(intent.intent_types) > 0
