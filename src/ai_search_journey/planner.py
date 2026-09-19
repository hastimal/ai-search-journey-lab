"""Planner component for Gemini structured intent extraction."""

from typing import Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from ai_search_journey.config import settings
from ai_search_journey.models import IntentType, SearchIntent


class GeminiIntentResponse(BaseModel):
    """Internal Pydantic schema for Gemini structured output API.

    Omits field validation constraints (such as Field(gt=0)) that generate
    unsupported schema keywords (e.g. exclusiveMinimum) in Gemini's schema parser.
    """

    intent_types: list[str] = Field(default_factory=list)
    category: Optional[str] = None
    reference_location: Optional[str] = None
    group_size: Optional[int] = None
    open_after: Optional[str] = None
    open_before: Optional[str] = None
    hard_constraints: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    requested_result_count: int = 3


SYSTEM_INSTRUCTION = (
    "You are an expert search intent parser. Analyze the user's natural language request "
    "for local discovery and extract a structured SearchIntent payload.\n\n"
    "Intent Classification Guidelines (Multi-Label):\n"
    "- 'informational': seeking general knowledge, concepts, or explanations "
    "(e.g., 'How does RAG work?').\n"
    "- 'navigational': seeking to reach a specific known website, place, or entity.\n"
    "- 'commercial': evaluating, researching, or comparing local options before deciding.\n"
    "- 'transactional': seeking to execute an explicit action such as booking, buying, "
    "or reserving.\n"
    "- 'local_discovery': discovering local venues, places, or services around a location.\n"
    "Note: A query can have multiple labels (e.g., finding nearby coffee shops is both "
    "'commercial' and 'local_discovery'). Do NOT label 'transactional' unless an explicit "
    "action (e.g. reserve, book) is requested.\n\n"
    "Extraction Rules:\n"
    "1. Extract only information supported by the user request. "
    "Do not invent missing constraints.\n"
    "2. Separate hard constraints (must-haves such as explicit opening hours, specific dietary "
    "requirements, or minimum group capacity) from preferences (nice-to-haves like atmosphere).\n"
    "3. Normalize time constraints to 24-hour HH:MM format (e.g., 8 PM -> 20:00, 9 PM -> 21:00).\n"
    "4. Preserve reference locations as mentioned by the user (e.g., 'Geekdom San Antonio').\n"
    "5. Default requested_result_count to 3 unless the user specifies otherwise.\n"
    "6. Leave missing or unmentioned attributes as null / empty."
)


async def extract_intent(
    question: str,
    client: Optional[genai.Client] = None,
) -> SearchIntent:
    """Extract structured SearchIntent from a user question using Gemini.

    Args:
        question: The user's natural language discovery request.
        client: Optional Google GenAI Client (useful for dependency injection / testing).

    Returns:
        SearchIntent Pydantic model populated with extracted parameters.

    Raises:
        ValueError: If the question is blank/empty or if required API configuration is missing.
        RuntimeError: If Gemini API call fails or fails domain validation.
    """
    if not question or not question.strip():
        raise ValueError("User question cannot be empty or whitespace.")

    if client is None:
        api_key = settings.gemini_api_key
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not configured.")
        client = genai.Client(api_key=api_key)

    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=question.strip(),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=GeminiIntentResponse,
            ),
        )
    except Exception as exc:
        raise RuntimeError(f"Gemini API request failed: {exc}") from exc

    raw_response: Optional[GeminiIntentResponse] = None

    if hasattr(response, "parsed") and isinstance(response.parsed, GeminiIntentResponse):
        raw_response = response.parsed
    elif hasattr(response, "text") and response.text:
        try:
            raw_response = GeminiIntentResponse.model_validate_json(response.text)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to parse Gemini response as GeminiIntentResponse: {exc}"
            ) from exc

    if raw_response is None:
        raise RuntimeError("Gemini API returned an empty or unparseable response.")

    raw_data = raw_response.model_dump()

    typed_intents: list[IntentType] = []
    for raw_type in raw_data.get("intent_types", []):
        try:
            typed_intents.append(IntentType(raw_type.strip().lower()))
        except ValueError:
            pass
    raw_data["intent_types"] = typed_intents

    try:
        return SearchIntent.model_validate(raw_data)
    except Exception as exc:
        raise RuntimeError(
            f"Extracted intent failed domain validation: {exc}"
        ) from exc
