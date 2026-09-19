"""Gemini + Google Search Grounding retrieval module."""

from typing import Any, Optional

from google import genai
from google.genai import types

from ai_search_journey.config import settings
from ai_search_journey.models import (
    FanoutQuery,
    SearchCitation,
    SearchGroundingResult,
    SearchSource,
    ToolName,
)

SEARCH_GROUNDING_SYSTEM_INSTRUCTION = (
    "You are an evidence gathering assistant. Use Google Search grounding to gather current, "
    "factual, and qualitative evidence addressing the specific research goal and query.\n"
    "Guidelines:\n"
    "- Provide concise, factual findings grounded in current web sources.\n"
    "- Focus specifically on addressing the criteria in the prompt (e.g. atmosphere, quietness, "
    "group seating capacity, late-night open status, vegetarian options).\n"
    "- Do not invent details not supported by search results.\n"
    "- Do not attempt to produce final overall rankings or final recommendations."
)


def _build_search_prompt(task: FanoutQuery) -> str:
    """Build a concise grounding prompt from a planner FanoutQuery task."""
    prompt_lines = [
        f"Goal: {task.goal}",
        f"Search Query: {task.query}",
    ]
    if task.reason:
        prompt_lines.append(f"Context / Reason: {task.reason}")
    prompt_lines.append(
        "\nProvide factual findings with details for relevant places found on the web."
    )
    return "\n".join(prompt_lines)


def _extract_grounding_metadata(
    grounding_metadata: Any,
) -> tuple[list[str], list[SearchSource], list[SearchCitation]]:
    """Extract executed search queries, deduplicated sources, and citation supports.

    Safely handles None, missing attributes, and both camelCase/snake_case variations.
    """
    if grounding_metadata is None:
        return [], [], []

    # 1. Executed Google Search Queries
    executed_queries: list[str] = []
    raw_queries = (
        getattr(grounding_metadata, "web_search_queries", None)
        or getattr(grounding_metadata, "webSearchQueries", None)
        or []
    )
    if isinstance(raw_queries, list):
        for q in raw_queries:
            if isinstance(q, str) and q.strip():
                executed_queries.append(q.strip())

    # 2. Grounding Chunks / Sources (Deduplicated by URL)
    sources: list[SearchSource] = []
    seen_urls: set[str] = set()
    raw_chunks = (
        getattr(grounding_metadata, "grounding_chunks", None)
        or getattr(grounding_metadata, "groundingChunks", None)
        or []
    )
    if isinstance(raw_chunks, list):
        for chunk in raw_chunks:
            web = getattr(chunk, "web", None)
            if web is not None:
                uri = getattr(web, "uri", None) or getattr(web, "url", None)
                title = getattr(web, "title", None)
                if uri and str(uri) not in seen_urls:
                    seen_urls.add(str(uri))
                    sources.append(
                        SearchSource(
                            title=str(title) if title else None,
                            url=str(uri),
                        )
                    )

    # 3. Grounding Supports / Citations
    citations: list[SearchCitation] = []
    raw_supports = (
        getattr(grounding_metadata, "grounding_supports", None)
        or getattr(grounding_metadata, "groundingSupports", None)
        or []
    )
    if isinstance(raw_supports, list):
        for sup in raw_supports:
            indices = (
                getattr(sup, "grounding_chunk_indices", None)
                or getattr(sup, "groundingChunkIndices", None)
                or []
            )
            segment = getattr(sup, "segment", None)
            start_idx = getattr(segment, "start_index", None)
            if start_idx is None:
                start_idx = getattr(segment, "startIndex", None)

            end_idx = getattr(segment, "end_index", None)
            if end_idx is None:
                end_idx = getattr(segment, "endIndex", None)

            text = getattr(segment, "text", None)

            citations.append(
                SearchCitation(
                    start_index=int(start_idx) if start_idx is not None else None,
                    end_index=int(end_idx) if end_idx is not None else None,
                    source_indices=[int(i) for i in indices] if isinstance(indices, list) else [],
                    cited_text=str(text) if text is not None else None,
                )
            )

    return executed_queries, sources, citations


async def search_web(
    task: FanoutQuery,
    *,
    client: Optional[genai.Client] = None,
) -> SearchGroundingResult:
    """Execute a google_search retrieval task using Gemini + Google Search Grounding.

    Args:
        task: FanoutQuery task containing query and tool definition.
        client: Optional Google GenAI Client (useful for dependency injection / testing).

    Returns:
        SearchGroundingResult containing grounded text, executed search queries, sources,
        and citation supports.

    Raises:
        ValueError: If task tool is not GOOGLE_SEARCH or API key is not configured.
        RuntimeError: If Gemini API call fails or returns an empty response.
    """
    if task.tool != ToolName.GOOGLE_SEARCH:
        raise ValueError(
            f"Invalid tool for search_web: expected '{ToolName.GOOGLE_SEARCH.value}', "
            f"got '{task.tool.value}'."
        )

    if client is None:
        api_key = settings.gemini_api_key
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not configured.")
        client = genai.Client(api_key=api_key)

    prompt = _build_search_prompt(task)

    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(
        system_instruction=SEARCH_GROUNDING_SYSTEM_INSTRUCTION,
        tools=[grounding_tool],
    )

    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=config,
        )
    except Exception as exc:
        raise RuntimeError(f"Gemini Google Search grounding request failed: {exc}") from exc

    if not response or not hasattr(response, "candidates") or not response.candidates:
        raise RuntimeError("Gemini Google Search grounding returned an empty response.")

    candidate = response.candidates[0]
    grounded_text = response.text or ""
    grounding_metadata = getattr(candidate, "grounding_metadata", None)

    executed_queries, sources, citations = _extract_grounding_metadata(grounding_metadata)

    return SearchGroundingResult(
        task_id=task.task_id,
        planner_query=task.query,
        grounded_text=grounded_text,
        executed_search_queries=executed_queries,
        sources=sources,
        citations=citations,
    )
