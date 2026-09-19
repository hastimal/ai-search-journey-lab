"""Full demonstration script for Google ADK Search Journey Orchestration."""

import asyncio
import sys

from ai_search_journey.adk import SearchJourneyAgent
from ai_search_journey.models import (
    ConstraintResult,
    ConstraintStatus,
    JourneyResult,
    RankedCandidate,
    SearchIntent,
)

DEFAULT_QUESTION = (
    "Find a coffee shop near Geekdom San Antonio for 6 people "
    "to work together, preferably quiet, and open after 8 PM."
)

MARKER_LETTERS = ["A", "B", "C"]


def format_intent(intent: SearchIntent) -> str:
    """Format SearchIntent into a human-readable developer-demo string."""
    lines = ["PARSED INTENT", ""]

    lines.append("Search Intent:")
    if intent.intent_types:
        for it in intent.intent_types:
            label = it.value.replace("_", " ").title()
            lines.append(f"  - {label}")
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("Category:")
    lines.append(f"  {intent.category}" if intent.category else "  None")
    lines.append("")

    lines.append("Location:")
    lines.append(f"  {intent.reference_location}" if intent.reference_location else "  None")
    lines.append("")

    lines.append("Group Size:")
    lines.append(f"  {intent.group_size}" if intent.group_size is not None else "  None")
    lines.append("")

    lines.append("Open After:")
    lines.append(f"  {intent.open_after}" if intent.open_after else "  None")
    lines.append("")

    lines.append("Open Before:")
    lines.append(f"  {intent.open_before}" if intent.open_before else "  None")
    lines.append("")

    lines.append("Hard Constraints:")
    if intent.hard_constraints:
        for c in intent.hard_constraints:
            lines.append(f"  - {c}")
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("Preferences:")
    if intent.preferences:
        for p in intent.preferences:
            lines.append(f"  - {p}")
    else:
        lines.append("  (none)")
    lines.append("")

    lines.append("Requested Results:")
    lines.append(f"  {intent.requested_result_count}")

    return "\n".join(lines)


def format_status_provenance(r: ConstraintResult) -> str:
    """Format constraint status with provenance into human readable matrix cell."""
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


def print_top_candidate_summary(
    ranked_cand: RankedCandidate,
    index: int,
) -> None:
    """Print clean summary line for ranked result with category metadata."""
    cand = ranked_cand.candidate
    letter = MARKER_LETTERS[index] if index < len(MARKER_LETTERS) else str(index + 1)
    dist_str = (
        f"{ranked_cand.distance_miles:.2f} mi" if ranked_cand.distance_miles is not None else "N/A"
    )
    cat_status = (
        ranked_cand.category_eligibility.status.value
        if ranked_cand.category_eligibility
        else "N/A"
    )
    primary_t = cand.primary_type or "none"
    types_preview = ", ".join(cand.place_types[:4]) if cand.place_types else "none"

    print(
        f"{letter}. #{ranked_cand.rank} {cand.name}\n"
        f"   Score: {ranked_cand.score:.2f} | Distance: {dist_str} | Category: {cat_status}\n"
        f"   Primary Type: {primary_t} | Types: [{types_preview}]"
    )


