"""V4 UI module for the AI Visibility Agent."""

import os

import streamlit as st

from ai_search_journey.config import settings
from ai_search_journey.visibility.bigquery_repository import _get_bigquery_module


def check_readiness() -> tuple[bool, str]:
    """Check if all requirements are met to run the V4 Agent."""
    if _get_bigquery_module() is None:
        return False, "⚠️ The `google-cloud-bigquery` dependency is missing."

    gemini_key = settings.gemini_api_key or os.environ.get("GEMINI_API_KEY")
    if not gemini_key or gemini_key == "your_gemini_api_key_here":
        return False, "⚠️ GEMINI_API_KEY is not configured. Add it to your `.env` file."

    if not settings.bigquery_project or settings.bigquery_project == "your-gcp-project":
        return False, "⚠️ BigQuery `BIGQUERY_PROJECT` is not configured in `.env`."

    if not settings.bigquery_dataset:
        return False, "⚠️ BigQuery `BIGQUERY_DATASET` is not configured in `.env`."

    if not settings.bigquery_location:
        return False, "⚠️ BigQuery `BIGQUERY_LOCATION` is not configured in `.env`."

    return True, ""

def render_visibility_agent_tab() -> None:
    """Renders the AI Visibility Agent [V4] tab."""
    st.header("AI Visibility Agent [V4]")
    st.write("Conversational analysis of persisted V3 BigQuery visibility history.")
    st.info(
        "🔒 **Read-only BigQuery analysis**: The agent strictly analyzes historical data "
        "and cannot modify the repository or trigger new scans."
    )

    is_ready, error_msg = check_readiness()

    if not is_ready:
        st.error(error_msg)
        return

    # Initialize chat history
    if "v4_chat_history" not in st.session_state:
        st.session_state["v4_chat_history"] = []

    # Chat area in a distinct bordered container
    with st.container(border=True):
        # Empty state
        if not st.session_state["v4_chat_history"]:
            st.markdown(
                "<div style='text-align: center; padding: 2rem; color: #666;'>"
                "<em>Ask about visibility, citations, competitors, or fan-out gaps.</em>"
                "</div>",
                unsafe_allow_html=True
            )

        # Display chat history
        for message in st.session_state["v4_chat_history"]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                has_sources = "sources_used" in message and message["sources_used"]
                if message["role"] == "assistant" and has_sources:
                    with st.expander("Sources / analysis window", expanded=False):
                        st.caption(
                            "Agent used read-only MCP analytics tools to inspect BigQuery history."
                        )

        # Chat input is sticky at the bottom
        user_input = st.chat_input("Ask a question about your brand's AI search visibility...")

    st.caption("Try a grounded question about your persisted visibility history")
    example_prompts = [
        "Which competitors should I prioritize?",
        "Why did our citation share change?",
        "Show the visibility trend for a selected date range.",
        "Which fan-out queries do not mention our brand?",
    ]

    cols = st.columns(len(example_prompts))
    selected_prompt = None
    for i, prompt in enumerate(example_prompts):
        if cols[i].button(prompt, key=f"v4_prompt_{i}", use_container_width=True):
            selected_prompt = prompt

    # If a button was clicked, treat it as input
    if selected_prompt and not user_input:
        user_input = selected_prompt

    if user_input:
        # Append user message
        st.session_state["v4_chat_history"].append({"role": "user", "content": user_input})

        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.status("Connecting to read-only analytics...") as status:
                try:
                    from ai_search_journey.visibility.v4_agent import VisibilityAnalyticsAgent
                    agent = VisibilityAnalyticsAgent()

                    status.update(label="Retrieving grounded metrics...")

                    # Instead of blocking entirely, we could stream, but we aren't faking streaming.
                    # We just let the agent run and update status before it completes.
                    response = agent.run(user_input)

                    status.update(label="Preparing response...", state="complete")

                    st.markdown(response)

                    with st.expander("Sources / analysis window", expanded=False):
                        st.caption(
                            "Agent used read-only MCP analytics tools to inspect BigQuery history."
                        )

                    st.session_state["v4_chat_history"].append({
                        "role": "assistant",
                        "content": response,
                        "sources_used": True
                    })
                except Exception:
                    status.update(label="Error connecting to analytics", state="error")
                    st.error("The agent encountered an error while processing the request.")
                    st.session_state["v4_chat_history"].append({
                        "role": "assistant",
                        "content": "⚠️ Error processing request.",
                        "sources_used": False
                    })
