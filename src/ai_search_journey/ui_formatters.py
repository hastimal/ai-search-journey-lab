"""UI Data formatting and inspection utilities for AI Search Journey Lab GUI.

Kept cleanly separated from Streamlit rendering for high testability.
"""

from typing import Optional

from ai_search_journey.models import (
    ConstraintResult,
    ConstraintStatus,
    JourneyExecutionTrace,
    JourneyResult,
    RankedCandidate,
    SearchIntent,
)

MARKER_LETTERS = ["A", "B", "C"]


def format_source_badge(source_type: str) -> str:
    """Format standard visual badge label for evidence sources and derived values."""
    s = source_type.lower()
    if "places" in s and "search" in s:
        return "PLACES + SEARCH"
    if "places" in s:
        return "GOOGLE PLACES"
    if "search" in s:
        return "GOOGLE SEARCH"
    if "derived" in s or "calc" in s or "score" in s or "proximity" in s:
        return "DERIVED"
    return source_type.upper()


def format_rank_movement_badge(movement: Optional[int]) -> str:
    """Format standard visual badge for rank movement."""
    if movement is None:
        return "● Direct"
    if movement > 0:
        return f"▲ +{movement}"
    if movement < 0:
        return f"▼ {movement}"
    return "● Unchanged"


def format_constraint_cell(r: ConstraintResult) -> str:
    """Format constraint status with multi-source provenance for the constraint matrix table."""
    if r.status == ConstraintStatus.UNKNOWN:
        return "?"

    symbol = "✓" if r.status == ConstraintStatus.SUPPORTED else "✗"

    if not r.supporting_evidence:
        return symbol

    sources: set[str] = set()
    for s in r.supporting_evidence:
        if s.source_type == "google_places":
            sources.add("PLACES")
        elif s.source_type == "google_search":
            sources.add("SEARCH")

    if "PLACES" in sources and "SEARCH" in sources:
        src_label = "PLACES + SEARCH"
    elif "PLACES" in sources:
        src_label = "PLACES"
    elif "SEARCH" in sources:
        src_label = "SEARCH"
    else:
        src_label = ""

    all_task_ids: list[str] = []
    for s in r.supporting_evidence:
        for tid in s.fanout_task_ids:
            if tid and tid not in all_task_ids:
                all_task_ids.append(tid)

    task_str = f"[{','.join(all_task_ids)}]" if all_task_ids else ""
    return f"{symbol} {src_label} {task_str}".strip()


def build_constraint_matrix_data(
    journey: JourneyResult,
) -> tuple[list[str], list[dict[str, str]]]:
    """Extract table columns and rows from JourneyResult constraint evaluations."""
    if not journey.constraint_result or not journey.constraint_result.evaluations:
        return [], []

    # Extract all unique constraint names in order of appearance
    constraint_names: list[str] = []
    for c_eval in journey.constraint_result.evaluations:
        for r in c_eval.results:
            if r.constraint not in constraint_names:
                constraint_names.append(r.constraint)

    rows: list[dict[str, str]] = []
    for c_eval in journey.constraint_result.evaluations:
        row: dict[str, str] = {"Candidate": c_eval.candidate.name}
        for r in c_eval.results:
            row[r.constraint] = format_constraint_cell(r)
        # Fill any missing constraints as "?"
        for cn in constraint_names:
            if cn not in row:
                row[cn] = "?"
        rows.append(row)

    headers = ["Candidate"] + constraint_names
    return headers, rows


def get_marker_label(index: int) -> str:
    """Return marker label A, B, C for index 0, 1, 2 or string number."""
    if 0 <= index < len(MARKER_LETTERS):
        return MARKER_LETTERS[index]
    return str(index + 1)


