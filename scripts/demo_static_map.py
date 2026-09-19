"""Minimal demo script for Google Maps Static API Preview."""

import asyncio
import sys

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


def print_top_candidate(
    ranked_cand: RankedCandidate,
    index: int,
    reference_location: ReferenceLocation | None = None,
) -> None:
    """Print clean formatted card for a top-ranked candidate."""
    cand = ranked_cand.candidate
    letter = MARKER_LETTERS[index] if index < len(MARKER_LETTERS) else str(index + 1)
    print(f"\n{letter}. Candidate #{ranked_cand.rank}")
    print(f"   Name:             {cand.name}")
    print(f"   Score:            {ranked_cand.score:.2f}")
    if cand.formatted_address:
        print(f"   Address:          {cand.formatted_address}")
    if ranked_cand.distance_miles is not None:
        ref_name = reference_location.name if reference_location else "reference location"
        print(f"   Distance:         {ranked_cand.distance_miles:.2f} miles from {ref_name}")
        print(f"   Proximity Bonus:  +{ranked_cand.proximity_score:.2f} pts")
    if cand.latitude is not None and cand.longitude is not None:
        print(f"   Coordinates:      ({cand.latitude:.5f}, {cand.longitude:.5f})")
    if cand.google_maps_url:
        print(f"   Google Maps URL:  {cand.google_maps_url}")


async def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUESTION
    print("\n--- STATIC MAP PREVIEW DEMO ---\n")
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
        print(f"TOP {len(top_candidates)}")
        print("=" * 65)

        for idx, top_cand in enumerate(top_candidates):
            print_top_candidate(top_cand, idx, reference_location=ref_loc)
        print("-" * 65)
        print()

        # 9. Static Map Preview Generation
        static_map_result = generate_static_map(top_candidates, max_candidates=3)

        print("=" * 65)
        print("STATIC MAP")
        print("=" * 65)
        print(f"Marker Count:\n{static_map_result.marker_count}\n")
        print("Markers:")
        for marker in static_map_result.markers:
            print(
                f"{marker.label} -> Candidate #{marker.rank} ({marker.candidate_name}) "
                f"at ({marker.latitude:.5f}, {marker.longitude:.5f})"
            )
        print()
        print(f"Static Map URL:\n{static_map_result.redacted_url}")
        print("=" * 65)

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
