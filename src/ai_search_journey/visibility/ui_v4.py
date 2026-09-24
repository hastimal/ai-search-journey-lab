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

    # Editable example prompts
    st.markdown("### Example Prompts")
    example_prompts = [
        "Which competitors should I prioritize?",
        "Why did our citation share change?",
        "Show the visibility trend for a selected date range.",
        "Which fan-out queries do not mention our brand?",
    ]
    
    # We use columns to lay out buttons
    cols = st.columns(len(example_prompts))
    selected_prompt = None
    for i, prompt in enumerate(example_prompts):
        if cols[i].button(prompt, key=f"v4_prompt_{i}"):
            selected_prompt = prompt

    # Initialize chat history
    if "v4_chat_history" not in st.session_state:
        st.session_state["v4_chat_history"] = []

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

    # Chat input
    user_input = st.chat_input("Ask a question about your brand's AI search visibility...")
    
    # If a button was clicked, treat it as input
    if selected_prompt and not user_input:
        user_input = selected_prompt

    if user_input:
        # Append user message
        st.session_state["v4_chat_history"].append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing V3 visibility history..."):
                try:
                    from ai_search_journey.visibility.v4_agent import VisibilityAnalyticsAgent
                    agent = VisibilityAnalyticsAgent()
                    response = agent.run(user_input)
                    
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
                    st.error("The agent encountered an error while processing the request.")
                    st.session_state["v4_chat_history"].append({
                        "role": "assistant", 
                        "content": "⚠️ Error processing request.",
                        "sources_used": False
                    })
