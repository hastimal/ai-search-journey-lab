"""AI Search Journey Lab — Streamlit Search Journey Inspector GUI.

Developer-oriented Journey Inspector visualizing the complete AI Search Journey:
Question → Intent → Fan-Out → Tools → Evidence → Constraints → Ranking → Map → Answer.
"""

import asyncio
import os
import time
from typing import Optional

import streamlit as st

from ai_search_journey.adk import SearchJourneyAgent
from ai_search_journey.config import settings
from ai_search_journey.models import (
    JourneyExecutionTrace,
    JourneyResult,
    JourneyStepTiming,
    ToolName,
)
from ai_search_journey.ui_assets import (
    render_app_title,
    render_header_logos,
    render_journey_hint,
)
from ai_search_journey.ui_formatters import (
    build_constraint_matrix_data,
    format_candidate_journey_card,
    format_candidate_summary_card,
    format_intent_attributes,
    format_rank_movement_badge,
    format_source_badge,
    render_execution_timeline,
)
from ai_search_journey.visibility.ui import render_visibility_tab
from ai_search_journey.visibility.ui_v4 import render_visibility_agent_tab

DEFAULT_COFFEE_QUERY = (
    "Find a coffee shop near Geekdom San Antonio for 6 people "
    "to work together, preferably quiet, and open after 8 PM."
)

DEFAULT_INDIAN_QUERY = (
    "Find an Indian restaurant near Trinity University for 8 students, "
    "open after 9 PM, with vegetarian options."
)


