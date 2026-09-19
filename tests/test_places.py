"""Unit tests for Google Places API (New) retrieval module."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from ai_search_journey.config import settings
from ai_search_journey.models import FanoutQuery, ToolName
from ai_search_journey.places import FIELD_MASK, PLACES_SEARCH_TEXT_URL, search_places


@pytest.mark.asyncio
async def test_search_places_success_mapping() -> None:
    """Verify Google Places API response mapping into Candidate Pydantic objects."""
    task = FanoutQuery(
        goal="Find coffee shops near Geekdom",
        query="coffee shop near Geekdom San Antonio",
        tool=ToolName.GOOGLE_PLACES,
    )

    mock_json = {
        "places": [
            {
                "id": "ChIJ123456789",
                "displayName": {"text": "Local Roast Coffee", "languageCode": "en"},
                "formattedAddress": "112 E Pecan St, San Antonio, TX 78205",
                "location": {"latitude": 29.4267, "longitude": -98.4900},
                "rating": 4.7,
                "userRatingCount": 350,
                "regularOpeningHours": {
                    "weekdayDescriptions": [
                        "Monday: 7:00 AM – 10:00 PM",
                        "Tuesday: 7:00 AM – 10:00 PM",
                    ]
                },
                "websiteUri": "https://example.com",
                "googleMapsUri": "https://maps.google.com/?cid=123456789",
            }
        ]
    }

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_json

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)

    candidates = await search_places(
        task,
        api_key="test_places_api_key",
        client=mock_client,
    )

    assert len(candidates) == 1
    c = candidates[0]
    assert c.place_id == "ChIJ123456789"
    assert c.name == "Local Roast Coffee"
    assert c.formatted_address == "112 E Pecan St, San Antonio, TX 78205"
    assert c.latitude == 29.4267
    assert c.longitude == -98.4900
    assert c.rating == 4.7
    assert c.user_rating_count == 350
    assert c.website_url == "https://example.com"
    assert c.google_maps_url == "https://maps.google.com/?cid=123456789"
    assert len(c.opening_hours) == 2
    assert "Monday: 7:00 AM – 10:00 PM" in c.opening_hours

    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args
    assert call_args[0][0] == PLACES_SEARCH_TEXT_URL

    headers = call_args[1]["headers"]
    assert headers["X-Goog-Api-Key"] == "test_places_api_key"
    assert headers["X-Goog-FieldMask"] == FIELD_MASK
    assert "places.id" in headers["X-Goog-FieldMask"]
    assert "*" not in headers["X-Goog-FieldMask"]

    payload = call_args[1]["json"]
    assert payload["textQuery"] == "coffee shop near Geekdom San Antonio"
    assert payload["maxResultCount"] == 10


@pytest.mark.asyncio
async def test_search_places_rejects_google_search_tool() -> None:
    """Verify tasks with tool != GOOGLE_PLACES are rejected with ValueError."""
    task = FanoutQuery(
        goal="Check reviews",
        query="quiet coffee shop reviews",
        tool=ToolName.GOOGLE_SEARCH,
    )

    with pytest.raises(ValueError, match="Invalid tool for search_places"):
        await search_places(task, api_key="test_key")


@pytest.mark.asyncio
async def test_search_places_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify missing GOOGLE_MAPS_API_KEY raises ValueError."""
    monkeypatch.setattr(settings, "google_maps_api_key", None)

    task = FanoutQuery(
        goal="Find places",
        query="coffee shop",
        tool=ToolName.GOOGLE_PLACES,
    )

    with pytest.raises(
        ValueError, match="GOOGLE_MAPS_API_KEY environment variable is not configured"
    ):
        await search_places(task)


@pytest.mark.asyncio
async def test_search_places_http_error_handling() -> None:
    """Verify non-200 HTTP response raises RuntimeError."""
    task = FanoutQuery(
        goal="Find places",
        query="coffee shop",
        tool=ToolName.GOOGLE_PLACES,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 403
    mock_response.text = "API key expired or invalid"

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)

    with pytest.raises(RuntimeError, match="Google Places API error \\(status 403\\)"):
        await search_places(task, api_key="test_key", client=mock_client)


@pytest.mark.asyncio
async def test_search_places_network_exception_handling() -> None:
    """Verify network exceptions are wrapped in RuntimeError."""
    task = FanoutQuery(
        goal="Find places",
        query="coffee shop",
        tool=ToolName.GOOGLE_PLACES,
    )

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(side_effect=httpx.ConnectTimeout("Network timeout"))

    with pytest.raises(RuntimeError, match="Google Places API network request failed"):
        await search_places(task, api_key="test_key", client=mock_client)


@pytest.mark.asyncio
async def test_search_places_empty_results() -> None:
    """Verify empty places array returns empty candidate list."""
    task = FanoutQuery(
        goal="Find places",
        query="nonexistent place",
        tool=ToolName.GOOGLE_PLACES,
    )

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"places": []}

    mock_client = MagicMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)

    candidates = await search_places(task, api_key="test_key", client=mock_client)
    assert candidates == []
