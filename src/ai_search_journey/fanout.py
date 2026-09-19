"""Dynamic query fan-out planner for generating retrieval tasks."""

from typing import Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from ai_search_journey.config import settings
from ai_search_journey.models import FanoutQuery, SearchIntent, ToolName


class GeminiFanoutItem(BaseModel):
    """Internal item schema for Gemini structured output API."""

    goal: str
    query: str
    tool: str
    reason: Optional[str] = None


class GeminiFanoutResponse(BaseModel):
    """Internal container schema for Gemini fan-out queries response."""

    queries: list[GeminiFanoutItem] = Field(default_factory=list)


SYSTEM_INSTRUCTION = (
    "You are an expert retrieval planner for a local discovery search system.\n"
    "Given a structured SearchIntent, decompose it into a set of targeted retrieval tasks "
    "that address distinct information needs.\n\n"
    "Decomposition Principles:\n"
    "- When an intent contains multiple separate requirements, generate distinct retrieval tasks "
    "for each materially different information need rather than combining them into one query.\n"
    "- Examples of distinct retrieval needs include:\n"
    "  * Candidate Discovery (places matching category & reference location)\n"
    "  * Operating Hours Verification (specific open_after or open_before requirements)\n"
    "  * Qualitative Atmosphere (vibe, quietness, work environment)\n"
    "  * Group & Capacity Suitability (space for specified group_size)\n"
    "  * Dietary or Special Attributes (vegetarian options, accessibility, etc.)\n"
    "- For simple intents with few constraints, 1-3 tasks are sufficient.\n"
    "- For multi-constraint intents, generate separate tasks for each distinct need "
    "(typically 4-5 tasks).\n"
    "- Avoid creating redundant tasks just to reach a target count.\n\n"
    "Rules for Tool Routing:\n"
    "1. 'google_places': Use for discovering nearby candidate places, obtaining formatted "
    "addresses, location coordinates, rating counts, opening hours, and structured place data.\n"
    "2. 'google_search': Use for qualitative or web evidence such as atmosphere/vibe, "
    "group suitability, dietary options, or online reviews.\n\n"
    "Strict Guidelines:\n"
    "- Preserve exact user semantics. Do NOT introduce unrequested activities or requirements "
    "(for example, do not add 'study' if the request only mentions 'work').\n"
    "- Include relevant structured constraints (such as explicit group_size) when forming "
    "qualitative group-suitability queries.\n"
    "- Set 'tool' to exactly 'google_places' or 'google_search'."
)


def _deduplicate_queries(queries: list[FanoutQuery]) -> list[FanoutQuery]:
    """Remove duplicate tasks matching on normalized query string and tool name."""
    seen: set[tuple[str, ToolName]] = set()
    unique: list[FanoutQuery] = []
    for q in queries:
        key = (q.query.strip().lower(), q.tool)
        if key not in seen:
            seen.add(key)
            unique.append(q)
    return unique


async def generate_fanout(
    intent: SearchIntent,
    client: Optional[genai.Client] = None,
    max_queries: int = 8,
) -> list[FanoutQuery]:
    """Generate dynamic query fan-out tasks from a SearchIntent.

    Args:
        intent: Structured SearchIntent derived from the user request.
        client: Optional Google GenAI Client instance.
        max_queries: Safety maximum for fan-out query count (default: 8).

    Returns:
        List of FanoutQuery domain objects.

    Raises:
        ValueError: If intent is invalid or max_queries <= 0.
        RuntimeError: If Gemini API fails or returns no valid queries.
    """
    if max_queries <= 0:
        raise ValueError("max_queries must be greater than 0.")

    if client is None:
        api_key = settings.gemini_api_key
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not configured.")
        client = genai.Client(api_key=api_key)

    intent_json = intent.model_dump_json(exclude_none=True)
    prompt = f"Decompose the following SearchIntent into retrieval tasks:\n{intent_json}"

    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=GeminiFanoutResponse,
            ),
        )
    except Exception as exc:
        raise RuntimeError(f"Gemini API fan-out generation failed: {exc}") from exc

    raw_response: Optional[GeminiFanoutResponse] = None

    if hasattr(response, "parsed") and isinstance(response.parsed, GeminiFanoutResponse):
        raw_response = response.parsed
    elif hasattr(response, "text") and response.text:
        try:
            raw_response = GeminiFanoutResponse.model_validate_json(response.text)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to parse Gemini response as GeminiFanoutResponse: {exc}"
            ) from exc

    if raw_response is None or not raw_response.queries:
        raise RuntimeError("Gemini API returned an empty or unparseable fan-out response.")

    domain_queries: list[FanoutQuery] = []
    for item in raw_response.queries:
        if not item.goal.strip() or not item.query.strip():
            continue
        try:
            tool_enum = ToolName(item.tool.strip().lower())
        except ValueError:
            tool_enum = ToolName.GOOGLE_SEARCH

        domain_queries.append(
            FanoutQuery(
                goal=item.goal.strip(),
                query=item.query.strip(),
                tool=tool_enum,
                reason=item.reason.strip() if item.reason else None,
            )
        )

    if not domain_queries:
        raise RuntimeError("No valid fan-out queries were generated.")

    deduped = _deduplicate_queries(domain_queries)
    return deduped[:max_queries]
