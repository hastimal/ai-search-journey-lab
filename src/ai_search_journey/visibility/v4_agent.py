"""V4 AI Visibility Agent Module using Google ADK and MCP."""

import os
from typing import Any

from google.adk import Agent
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp.client.stdio import StdioServerParameters

V4_AGENT_INSTRUCTIONS = """You are the AI Visibility Agent [V4] for the AI Search Journey Lab.
Your role is to answer questions about historical brand visibility using strictly read-only
analytics data.

Strict Guidelines:
1. NO INVENTION: You must NOT invent metrics, scan history, trends, citations,
   competitors, or dates.
2. TOOL DEPENDENCE: You MUST use the provided analytical tools to gather factual data.
3. GROUNDING: Every final answer MUST explicitly state the applied date range
   and identify the tool data used.
4. EMPTY HISTORY: If the history is empty or insufficient, you MUST say so clearly.
   Do not attempt to guess or hallucinate data.
5. You must use ISO 8601 formats for dates when calling tools (e.g. 2023-01-01T00:00:00Z).
"""

def create_v4_agent() -> Agent:
    """Creates the V4 AI Visibility Agent using Google ADK and an MCP Toolset."""
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "ai_search_journey.visibility.mcp_server"],
        env=os.environ.copy()
    )
    mcp_params = StdioConnectionParams(server_params=server_params)
    
    mcp_toolset = McpToolset(connection_params=mcp_params)

    return Agent(
        name="VisibilityAnalyticsAgent",
        instruction=V4_AGENT_INSTRUCTIONS,
        model="gemini-2.5-flash",
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
        
        runner = Runner(
            agent=self.agent,
            session_service=InMemorySessionService(),
            app_name="test_app"
        )
        
        events = runner.run(
            user_id="user1", 
            session_id="session1", 
            new_message=types.Content(role="user", parts=[types.Part.from_text(text=query)])
        )
        
        # In this simplistic wrapper for the demo, we just return the final text event.
        texts = []
        for event in events:
            if hasattr(event, "text"):
                texts.append(str(event.text))
        return "".join(texts)
