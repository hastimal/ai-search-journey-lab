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

def _process_agent_query(query_text: str) -> None:
    """Execute the agent for a user query and render message/status cleanly."""
    with st.chat_message("user"):
        st.markdown(query_text)

    with st.chat_message("assistant"):
        with st.status("Connecting to read-only analytics...") as status:
            try:
                from ai_search_journey.visibility.v4_agent import VisibilityAnalyticsAgent

                agent = VisibilityAnalyticsAgent()
                status.update(label="Retrieving grounded metrics...")
                response = agent.run(query_text)
                status.update(label="Preparing response...", state="complete")
                st.markdown(response)

                with st.expander("Sources / analysis window", expanded=False):
                    st.caption(
                        "Agent used read-only MCP analytics tools to inspect BigQuery history."
                    )

                st.session_state["v4_chat_history"].append({"role": "user", "content": query_text})
                st.session_state["v4_chat_history"].append({
                    "role": "assistant",
                    "content": response,
                    "sources_used": True,
                })
            except Exception as e:
                status.update(label="Error connecting to analytics", state="error")
                err_str = str(e).lower()
                is_model_unavailable = any(
                    s in err_str for s in ("404", "not found", "not_found", "unavailable")
                )
                if is_model_unavailable:
                    st.error(
                        "Configured Gemini model is unavailable. "
                        "Update GEMINI_MODEL and restart the app."
                    )
                else:
                    st.error("The agent encountered an error while processing the request.")
                st.session_state["v4_chat_history"].append({"role": "user", "content": query_text})
                st.session_state["v4_chat_history"].append({
                    "role": "assistant",
                    "content": "⚠️ Error processing request.",
                    "sources_used": False,
                })


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

    # Modern AI agent console styling with low-intensity glow and perimeter accent
    st.markdown(
        """
        <style>
        .v4-agent-console {
            border: 1px solid rgba(59, 130, 246, 0.35);
            border-radius: 12px;
            background: linear-gradient(
                180deg, rgba(15, 23, 42, 0.75) 0%, rgba(15, 23, 42, 0.4) 100%
            );
            box-shadow: 0 0 20px rgba(59, 130, 246, 0.12), inset 0 0 12px rgba(139, 92, 246, 0.08);
            padding: 1.5rem;
            margin-bottom: 1rem;
            position: relative;
            overflow: hidden;
        }
        .v4-agent-console::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; height: 2px;
            background: linear-gradient(
                90deg,
                rgba(59, 130, 246, 0.2),
                rgba(6, 182, 212, 0.8),
                rgba(139, 92, 246, 0.8),
                rgba(59, 130, 246, 0.2)
            );
            animation: v4-scan-line 6s ease-in-out infinite;
        }
        @keyframes v4-scan-line {
            0% { transform: translateX(-100%); }
            50% { transform: translateX(100%); }
            100% { transform: translateX(-100%); }
        }
        .v4-status-badge {
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 0.8rem;
            color: #38bdf8;
            background: rgba(6, 182, 212, 0.12);
            border: 1px solid rgba(56, 189, 248, 0.3);
            border-radius: 6px;
            padding: 0.25rem 0.6rem;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 0.75rem;
        }
        .v4-pulse-dot {
            width: 7px;
            height: 7px;
            background-color: #38bdf8;
            border-radius: 50%;
            box-shadow: 0 0 8px #38bdf8;
        }
        .v4-rotating-text {
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 0.92rem;
            color: #94a3b8;
            height: 1.6rem;
            position: relative;
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .v4-rotating-item {
            position: absolute;
            width: 100%;
            opacity: 0;
            animation: v4-cycle-text 12s infinite ease-in-out;
        }
        .v4-rotating-item:nth-child(1) { animation-delay: 0s; }
        .v4-rotating-item:nth-child(2) { animation-delay: 4s; }
        .v4-rotating-item:nth-child(3) { animation-delay: 8s; }

        @keyframes v4-cycle-text {
            0%, 25% { opacity: 0; transform: translateY(6px); }
            5%, 20% { opacity: 1; transform: translateY(0); }
            30%, 100% { opacity: 0; transform: translateY(-6px); }
        }

        @media (prefers-reduced-motion: reduce) {
            .v4-agent-console::before {
                animation: none;
                transform: none;
            }
            .v4-rotating-item {
                animation: none;
                position: static;
                opacity: 1;
                display: none;
            }
            .v4-rotating-item:first-child {
                display: block;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # 2. Example Prompt Chips (only when chat history is empty)
    selected_prompt = None
    if not st.session_state["v4_chat_history"]:
        st.caption("Try a grounded question about your persisted visibility history")
        example_prompts = [
            "Which competitors should I prioritize?",
            "Why did our citation share change?",
            "Show the visibility trend for a selected date range.",
            "Which fan-out queries do not mention our brand?",
        ]

        cols = st.columns(len(example_prompts))
        for i, prompt in enumerate(example_prompts):
            if cols[i].button(prompt, key=f"v4_prompt_{i}", use_container_width=True):
                selected_prompt = prompt

    # 3. Chat Conversation History Container (oldest → newest)
    with st.container(border=True):
        # Empty state console card (visible only when no history exists and no prompt clicked)
        if not st.session_state["v4_chat_history"] and not selected_prompt:
            st.markdown(
                """
                <div class="v4-agent-console">
                    <div style="text-align: center; margin-bottom: 0.5rem;">
                        <span class="v4-status-badge">
                            <span class="v4-pulse-dot"></span>
                            AI VISIBILITY CONSOLE [READY]
                        </span>
                    </div>
                    <div class="v4-rotating-text">
                        <div class="v4-rotating-item">Inspecting visibility history…</div>
                        <div class="v4-rotating-item">Grounded in read-only BigQuery data…</div>
                        <div class="v4-rotating-item">
                            Ask about citations, competitors, or fan-out gaps.
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # Render existing conversation history: oldest → newest
        for message in st.session_state["v4_chat_history"]:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
                has_sources = "sources_used" in message and message["sources_used"]
                if message["role"] == "assistant" and has_sources:
                    with st.expander("Sources / analysis window", expanded=False):
                        st.caption(
                            "Agent used read-only MCP analytics tools to inspect BigQuery history."
                        )

        # If a prompt chip was clicked this cycle, process it so it renders above chat input
        if selected_prompt:
            _process_agent_query(selected_prompt)

        # 4. Chat input as the final widget at the bottom of the container
        user_input = st.chat_input("Ask a question about your brand's AI search visibility...")
        if user_input:
            _process_agent_query(user_input)