def render_app() -> None:
    """Render the main Streamlit Search Journey Inspector application."""
    st.set_page_config(
        page_title="AI Search Journey Lab",
        page_icon="🔍",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    # 1. Header Hierarchy: Clean standalone logo, then primary title card & subtitle
    render_header_logos()
    render_app_title()

    # 2. Input Section
    col_input, col_preset = st.columns([3, 1])
    with col_preset:
        preset = st.selectbox(
            "Quick Demo Presets",
            options=["Coffee Shop @ Geekdom", "Indian Restaurant @ Trinity", "Custom"],
            index=0,
        )

    default_val = DEFAULT_COFFEE_QUERY
    if preset == "Indian Restaurant @ Trinity":
        default_val = DEFAULT_INDIAN_QUERY
    elif preset == "Custom":
        default_val = ""

    with col_input:
        user_question = st.text_area(
            "User Search Request",
            value=default_val,
            height=85,
            placeholder="Enter a local search question with constraints...",
        )

    run_clicked = st.button("🚀 Run Search Journey", type="primary", use_container_width=True)

    # Session State management
    if "journey_result" not in st.session_state:
        st.session_state.journey_result = None
    if "journey_error" not in st.session_state:
        st.session_state.journey_error = None

    if run_clicked:
        if not user_question.strip():
            st.warning("Please enter a question to execute the search journey.")
            return

        # Check API keys before execution
        gemini_key = settings.gemini_api_key or os.environ.get("GEMINI_API_KEY")
        maps_key = settings.google_maps_api_key or os.environ.get("GOOGLE_MAPS_API_KEY")

        if not gemini_key or gemini_key == "your_gemini_api_key_here":
            st.error("⚠️ GEMINI_API_KEY is not configured in .env or environment.")
            return
        if not maps_key or maps_key == "your_google_maps_api_key_here":
            st.error("⚠️ GOOGLE_MAPS_API_KEY is not configured in .env or environment.")
            return

        # 3. Live Search Journey Execution Timeline
        timeline_box = st.empty()
        start_time = time.perf_counter()

        def handle_step_update(
            step: Optional[JourneyStepTiming], trace: JourneyExecutionTrace
        ) -> None:
            elapsed_now = max(0.0, time.perf_counter() - start_time)
            with timeline_box.container(border=True):
                render_execution_timeline(trace, total_elapsed=elapsed_now)

        try:
            agent = SearchJourneyAgent()
            journey: JourneyResult = asyncio.run(
                agent.run(user_question.strip(), on_step_update=handle_step_update)
            )
            st.session_state.journey_result = journey
            st.session_state.journey_error = None
            # Update live box with final collapsible trace
            timeline_box.empty()
        except Exception as e:
            st.session_state.journey_error = str(e)
            st.session_state.journey_result = None
            st.error(f"Error during journey execution: {e}")
            return

    journey = st.session_state.journey_result
    if not journey:
        tab_v1, tab_v2, tab_v3, tab_v4 = st.tabs([
            "Search to Decision [V1]",
            "Journey Analysis [V2]",
            "AI Visibility [V3]",
            "AI Visibility Agent [V4]",
        ])
        with tab_v1:
            render_journey_hint()
        with tab_v2:
            render_journey_hint()
        with tab_v3:
            render_visibility_tab(None)
        with tab_v4:
            render_visibility_agent_tab()
        return

    # 3. Search Journey Complete Collapsible Expander (Default collapsed)
    if journey.execution_trace:
        render_execution_timeline(journey.execution_trace, journey=journey)

    # Capability Tabs: V1 (Search to Decision), V2 (Journey Analysis), V3 (AI Visibility), V4
    tab_v1, tab_v2, tab_v3, tab_v4 = st.tabs([
        "Search to Decision [V1]",
        "Journey Analysis [V2]",
        "AI Visibility [V3]",
        "AI Visibility Agent [V4]",
    ])

    # ==================================================================
    # TAB 1: Search to Decision [V1] (Preserves v1.0.0 Interface Exactly)
    # ==================================================================
    with tab_v1:
        tab_overview, tab_fanout, tab_matrix, tab_evidence, tab_trace = st.tabs([
            "🎯 Recommendations & Intent",
            "🔀 Planner Query Fan-Out",
            "📊 Constraint Matrix & Metrics",
            "🔎 Evidence Inspector",
            "🛠️ ADK Developer Trace",
        ])

        # ---------------- SUB-TAB 1: Recommendations & Intent ----------------
        with tab_overview:
            col_left, col_right = st.columns([1, 1])

            # LEFT COLUMN: Google Maps Static Preview & Final Answer
            with col_left:
                st.subheader("🗺️ Static Map Preview")
                if journey.static_map and journey.static_map.url:
                    marker_cnt = journey.static_map.marker_count
                    st.image(
                        journey.static_map.url,
                        caption=f"Google Maps Static API Preview ({marker_cnt} markers: A, B, C)",
                        use_container_width=True,
                    )
                else:
                    st.info("No static map available for the ranked results.")

                st.subheader("📝 Grounded Final Answer")
                if journey.answer:
                    st.info(journey.answer.summary)
                    for rec in journey.answer.recommendations:
                        with st.expander(f"#{rec.rank} {rec.candidate_name}", expanded=True):
                            st.write(rec.summary)
                            if rec.why_it_matches:
                                st.write("**Why it matches:**")
                                for m in rec.why_it_matches:
                                    st.write(f"- {m}")
                            if rec.unknowns:
                                st.write("**Unknown / Unverified:**")
                                for u in rec.unknowns:
                                    st.write(f"- {u}")
                            if rec.maps_url:
                                st.link_button("📍 Open in Google Maps", rec.maps_url)

                    if journey.answer.caveats:
                        st.write("**Caveats & Disclaimers:**")
                        for c in journey.answer.caveats:
                            st.caption(f"⚠️ {c}")
                else:
                    st.warning(
                        "⚠️ Final grounded answer is currently unavailable. "
                        "Deterministic candidate rankings, constraint evaluation, "
                        "and map preview remain fully available."
                    )

            # RIGHT COLUMN: Top 3 Cards & Parsed Intent
            with col_right:
                st.subheader("🏆 Ranked Top 3 Candidates")
                top_candidates = journey.ranking[:3]
                for idx, top_cand in enumerate(top_candidates):
                    card = format_candidate_summary_card(top_cand, idx)
                    with st.container(border=True):
                        col_t1, col_t2 = st.columns([3, 1])
                        with col_t1:
                            st.markdown(f"### {card['letter']}. {card['rank']} {card['name']}")
                        with col_t2:
                            st.metric("Score", card["score"])

                        c_m1, c_m2, c_m3 = st.columns(3)
                        c_m1.caption(f"📍 **Distance:** {card['distance']}")
                        c_m2.caption(f"⭐ **Rating:** {card['rating']}")
                        c_m3.caption(f"🏷️ **Category:** {card['category_status']}")

                        type_line = (
                            f"**Primary Type:** `{card['primary_type']}` | "
                            f"**Types:** {card['types']}"
                        )
                        st.caption(type_line)

                        # Key constraint highlights
                        c_res = top_cand.constraint_results
                        supp_list = [res for res in c_res if res.status.value == "supported"]
                        unk_list = [res for res in c_res if res.status.value == "unknown"]

                        if supp_list:
                            st.write("**Supported Signals:**")
                            for s_item in supp_list:
                                badge = format_source_badge(s_item.source_type or "DERIVED")
                                st.markdown(f"✓ {s_item.constraint} ({badge})")
                        if unk_list:
                            st.write("**Unverified:**")
                            for u_item in unk_list:
                                st.caption(f"? {u_item.constraint}")

                        if card["google_maps_url"]:
                            st.link_button("View on Google Maps", card["google_maps_url"])

                st.subheader("📋 Parsed Search Intent")
                with st.container(border=True):
                    for attr, val in format_intent_attributes(journey.intent):
                        st.write(f"**{attr}:** {val}")

        # ---------------- SUB-TAB 2: Planner Query Fan-Out ----------------
        with tab_fanout:
            st.subheader("🔀 Planner Query Fan-Out")
            st.caption(
                "Gemini analyzes the intent and dynamically generates distinct retrieval tasks."
            )

            for q in journey.fanout:
                is_places = q.tool == ToolName.GOOGLE_PLACES
                badge_class = "badge-places" if is_places else "badge-search"
                badge_label = "GOOGLE PLACES" if is_places else "GOOGLE SEARCH"

                with st.container(border=True):
                    col_f1, col_f2 = st.columns([1, 4])
                    with col_f1:
                        st.markdown(f"### Task {q.task_id or 'F'}")
                        st.markdown(
                            f'<span class="{badge_class}">{badge_label}</span>',
                            unsafe_allow_html=True,
                        )
                    with col_f2:
                        st.markdown(f"**Goal:** {q.goal}")
                        st.markdown(f"**Planner Query:** `{q.query}`")
                        if q.reason:
                            st.caption(f"**Reason:** {q.reason}")

            st.divider()

            # Executed Search Queries Section (Clearly separated)
            st.subheader("🌐 Executed Google Search Queries")
            st.caption(
                "Exact search queries executed by Google Search Grounding for each search task."
            )

            for sr in journey.search_results:
                with st.container(border=True):
                    header = (
                        f"**Search Task:** `{sr.task_id or 'SEARCH'}` | "
                        f"**Planner Query:** `{sr.planner_query}`"
                    )
                    st.markdown(header)
                    if sr.executed_search_queries:
                        st.write("**Executed Search Queries:**")
                        for eq in sr.executed_search_queries:
                            st.markdown(f"- 🔍 `{eq}`")
                    else:
                        st.caption("No sub-queries recorded.")

                    if sr.sources:
                        with st.expander(f"Sources Found ({len(sr.sources)})"):
                            for src_item in sr.sources:
                                st.markdown(f"- [{src_item.title or 'Source'}]({src_item.url})")

        # ---------------- SUB-TAB 3: Constraint Matrix & Metrics ----------------
        with tab_matrix:
            st.subheader("📊 Retrieval Summary Metrics")
            m1, m2, m3, m4, m5 = st.columns(5)
            places_tasks_count = len(
                [q for q in journey.fanout if q.tool == ToolName.GOOGLE_PLACES]
            )
            search_tasks_count = len(
                [q for q in journey.fanout if q.tool == ToolName.GOOGLE_SEARCH]
            )
            top_candidates = journey.ranking[:3]

            m1.metric("Places Tasks", str(places_tasks_count))
            m2.metric("Search Tasks", str(search_tasks_count))
            m3.metric("Unique Candidates", str(len(journey.candidates)))
            m4.metric("Search Findings", str(len(journey.search_results)))
            m5.metric("Top Ranked", str(len(top_candidates)))

            st.subheader("🧩 Candidate Constraint Matrix")
            st.caption(
                "Deterministic evaluation matrix with multi-source provenance. "
                "Legend: ✓ SUPPORTED | ? UNKNOWN | ✗ NOT SATISFIED"
            )

            headers, matrix_rows = build_constraint_matrix_data(journey)
            if matrix_rows:
                st.dataframe(matrix_rows, use_container_width=True, hide_index=True)

            st.subheader("🔍 Constraint Evidence Inspector")
            if journey.constraint_result:
                for c_eval in journey.constraint_result.evaluations:
                    with st.expander(f"Details: {c_eval.candidate.name}"):
                        for r in c_eval.results:
                            st.markdown(f"**{r.constraint}**: `{r.status.value.upper()}`")
                            if r.explanation:
                                st.caption(f"Explanation: {r.explanation}")
                            if r.supporting_evidence:
                                st.write("Supporting Evidence:")
                                for se in r.supporting_evidence:
                                    badge = format_source_badge(se.source_type)
                                    task_ids = se.fanout_task_ids
                                    task_t = f" [{','.join(task_ids)}]" if task_ids else ""
                                    claim_txt = se.evidence_text or "Verified"
                                    st.markdown(f"- **{badge}{task_t}**: {claim_txt}")
                                    if se.source_url:
                                        src_title = se.source_title or "Link"
                                        st.caption(f"  Source: [{src_title}]({se.source_url})")

        # ---------------- SUB-TAB 4: Evidence Inspector ----------------
        with tab_evidence:
            st.subheader("🔎 Structured & Grounded Evidence by Candidate")
            if journey.evidence_result:
                for ce in journey.evidence_result.candidates:
                    with st.expander(f"{ce.candidate.name} ({ce.candidate.primary_type or 'N/A'})"):
                        col_p, col_s = st.columns(2)
                        with col_p:
                            st.markdown("#### 🏢 Google Places Evidence")
                            cand = ce.candidate
                            st.write(f"**Address:** {cand.formatted_address or 'N/A'}")
                            rev_count = cand.user_rating_count or 0
                            st.write(f"**Rating:** {cand.rating or 'N/A'}★ ({rev_count} reviews)")
                            st.write(f"**Primary Type:** `{cand.primary_type or 'None'}`")
                            st.write(f"**Types:** {', '.join(cand.place_types)}")
                            if cand.opening_hours:
                                st.write("**Opening Hours:**")
                                for h in cand.opening_hours:
                                    st.caption(f"- {h}")
                            if cand.google_maps_url:
                                st.link_button("Google Maps Link", cand.google_maps_url)

                        with col_s:
                            st.markdown("#### 🌐 Google Search Grounding Evidence")
                            if ce.search_evidence:
                                for search_ev in ce.search_evidence:
                                    st.markdown(f"**Claim:** {search_ev.claim}")
                                    if search_ev.source_title or search_ev.source_url:
                                        src_t = search_ev.source_title or "Web"
                                        st.caption(f"Source: [{src_t}]({search_ev.source_url})")
                                    if search_ev.planner_query:
                                        st.caption(f"Planner Query: `{search_ev.planner_query}`")
                                    st.divider()
                            else:
                                st.caption("No specific search claims matched to this candidate.")

        # ---------------- SUB-TAB 5: ADK Developer Trace ----------------
        with tab_trace:
            st.subheader("🛠️ ADK Observability Trace")
            st.caption("Step-by-step execution trace generated by SearchJourneyAgent.")
            for step in journey.trace_steps:
                st.code(step, language="text")

    # ==================================================================
    # TAB 2: Journey Analysis [V2] (Search Journey Optimization)
    # ==================================================================
    with tab_v2:
        st.subheader("🚀 Search Journey Optimization (SJO) Analysis")
        st.caption(
            "Analyze how candidates transition from Google Places retrieval positions through "
            "multi-source evidence enrichment to final recommendation positions."
        )

        # D. Coverage Metrics
        avg_ev = 0.0
        avg_cit = 0.0
        if journey.evidence_result and journey.evidence_result.candidates:
            c_list = journey.evidence_result.candidates
            avg_ev = sum(c.evidence_coverage for c in c_list) / len(c_list)
            avg_cit = sum(c.citation_coverage for c in c_list) / len(c_list)

        col_cov1, col_cov2, col_cov3, col_cov4 = st.columns(4)
        col_cov1.metric("Evaluated Candidates", str(len(journey.candidates)))
        col_cov2.metric("Avg Evidence Coverage", f"{avg_ev * 100:.0f}%")
        col_cov3.metric("Avg Citation Coverage", f"{avg_cit * 100:.0f}%")
        if journey.ranking:
            col_cov4.metric("Top Recommendation", journey.ranking[0].candidate.name)

        st.divider()

        # A & B. Search Journey Summary & Movement
        st.subheader("📈 Search Journey Progression Summary")
        journey_summary_rows = []
        for cand_ranked in journey.ranking:
            ret_pos = (
                f"#{cand_ranked.best_retrieval_position}"
                if cand_ranked.best_retrieval_position is not None
                else "N/A"
            )
            ev_pos = (
                f"#{cand_ranked.evidence_enriched_position}"
                if cand_ranked.evidence_enriched_position is not None
                else "N/A"
            )
            rec_pos = (
                f"#{cand_ranked.final_recommendation_position}"
                if cand_ranked.final_recommendation_position is not None
                else "N/A"
            )
            movement_badge = format_rank_movement_badge(cand_ranked.rank_movement)
            journey_summary_rows.append({
                "Candidate": cand_ranked.candidate.name,
                "Places Retrieval Position": ret_pos,
                "Evidence-Enriched Position": ev_pos,
                "Recommendation Position": rec_pos,
                "Rank Movement": movement_badge,
                "Final Score": f"{cand_ranked.score:.2f}",
            })
        if journey_summary_rows:
            st.dataframe(journey_summary_rows, use_container_width=True, hide_index=True)

        st.divider()

        # E. Retrieval Provenance Table
        st.subheader("🧭 Retrieval Provenance by Query")
        st.caption("Exact retrieval tasks and query positions where candidates were discovered.")
        provenance_rows = []
        for cand_ranked in journey.ranking:
            for occ in cand_ranked.candidate.retrieval_occurrences:
                provenance_rows.append({
                    "Candidate": cand_ranked.candidate.name,
                    "Fan-out Task ID": occ.query_task_id or "N/A",
                    "Exact Query Text": occ.query_text,
                    "Position in Result Set": f"#{occ.position}",
                    "Source Name": occ.source_name,
                })
        if provenance_rows:
            st.dataframe(provenance_rows, use_container_width=True, hide_index=True)
        else:
            st.info("No retrieval occurrences recorded.")

        st.divider()

        # C & F. Expandable Details (Movement, Score Breakdown, Occurrences, Reasons)
        st.subheader("🔍 Ranked Candidate Deep-Dive")
        for idx, cand_ranked in enumerate(journey.ranking):
            card = format_candidate_journey_card(cand_ranked, idx)
            badge = card["movement_badge"]
            with st.expander(
                f"#{card['rank']} {card['name']} — Score: {card['score']} | Movement: {badge}",
                expanded=(idx < 3),
            ):
                # Movement explanation
                if card.get("movement_explanation"):
                    st.info(f"🔄 **Movement Explanation:** {card['movement_explanation']}")
                else:
                    st.caption("No movement explanation available.")

                # Transparent Score breakdown
                st.markdown("#### 📊 Transparent Score Breakdown")
                sb = cand_ranked.score_breakdown
                if sb:
                    col_sb1, col_sb2, col_sb3, col_sb4, col_sb5, col_sb6 = st.columns(6)
                    col_sb1.metric("Hard Constraints", f"+{sb.hard_constraint_points:.1f}")
                    col_sb2.metric("Preferences", f"+{sb.preference_points:.1f}")
                    col_sb3.metric("Penalties", f"{sb.penalties:.1f}")
                    col_sb4.metric("Proximity Points", f"+{sb.proximity_points:.1f}")
                    col_sb5.metric("Quality Points", f"+{sb.quality_points:.1f}")
                    col_sb6.metric("Final Score", f"{sb.total_score:.2f}")
                else:
                    st.write(f"Final Score: {cand_ranked.score:.2f}")

                # Retrieval occurrences
                st.markdown("#### 📍 Retrieval Occurrences")
                if cand_ranked.candidate.retrieval_occurrences:
                    for occ in cand_ranked.candidate.retrieval_occurrences:
                        st.markdown(
                            f"- **Task `{occ.query_task_id or 'N/A'}`** ({occ.source_name}): "
                            f"Position `#{occ.position}` for query *\"{occ.query_text}\"*"
                        )
                else:
                    st.caption("No retrieval occurrences recorded.")

                # Supporting ranking reasons
                if cand_ranked.ranking_reasons:
                    st.markdown("#### 🎯 Supporting Ranking Reasons")
                    for reason in cand_ranked.ranking_reasons:
                        st.markdown(f"- {reason}")

    # ==================================================================
    # TAB 3: AI Visibility [V3] (Milestone 6)
    # ==================================================================
    with tab_v3:
        render_visibility_tab(journey)

    # ==================================================================
    # TAB 4: AI Visibility Agent [V4]
    # ==================================================================
    with tab_v4:
        render_visibility_agent_tab()

if __name__ == "__main__":
    render_app()
