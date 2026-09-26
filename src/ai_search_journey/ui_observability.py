"""Streamlit UI component for Observability [V5].

Visualizes in-process OpenTelemetry traces, spans, execution timelines,
status codes, and sanitized attributes across V1–V4 workflows.
"""

import streamlit as st

from ai_search_journey.config import settings
from ai_search_journey.telemetry.store import TelemetryStore


def render_observability_tab() -> None:
    """Render the Observability [V5] tab."""
    st.header("Observability [V5]")
    st.write(
        "Safe, local, in-process OpenTelemetry telemetry timeline "
        "across the Search Journey pipelines."
    )

    st.info(
        "🔒 **Local Telemetry & Privacy Guard**: Raw prompts, credentials, and sensitive content "
        "are not exported. Telemetry is buffered in-process and can also be sent to the local "
        "OpenTelemetry observability stack when enabled."
    )

    # Local Grafana Observability stack shortcuts
    grafana_base = settings.grafana_url.rstrip("/")
    grafana_dashboard_url = (
        f"{grafana_base}/d/ai-search-journey-overview/ai-search-journey-observability-overview"
    )
    tempo_explore_url = f"{grafana_base}/explore"

    col_btn1, col_btn2, _ = st.columns([1.2, 1.0, 2.0])
    with col_btn1:
        if hasattr(st, "link_button"):
            st.link_button(
                "📊 Open Grafana AgentOps Dashboard",
                grafana_dashboard_url,
                help="Open local Grafana overview dashboard",
            )
        else:
            st.markdown(f"[📊 Open Grafana AgentOps Dashboard]({grafana_dashboard_url})")
    with col_btn2:
        if hasattr(st, "link_button"):
            st.link_button(
                "🔎 Open Tempo Explore",
                tempo_explore_url,
                help="Explore distributed traces in Tempo",
            )
        else:
            st.markdown(f"[🔎 Open Tempo Explore]({tempo_explore_url})")

    st.divider()

    store = TelemetryStore.get_instance()
    runs = store.get_runs()

    if not runs:
        st.info(
            "ℹ️ No journey traces recorded yet. Run a Search Journey [V1], Visibility Scan [V3], "
            "or Agent Interaction [V4] to observe live traces."
        )
        return

    # Filter by workflow stage
    col_filter, col_run = st.columns([1, 2])
    with col_filter:
        stage_filter = st.selectbox(
            "Filter by Workflow",
            options=["All Stages", "V1 Search Journey", "V3 Visibility Scan", "V4 Agent Chat"],
            index=0,
            key="v5_stage_filter",
        )

    stage_code = None
    if stage_filter == "V1 Search Journey":
        stage_code = "v1"
    elif stage_filter == "V3 Visibility Scan":
        stage_code = "v3"
    elif stage_filter == "V4 Agent Chat":
        stage_code = "v4"

    filtered_runs = store.get_runs(stage_filter=stage_code)
    if not filtered_runs:
        st.warning(f"No traces found for filter: {stage_filter}")
        return

    # Select run
    run_options = [
        f"[{r['stage'].upper()}] {r['run_id']} · {r['span_count']} spans · {r['status']}"
        for r in filtered_runs
    ]
    with col_run:
        # Key selector by stage filter to ensure clean reset/revalidation when filter changes
        selected_idx = st.selectbox(
            "Select Execution Run",
            options=range(len(run_options)),
            format_func=lambda i: run_options[i],
            key=f"v5_selected_run_idx_{stage_code or 'all'}",
        )

    if selected_idx is None or selected_idx >= len(filtered_runs):
        selected_idx = 0

    selected_run = filtered_runs[selected_idx]
    run_id = selected_run["run_id"]
    spans = store.get_spans_for_run(run_id)

    st.markdown(f"### ⏱️ Run Timeline: `{run_id}`")

    # Run summary metrics
    total_duration = sum(s.duration_ms for s in spans if not s.parent_span_id)
    if total_duration == 0:
        total_duration = sum(s.duration_ms for s in spans)

    error_spans = [s for s in spans if s.status == "ERROR"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Stage", selected_run["stage"].upper())
    m2.metric("Total Spans", len(spans))
    m3.metric("Duration", f"{total_duration:.1f} ms")
    m4.metric("Status", "❌ ERROR" if error_spans else "✅ OK")

    st.divider()

    # Timeline / Span table
    st.subheader("Span Execution Trace")

    # Display timeline cards
    for span in spans:
        status_icon = "✅" if span.status == "OK" else ("❌" if span.status == "ERROR" else "⚪")
        parent_indicator = "└── " if span.parent_span_id else "■ "
        header_title = (
            f"{status_icon} `{parent_indicator}{span.name}` — "
            f"**{span.duration_ms:.1f} ms** (Status: `{span.status}`)"
        )

        with st.expander(header_title, expanded=(span.status == "ERROR")):
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                st.caption(f"**Span ID:** `{span.span_id}`")
                if span.parent_span_id:
                    st.caption(f"**Parent Span ID:** `{span.parent_span_id}`")
                st.caption(f"**Trace ID:** `{span.trace_id}`")
            with col_s2:
                st.caption(f"**Started:** `{span.start_time_iso}`")
                st.caption(f"**Ended:** `{span.end_time_iso}`")

            if span.error_message:
                st.error(f"**Sanitized Error:** {span.error_message}")

            if span.attributes:
                st.markdown("**Safe Telemetry Attributes:**")
                # Format attributes as a neat Markdown table
                attr_data = [{"Attribute": k, "Value": str(v)} for k, v in span.attributes.items()]
                st.table(attr_data)
            else:
                st.caption("No attributes recorded.")
