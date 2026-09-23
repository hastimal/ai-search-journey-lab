"""Offline demonstration of V4 Visibility Agent architecture."""

import os
from unittest import mock

# Force the server to use the mock repository so we don't need BigQuery configured
os.environ["USE_MOCK_VISIBILITY_REPO"] = "1"

from ai_search_journey.visibility.v4_agent import VisibilityAnalyticsAgent


def run_demo() -> None:
    print("=====================================================")
    print(" V4 AI Visibility Agent Demonstration")
    print(" Architecture: Google ADK + MCP")
    print("=====================================================")

    agent = VisibilityAnalyticsAgent()
    query = "What is the overall visibility summary for 'target' in 2024?"
    print(f"\nUser Query: {query}\n")

    with mock.patch("google.adk.runners.Runner.run") as mock_run:
        class MockEvent:
            def __init__(self, text: str):
                self.text = text
        
        mock_result = MockEvent(
            "[Agent Final Answer]\n"
            "Based on the data for 2024-01-01 to 2024-12-31, the brand 'target' appeared "
            "in 15 scans with an 80% mention rate."
        )
        mock_run.return_value = [mock_result]
        
        answer = agent.run(query)
        
        print(answer)

if __name__ == "__main__":
    run_demo()
