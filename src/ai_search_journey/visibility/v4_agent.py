"""V4 AI Visibility Agent Module using Google ADK and MCP."""

import os
import sys
from typing import Any

from google.adk import Agent
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp.client.stdio import StdioServerParameters

from ai_search_journey.config import settings

V4_AGENT_INSTRUCTIONS = """You are the AI Visibility Agent [V4] for the AI Search Journey Lab.
Your role is to answer questions about historical brand visibility using strictly read-only
analytics data.

Strict Guidelines:
1. NO INVENTION & NO HARD-CODED DEFAULTS: You must NOT invent metrics, scan history, trends,
   citations, competitors, or dates. Never assume or hard-code a default brand (such as 'default'
   or 'nike') or arbitrary dates (such as 2024).
2. DISCOVER HISTORY FIRST: Whenever the user omits a brand, omits a date range, or asks broad
   questions about 'available history', 'summary', 'latest', or 'recent', you MUST first call
   the `get_available_history` tool to discover existing scans, real brand IDs, and valid bounds.
3. SINGLE SCAN / TREND INFERENCE: If the available history contains only one scan, you MUST state
   that only one scan is available and that a trend cannot yet be inferred.
4. TOOL DEPENDENCE: You MUST use the provided analytical tools to gather factual data.
5. GROUNDING: Every final answer MUST explicitly state the applied date range, the observed scan
   count, and identify the tool data used.
6. EMPTY HISTORY: If the history is empty or insufficient, you MUST say so clearly.
   Do not attempt to guess or hallucinate data.
7. You must use ISO 8601 formats for dates when calling tools (e.g. 2026-09-24T00:00:00Z).
8. Tool date ranges must not exceed 365 days.
"""

def create_v4_agent() -> Agent:
    """Creates the V4 AI Visibility Agent using Google ADK and an MCP Toolset."""
    if settings.gemini_api_key and "GEMINI_API_KEY" not in os.environ:
        os.environ["GEMINI_API_KEY"] = settings.gemini_api_key

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ai_search_journey.visibility.mcp_server"],
        env=os.environ.copy()
    )
    mcp_params = StdioConnectionParams(server_params=server_params)

    mcp_toolset = McpToolset(connection_params=mcp_params)

    return Agent(
        name="VisibilityAnalyticsAgent",
        instruction=V4_AGENT_INSTRUCTIONS,
        model=settings.gemini_model,
        tools=[mcp_toolset]
    )

class VisibilityAnalyticsAgent:
    """Wrapper class to maintain the expected interface while delegating to ADK."""

    def __init__(self, **kwargs: Any) -> None:
        self.agent = create_v4_agent()

    def run(self, query: str) -> str:
        """Run a single-turn agent interaction.

        Returns:
            The final grounded string answer.
        """
        # Note: If no GOOGLE_API_KEY is set, this will fail. For tests, we mock it.
        # Run the ADK agent synchronously
        import google.genai.types as types
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService

        # If settings.gemini_api_key is configured but GEMINI_API_KEY is absent, safely set it
        from ai_search_journey.config import settings
        if settings.gemini_api_key and "GEMINI_API_KEY" not in os.environ:
            os.environ["GEMINI_API_KEY"] = settings.gemini_api_key

        session_service = InMemorySessionService()
        runner = Runner(
            agent=self.agent,
            session_service=session_service,
            app_name="test_app"
        )

        import uuid
        session_id = str(uuid.uuid4())
        # create the unique session before running
        session_service.create_session_sync(
            session_id=session_id,
            user_id="user1",
            app_name="test_app",
        )

        events = runner.run(
            user_id="user1",
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part.from_text(text=query)])
        )

        texts = []
        for event in events:
            if hasattr(event, "text") and event.text:
                texts.append(str(event.text))
            elif (
                hasattr(event, "content")
                and event.content
                and getattr(event.content, "parts", None)
            ):
                for part in event.content.parts:  # type: ignore[union-attr]
                    if hasattr(part, "text") and part.text:
                        texts.append(str(part.text))
        return "".join(texts)
