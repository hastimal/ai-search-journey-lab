"""Minimal demo script for Gemini Grounded Final Answer synthesis."""

import asyncio
import sys

from ai_search_journey.answer import generate_grounded_answer
from ai_search_journey.constraints import evaluate_constraints
from ai_search_journey.evidence import aggregate_evidence
from ai_search_journey.fanout import generate_fanout
from ai_search_journey.models import (
    Candidate,
    RankedCandidate,
    ReferenceLocation,
    SearchGroundingResult,
    ToolName,
)
from ai_search_journey.normalize import normalize_candidates
from ai_search_journey.places import resolve_reference_location, search_places
from ai_search_journey.planner import extract_intent
from ai_search_journey.ranking import rank_candidates
from ai_search_journey.search import search_web
from ai_search_journey.static_map import generate_static_map

DEFAULT_QUESTION = (
    "Find a coffee shop near Geekdom San Antonio for 6 people "
    "to work together, preferably quiet, and open after 8 PM."
)

MARKER_LETTERS = ["A", "B", "C"]


def print_top_candidate_summary(
    ranked_cand: RankedCandidate,
    index: int,
    reference_location: ReferenceLocation | None = None,
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
    print("\n--- GROUNDED FINAL ANSWER DEMO ---\n")
    print(f"QUESTION:\n{question}\n")

    try:
        # 1. Intent Extraction
        intent = await extract_intent(question)

        # 1b. Resolve Reference Location (if present)
        ref_loc: ReferenceLocation | None = None
        if intent.reference_location:
            ref_loc = await resolve_reference_location(intent.reference_location)
            print("=" * 65)
            print("REFERENCE LOCATION")
            print("=" * 65)
            if ref_loc:
                print(f"Query:        {ref_loc.query}")
                print(f"Name:         {ref_loc.name}")
                if ref_loc.formatted_address:
                    print(f"Address:      {ref_loc.formatted_address}")
                print(f"Coordinates:  ({ref_loc.latitude:.5f}, {ref_loc.longitude:.5f})")
            else:
                print(f"Could not resolve reference location: '{intent.reference_location}'")
            print("=" * 65)
            print()

        # 2. Planner Fan-Out
        fanout = await generate_fanout(intent)
        print("QUERY FAN-OUT USED:")
        for q in fanout:
            task_label = q.task_id or "F"
            print(f"\n{task_label} [{q.tool.value.upper()}]")
            print(f"   Goal:   {q.goal}")
            print(f"   Query:  {q.query}")
        print()

        # 3. Execute Google Places Tasks
        places_tasks = [q for q in fanout if q.tool == ToolName.GOOGLE_PLACES]
        raw_candidate_groups: list[list[Candidate]] = []

        for task in places_tasks:
            candidates = await search_places(task, max_results=10)
            raw_candidate_groups.append(candidates)

        # 4. Candidate Normalization (excluding reference location anchor)
        canonical_candidates = normalize_candidates(
            raw_candidate_groups,
            reference_location=intent.reference_location,
        )

        # 5. Execute Google Search Grounding Tasks
        search_tasks = [q for q in fanout if q.tool == ToolName.GOOGLE_SEARCH]
        search_results: list[SearchGroundingResult] = []

        for task in search_tasks:
            res = await search_web(task)
            search_results.append(res)

        # 6. Evidence Aggregation
        primary_places_task_id = places_tasks[0].task_id if places_tasks else "F1"
        aggregation = aggregate_evidence(
            canonical_candidates,
            search_results,
            places_task_id=primary_places_task_id,
        )

        # 7. Constraint Evaluation
        eval_matrix = evaluate_constraints(intent, aggregation.candidates)

        # 8. Deterministic Ranking
        ranked_all = rank_candidates(eval_matrix, reference_location=ref_loc)
        top_candidates = ranked_all[:3]

        print("=" * 65)
        print(f"TOP {len(top_candidates)} RANKED RESULTS")
        print("=" * 65)
        for idx, top_cand in enumerate(top_candidates):
            print_top_candidate_summary(top_cand, idx, reference_location=ref_loc)
        print("=" * 65)
        print()

        # 9. Static Map Preview Generation
        static_map_result = generate_static_map(top_candidates, max_candidates=3)

        print("=" * 65)
        print("STATIC MAP")
        print("=" * 65)
        for marker in static_map_result.markers:
            print(f"{marker.label} -> {marker.candidate_name}")
        print(f"\nStatic Map URL:\n{static_map_result.redacted_url}")
        print("=" * 65)
        print()

        # 10. Gemini Grounded Final Answer Synthesis
        grounded_answer = await generate_grounded_answer(
            question=question,
            intent=intent,
            ranked_candidates=top_candidates,
            max_candidates=3,
        )

        print("=" * 65)
        print("FINAL ANSWER")
        print("=" * 65)
        print(f"Summary:\n{grounded_answer.summary}\n")

        for rec in grounded_answer.recommendations:
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

        if grounded_answer.caveats:
            print("\nCAVEATS")
            for caveat in grounded_answer.caveats:
                print(f"- {caveat}")

        print("=" * 65)

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
