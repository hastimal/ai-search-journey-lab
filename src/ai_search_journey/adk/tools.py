"""ADK-style tool wrappers for AI Search Journey retrieval components.

These tools wrap existing functions (places.py, search.py, etc.) without duplicating
business logic, providing clean, typed interfaces for orchestration.
"""

from typing import Optional

from ai_search_journey.models import (
    Candidate,
    FanoutQuery,
    ReferenceLocation,
    SearchGroundingResult,
    ToolName,
)
from ai_search_journey.places import resolve_reference_location, search_places
from ai_search_journey.search import search_web


async def places_retrieval_tool(
    query: str,
    *,
    task_id: Optional[str] = None,
    goal: str = "Candidate Discovery",
    max_results: int = 10,
) -> list[Candidate]:
    """Retrieve candidate places from Google Places API (New).

    Wraps ai_search_journey.places.search_places.
    """
    task = FanoutQuery(
        task_id=task_id,
        goal=goal,
        query=query,
        tool=ToolName.GOOGLE_PLACES,
    )
    return await search_places(task, max_results=max_results)


async def search_grounding_tool(
    query: str,
    *,
    task_id: Optional[str] = None,
    goal: str = "Web Grounding",
) -> SearchGroundingResult:
    """Retrieve web grounding evidence using Gemini + Google Search Grounding.

    Wraps ai_search_journey.search.search_web.
    """
    task = FanoutQuery(
        task_id=task_id,
        goal=goal,
        query=query,
        tool=ToolName.GOOGLE_SEARCH,
    )
    return await search_web(task)


async def reference_location_tool(
    location_query: str,
) -> Optional[ReferenceLocation]:
    """Resolve a geographic reference location anchor using Google Places API (New).

    Wraps ai_search_journey.places.resolve_reference_location.
    """
    return await resolve_reference_location(location_query)
