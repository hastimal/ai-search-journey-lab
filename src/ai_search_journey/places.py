"""Google Places API (New) retrieval module."""

from typing import Any, Optional

import httpx

from ai_search_journey.config import settings
from ai_search_journey.models import Candidate, FanoutQuery, ToolName

PLACES_SEARCH_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"

FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.location,"
    "places.rating,"
    "places.userRatingCount,"
    "places.regularOpeningHours,"
    "places.websiteUri,"
    "places.googleMapsUri"
)


async def search_places(
    task: FanoutQuery,
    *,
    api_key: Optional[str] = None,
    max_results: int = 10,
    client: Optional[httpx.AsyncClient] = None,
) -> list[Candidate]:
    """Execute a google_places retrieval task against Google Places API (New).

    Args:
        task: FanoutQuery task containing query and tool definition.
        api_key: Optional Google Maps API Key override.
        max_results: Maximum candidate places to retrieve (default: 10).
        client: Optional httpx.AsyncClient instance for dependency injection.

    Returns:
        List of normalized Candidate Pydantic models.

    Raises:
        ValueError: If task tool is not GOOGLE_PLACES or API key is missing.
        RuntimeError: If HTTP network request fails or Google API returns error.
    """
    if task.tool != ToolName.GOOGLE_PLACES:
        raise ValueError(
            f"Invalid tool for search_places: expected '{ToolName.GOOGLE_PLACES.value}', "
            f"got '{task.tool.value}'."
        )

    effective_api_key = api_key or settings.google_maps_api_key
    if not effective_api_key or effective_api_key == "your_google_maps_api_key_here":
        raise ValueError("GOOGLE_MAPS_API_KEY environment variable is not configured.")

    if max_results <= 0:
        raise ValueError("max_results must be greater than 0.")

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": effective_api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }

    payload = {
        "textQuery": task.query,
        "maxResultCount": max_results,
    }

    should_close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=15.0)
        should_close_client = True

    try:
        response = await client.post(
            PLACES_SEARCH_TEXT_URL,
            headers=headers,
            json=payload,
        )
    except Exception as exc:
        raise RuntimeError(f"Google Places API network request failed: {exc}") from exc
    finally:
        if should_close_client:
            await client.aclose()

    if response.status_code != 200:
        raise RuntimeError(
            f"Google Places API error (status {response.status_code}): {response.text}"
        )

    try:
        data: dict[str, Any] = response.json()
    except Exception as exc:
        raise RuntimeError(f"Failed to parse Google Places API response as JSON: {exc}") from exc

    places_raw = data.get("places", [])
    if not places_raw:
        return []

    candidates: list[Candidate] = []
    for raw in places_raw:
        place_id = raw.get("id")
        if not place_id:
            continue

        display_name = raw.get("displayName", {})
        name = display_name.get("text", "") if isinstance(display_name, dict) else ""

        location = raw.get("location", {})
        lat = location.get("latitude") if isinstance(location, dict) else None
        lng = location.get("longitude") if isinstance(location, dict) else None

        opening_hours_raw = raw.get("regularOpeningHours", {})
        weekday_descriptions = (
            opening_hours_raw.get("weekdayDescriptions", [])
            if isinstance(opening_hours_raw, dict)
            else []
        )

        candidates.append(
            Candidate(
                place_id=str(place_id),
                name=str(name) if name else f"Place {place_id}",
                formatted_address=raw.get("formattedAddress"),
                latitude=float(lat) if lat is not None else None,
                longitude=float(lng) if lng is not None else None,
                rating=float(raw["rating"]) if raw.get("rating") is not None else None,
                user_rating_count=int(raw["userRatingCount"])
                if raw.get("userRatingCount") is not None
                else None,
                website_url=raw.get("websiteUri"),
                google_maps_url=raw.get("googleMapsUri"),
                opening_hours=list(weekday_descriptions),
                retrieval_task_ids=[task.task_id] if task.task_id else [],
            )
        )

    return candidates