def format_candidate_summary_card(
    ranked_cand: RankedCandidate,
    index: int,
) -> dict[str, str]:
    """Format structured metadata card for V1 Top 3 candidates."""
    cand = ranked_cand.candidate
    letter = get_marker_label(index)
    dist_str = (
        f"{ranked_cand.distance_miles:.2f} mi"
        if ranked_cand.distance_miles is not None
        else "N/A"
    )
    cat_status = (
        ranked_cand.category_eligibility.status.value.upper()
        if ranked_cand.category_eligibility
        else "UNKNOWN"
    )
    req_cat = (
        ranked_cand.category_eligibility.requested_category
        if ranked_cand.category_eligibility
        else "N/A"
    )
    rating_str = f"{cand.rating}★" if cand.rating is not None else "N/A"
    reviews_str = f"{cand.user_rating_count:,}" if cand.user_rating_count is not None else "0"

    return {
        "letter": letter,
        "rank": f"#{ranked_cand.rank}",
        "name": cand.name,
        "score": f"{ranked_cand.score:.2f}",
        "distance": dist_str,
        "rating": f"{rating_str} ({reviews_str} reviews)",
        "requested_category": req_cat,
        "primary_type": cand.primary_type or "N/A",
        "category_status": cat_status,
        "types": ", ".join(cand.place_types) if cand.place_types else "N/A",
        "google_maps_url": cand.google_maps_url or "",
    }


def format_candidate_journey_card(
    ranked_cand: RankedCandidate,
    index: int,
) -> dict[str, str]:
    """Format structured metadata card for V2 Journey Analysis with SJO fields."""
    card = format_candidate_summary_card(ranked_cand, index)

    ret_pos_str = (
        f"#{ranked_cand.best_retrieval_position}"
        if ranked_cand.best_retrieval_position is not None
        else "N/A"
    )
    movement_str = (
        f"{ranked_cand.rank_movement:+d}"
        if ranked_cand.rank_movement is not None
        else "N/A"
    )
    movement_badge = format_rank_movement_badge(ranked_cand.rank_movement)

    sb = ranked_cand.score_breakdown
    hard_pts = f"{sb.hard_constraint_points:.1f}" if sb else "N/A"
    pref_pts = f"{sb.preference_points:.1f}" if sb else "N/A"
    penalties_pts = f"{sb.penalties:.1f}" if sb else "N/A"
    prox_pts = f"{sb.proximity_points:.1f}" if sb else f"{ranked_cand.proximity_score:.1f}"
    qual_pts = f"{sb.quality_points:.1f}" if sb else f"{ranked_cand.quality_score:.1f}"

    card.update(
        {
            "retrieval_position": ret_pos_str,
            "rank_movement": movement_str,
            "movement_badge": movement_badge,
            "movement_explanation": ranked_cand.movement_explanation or "",
            "hard_points": hard_pts,
            "pref_points": pref_pts,
            "penalties": penalties_pts,
            "proximity_points": prox_pts,
            "quality_points": qual_pts,
        }
    )
    return card


def format_intent_attributes(intent: SearchIntent) -> list[tuple[str, str]]:
    """Format intent attributes for structured display."""
    types_str = (
        ", ".join(it.value.replace("_", " ").title() for it in intent.intent_types)
        if intent.intent_types
        else "None"
    )
    return [
        ("Intent Types", types_str),
        ("Requested Category", intent.category or "None"),
        ("Reference Location", intent.reference_location or "None"),
        ("Group Size", str(intent.group_size) if intent.group_size is not None else "None"),
        ("Open After", intent.open_after or "None"),
        ("Open Before", intent.open_before or "None"),
        (
            "Hard Constraints",
            ", ".join(intent.hard_constraints) if intent.hard_constraints else "None",
        ),
        (
            "Preferences",
            ", ".join(intent.preferences) if intent.preferences else "None",
        ),
        ("Requested Results", str(intent.requested_result_count)),
    ]


def redact_api_key(url: Optional[str]) -> str:
    """Redact any API key in a URL string for safe UI presentation."""
    if not url:
        return ""
    import re
    return re.sub(r"key=[A-Za-z0-9_\-]+", "key=REDACTED", url)


def format_step_status_symbol(status: str) -> str:
    """Return clean status symbol for execution trace steps (✓, →, ○, ✗)."""
    s = str(status).lower()
    if "completed" in s:
        return "✓"
    if "running" in s:
        return "→"
    if "failed" in s:
        return "✗"
    return "○"


def format_step_duration(duration_seconds: Optional[float]) -> str:
    """Format step duration in seconds with 1-2 decimal places."""
    if duration_seconds is None:
        return ""
    if duration_seconds < 0.05:
        return f"{duration_seconds:.2f}s"
    return f"{duration_seconds:.1f}s"