async def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUESTION
    print("\n--- GOOGLE ADK SEARCH JOURNEY DEMO ---\n")
    print(f"QUESTION:\n{question}\n")

    try:
        agent = SearchJourneyAgent()
        journey: JourneyResult = await agent.run(
            question,
            on_trace=lambda step: print(step),
        )
        print()

        # 1. Parsed Intent
        print("=" * 65)
        print(format_intent(journey.intent))
        print("=" * 65)
        print()

        # 1b. Reference Location
        if journey.reference_location:
            ref = journey.reference_location
            print("=" * 65)
            print("REFERENCE LOCATION")
            print("=" * 65)
            print(f"Query:        {ref.query}")
            print(f"Name:         {ref.name}")
            if ref.formatted_address:
                print(f"Address:      {ref.formatted_address}")
            print(f"Coordinates:  ({ref.latitude:.5f}, {ref.longitude:.5f})")
            print("=" * 65)
            print()

        # 2. Query Fan-Out
        print("=" * 65)
        print("QUERY FAN-OUT")
        print("=" * 65)
        for q in journey.fanout:
            task_label = q.task_id or "F"
            print(f"\n{task_label} [{q.tool.value.upper()}]")
            print(f"   Goal:   {q.goal}")
            print(f"   Query:  {q.query}")
        print("=" * 65)
        print()

        # 3. Retrieval Summary
        print("=" * 65)
        print("RETRIEVAL SUMMARY")
        print("=" * 65)
        print(f"Total Unique Candidates Retrieved: {len(journey.candidates)}")
        for idx, cand in enumerate(journey.candidates[:8], 1):
            tasks_str = (
                f"[{','.join(cand.retrieval_task_ids)}]" if cand.retrieval_task_ids else ""
            )
            print(f"  {idx}. {cand.name} {tasks_str} ({cand.primary_type or 'N/A'})")
        if len(journey.candidates) > 8:
            print(f"  ... and {len(journey.candidates) - 8} more candidates")
        print("=" * 65)
        print()

        # 4. Search Grounding Summary
        print("=" * 65)
        print("SEARCH GROUNDING SUMMARY")
        print("=" * 65)
        print(f"Search Grounding Tasks Executed: {len(journey.search_results)}")
        for sr in journey.search_results:
            print(f"\n[{sr.task_id or 'SEARCH'}] Query: '{sr.planner_query}'")
            print(f"Sources Found: {len(sr.sources)}")
            for src in sr.sources[:3]:
                print(f"  - {src.title or 'Source'}: {src.url}")
        print("=" * 65)
        print()

        # 5. Constraint Matrix
        if journey.constraint_result:
            print("=" * 65)
            print("CONSTRAINT MATRIX")
            print("=" * 65)
            for c_eval in journey.constraint_result.evaluations[:5]:
                print(f"\nCandidate: {c_eval.candidate.name}")
                for r in c_eval.results:
                    print(f"  {r.constraint:<30} -> {format_status_provenance(r)}")
            print("=" * 65)
            print()

        # 6. Deterministic Ranking Top 3
        top_candidates = journey.ranking[:3]
        print("=" * 65)
        print(f"RANKING TOP {len(top_candidates)}")
        print("=" * 65)
        for idx, top_cand in enumerate(top_candidates):
            print_top_candidate_summary(top_cand, idx)
        print("=" * 65)
        print()

        # 7. Static Map Preview
        if journey.static_map:
            print("=" * 65)
            print("STATIC MAP")
            print("=" * 65)
            for marker in journey.static_map.markers:
                print(f"{marker.label} -> {marker.candidate_name}")
            print(f"\nStatic Map URL:\n{journey.static_map.redacted_url}")
            print("=" * 65)
            print()

        # 8. Grounded Final Answer
        if journey.answer:
            print("=" * 65)
            print("FINAL GROUNDED ANSWER")
            print("=" * 65)
            print(f"Summary:\n{journey.answer.summary}\n")

            for rec in journey.answer.recommendations:
                print(f"#{rec.rank} {rec.candidate_name}")
                print(f"Summary: {rec.summary}")

                print("\nWhy it matches:")
                if rec.why_it_matches:
                    for match in rec.why_it_matches:
                        print(f"  - {match}")
                else:
                    print("  (none)")

                print("\nUnknown / unverified:")
                if rec.unknowns:
                    for unk in rec.unknowns:
                        print(f"  - {unk}")
                else:
                    print("  (none)")

                print("\nConflicts:")
                if rec.conflicts:
                    for conf in rec.conflicts:
                        print(f"  - {conf}")
                else:
                    print("  (none)")

                print("\nEvidence Sources:")
                if rec.evidence_sources:
                    for src in rec.evidence_sources:
                        print(f"  - {src}")
                else:
                    print("  - Google Places")

                if rec.maps_url:
                    print(f"\nGoogle Maps:\n{rec.maps_url}")
                print("-" * 65)

            if journey.answer.caveats:
                print("\nCAVEATS")
                for caveat in journey.answer.caveats:
                    print(f"- {caveat}")

            print("=" * 65)

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
