"""Minimal demo script for testing Google Places API (New) retrieval and Candidate Normalization."""

import asyncio
import sys

from ai_search_journey.fanout import generate_fanout
from ai_search_journey.models import Candidate, SearchIntent, ToolName
from ai_search_journey.normalize import normalize_candidates
from ai_search_journey.places import search_places
from ai_search_journey.planner import extract_intent

DEFAULT_QUESTION = (
    "Find a coffee shop near Geekdom San Antonio for 6 people "
    "to work together, preferably quiet, and open after 8 PM."
)


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


async def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUESTION
    print("\n--- GOOGLE PLACES RETRIEVAL & NORMALIZATION DEMO ---\n")
    print(f"QUESTION:\n{question}\n")

    try:
        intent = await extract_intent(question)
        print(format_intent(intent))
        print()

        fanout = await generate_fanout(intent)
        print("PLANNER FAN-OUT:")
        for idx, q in enumerate(fanout, start=1):
            print(f"\n{idx}. [{q.tool.value.upper()}]")
            print(f"   Goal:   {q.goal}")
            print(f"   Query:  {q.query}")
            if q.reason:
                print(f"   Reason: {q.reason}")
        print()

        places_tasks = [q for q in fanout if q.tool == ToolName.GOOGLE_PLACES]
        print(f"Executing {len(places_tasks)} Google Places API retrieval task(s)...\n")

        raw_candidate_groups: list[list[Candidate]] = []
        raw_candidates_flat: list[Candidate] = []

        for task in places_tasks:
            candidates = await search_places(task, max_results=10)
            raw_candidate_groups.append(candidates)
            raw_candidates_flat.extend(candidates)

        normalized = normalize_candidates(raw_candidate_groups)

        duplicates_removed = len(raw_candidates_flat) - len(normalized)

        print("=" * 60)
        print("RETRIEVAL SUMMARY")
        print("=" * 60)
        print(f"Places tasks executed:                    {len(places_tasks)}")
        print(f"Raw candidate records before normalization: {len(raw_candidates_flat)}")
        print(f"Unique candidates after normalization:    {len(normalized)}")
        print(f"Duplicate records removed:                {duplicates_removed}")
        print("=" * 60)
        print()

        print(f"NORMALIZED CANDIDATES ({len(normalized)} canonical places):\n")
        for idx, c in enumerate(normalized, start=1):
            print(f"Candidate {idx}:")
            print(f"Name:            {c.name}")
            print(f"Place ID:        {c.place_id}")
            print(f"Address:         {c.formatted_address or 'N/A'}")
            print(f"Location:        ({c.latitude}, {c.longitude})")
            print(f"Rating:          {c.rating} ({c.user_rating_count} reviews)")
            print("Opening Hours:")
            if c.opening_hours:
                for h in c.opening_hours:
                    print(f"  - {h}")
            else:
                print("  (none listed)")
            print(f"Website:         {c.website_url or 'N/A'}")
            print(f"Google Maps URL: {c.google_maps_url or 'N/A'}")
            print("-" * 50)

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