def format_preview_list(items: list[str], max_items: int = 5) -> list[str]:
    """Format a list of strings with truncation and '+ N more' indicator."""
    if not items:
        return []
    if len(items) <= max_items:
        return [f"- {it}" for it in items]
    shown = [f"- {it}" for it in items[:max_items]]
    remaining = len(items) - max_items
    shown.append(f"  *+ {remaining} more*")
    return shown


def extract_source_domain(url: str) -> str:
    """Extract clean domain/host name from a URL string."""
    if not url:
        return ""
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        if domain.startswith("www."):
            domain = domain[4:]
        return domain or url
    except Exception:
        return url


def _render_timeline_steps(
    trace: JourneyExecutionTrace,
    journey: Optional[JourneyResult] = None,
) -> None:
    """Render the list of steps and nested inspection details."""
    import streamlit as st

    from ai_search_journey.models import (
        ConstraintStatus,
        ToolName,
    )

    for step in trace.steps:
        st_val = step.status.value if hasattr(step.status, "value") else str(step.status)
        sym = format_step_status_symbol(st_val)
        dur_str = format_step_duration(step.duration_seconds)

        if sym == "✓":
            label_md = f":green[**✓**] **{step.label}**"
        elif sym == "→":
            label_md = f":blue[**→**] **{step.label}** *(running...)*"
        elif sym == "✗":
            label_md = f":red[**✗**] **{step.label}**"
        else:
            label_md = f":gray[○] :gray[{step.label}]"

        col_l, col_r = st.columns([4, 1])
        with col_l:
            st.markdown(label_md)
            if step.detail and sym in ("✓", "→"):
                st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp;↳ {step.detail}")
            elif step.error and sym == "✗":
                st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp;⚠️ {step.error}")
        with col_r:
            if dur_str:
                st.caption(f"`{dur_str}`")

        # Compact expandable inspection views when full journey context is available
        if journey and sym == "✓":
            # 1. Normalization Details
            if step.key == "normalize" and journey.candidates:
                with st.expander("🔍 View normalization details", expanded=False):
                    st.markdown("- **Deduplication Key:** `Google Place ID`")
                    st.markdown(f"- **Unique Candidates Retained:** `{len(journey.candidates)}`")
                    if step.detail:
                        st.caption(step.detail)

            # 2. Search Grounding Details (Tasks, Planner Query vs Executed Search Queries, Sources)
            elif step.key == "search" and journey.search_results:
                with st.expander("🔎 View Search details", expanded=False):
                    search_fanouts = [
                        q for q in journey.fanout if q.tool == ToolName.GOOGLE_SEARCH
                    ]
                    for s_res in journey.search_results:
                        task_id = s_res.task_id or "F?"
                        matching_fo = next(
                            (f for f in search_fanouts if f.task_id == task_id), None
                        )
                        goal_str = matching_fo.goal if matching_fo else "Grounding"
                        st.markdown(f"**{task_id} [SEARCH]** — *Goal: {goal_str}*")
                        st.markdown(f"**Planner Query:** `{s_res.planner_query}`")

                        st.markdown("**Executed Google Search Queries:**")
                        if s_res.executed_search_queries:
                            for q_line in format_preview_list(s_res.executed_search_queries, 5):
                                st.markdown(q_line)
                        else:
                            st.caption("*(None)*")

                        st.markdown("**Sources:**")
                        if s_res.sources:
                            source_labels = []
                            for src in s_res.sources:
                                dom = extract_source_domain(src.url)
                                title_prefix = f"{src.title} ({dom})" if src.title else dom
                                source_labels.append(title_prefix)
                            for s_line in format_preview_list(source_labels, 5):
                                st.markdown(s_line)
                        else:
                            st.caption("*(None)*")
                        st.divider()

            # 3. Evidence Sample
            elif step.key == "evidence" and journey.evidence_result:
                with st.expander("📑 View evidence sample", expanded=False):
                    cands = journey.evidence_result.candidates[:3]
                    for cand_ev in cands:
                        st.markdown(f"**Candidate:** `{cand_ev.candidate.name}`")
                        if cand_ev.structured_evidence:
                            for sev in cand_ev.structured_evidence[:2]:
                                st.markdown(f"- **[PLACES]** `{sev.attribute}`: {sev.claim}")
                        if cand_ev.search_evidence:
                            for wev in cand_ev.search_evidence[:3]:
                                src_dom = extract_source_domain(wev.source_url or "")
                                fo_tag = f"[{wev.fanout_task_id}]" if wev.fanout_task_id else ""
                                st.markdown(
                                    f"- **[SEARCH {fo_tag}]** `{wev.attribute}`: "
                                    f"{wev.claim} *(Source: "
                                    f"{src_dom or wev.source_title or 'web'})*"
                                )
                    total_claims = sum(
                        len(c.structured_evidence) + len(c.search_evidence)
                        for c in journey.evidence_result.candidates
                    )
                    st.caption(
                        f"Showing sample from {len(cands)} candidates "
                        f"({total_claims} total claims)."
                    )

            # 4. Constraint Evaluation Sample
            elif step.key == "constraints" and journey.constraint_result:
                with st.expander("📊 View constraint sample", expanded=False):
                    sample_evals = journey.constraint_result.evaluations[:3]
                    for ev in sample_evals:
                        st.markdown(f"**{ev.candidate.name}:**")
                        for r in ev.results:
                            status_sym = (
                                "✓" if r.status == ConstraintStatus.SUPPORTED
                                else "✗" if r.status == ConstraintStatus.NOT_SATISFIED
                                else "?"
                            )
                            srcs = []
                            for s in r.supporting_evidence:
                                s_lbl = "PLACES" if s.source_type == "google_places" else "SEARCH"
                                t_tasks = ",".join(s.fanout_task_ids)
                                t_lbl = f"[{t_tasks}]" if s.fanout_task_ids else ""
                                srcs.append(f"{s_lbl} {t_lbl}".strip())
                            prov = f"({', '.join(srcs)})" if srcs else ""
                            st.markdown(f"- {status_sym} **{r.constraint}** {prov}")

            # 5. Ranking Factors Sample
            elif step.key == "ranking" and journey.ranking:
                with st.expander("🏆 View ranking factors", expanded=False):
                    for rc in journey.ranking[:3]:
                        dist_str = (
                            f"{rc.distance_miles:.2f} mi"
                            if rc.distance_miles is not None
                            else "N/A"
                        )
                        st.markdown(
                            f"**#{rc.rank} {rc.candidate.name}** — Score: `{rc.score:.2f}`\n"
                            f"- Hard satisfied: `{rc.hard_supported}` | "
                            f"Failed: `{rc.hard_failed}`\n"
                            f"- Preferences matched: `{rc.preference_supported}`\n"
                            f"- Distance: `{dist_str}` "
                            f"(Proximity bonus: `+{rc.proximity_score:.2f}`)\n"
                            f"- Rating quality bonus: `+{rc.quality_score:.2f}`"
                        )


def render_execution_timeline(
    trace: object,
    total_elapsed: Optional[float] = None,
    journey: Optional[JourneyResult] = None,
) -> None:
    """Render the live or completed Search Journey Execution timeline in Streamlit."""
    import streamlit as st

    from ai_search_journey.models import JourneyExecutionTrace

    if not isinstance(trace, JourneyExecutionTrace):
        return

    # COMPLETED STATE: Render inside a collapsible expander (collapsed by default)
    if trace.is_complete:
        dur = trace.total_duration_seconds or (total_elapsed or 0.0)
        expander_title = f"✅ Search Journey Complete · {dur:.1f}s"
        with st.expander(expander_title, expanded=False):
            _render_timeline_steps(trace, journey=journey)
        return

    # FAILED STATE
    if trace.failed_step_key:
        header_title = "❌ **Search Journey Execution Failed**"
        st.markdown(header_title)
        _render_timeline_steps(trace, journey=journey)
        return

    # RUNNING STATE: Live execution panel expanded
    elapsed_str = f"({total_elapsed:.1f}s elapsed)" if total_elapsed is not None else ""
    header_title = f"⏳ **Executing Search Journey...** `{elapsed_str}`"
    st.markdown(header_title)
    _render_timeline_steps(trace, journey=journey)


