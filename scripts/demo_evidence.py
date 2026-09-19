"""Minimal demo script for Evidence Aggregation across Places and Search Grounding."""

import asyncio
import sys

from ai_search_journey.evidence import aggregate_evidence
from ai_search_journey.fanout import generate_fanout
from ai_search_journey.models import (
    Candidate,
    SearchGroundingResult,
    SearchIntent,
    ToolName,
)
from ai_search_journey.normalize import normalize_candidates
from ai_search_journey.places import search_places
from ai_search_journey.planner import extract_intent
from ai_search_journey.search import search_web

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
    print("\n--- EVIDENCE AGGREGATION DEMO ---\n")
    print(f"QUESTION:\n{question}\n")

    try:
        # 1. Intent Extraction
        intent = await extract_intent(question)
        print(format_intent(intent))
        print()

        # 2. Planner Fan-Out
        fanout = await generate_fanout(intent)
        print("PLANNER FAN-OUT:")
        for idx, q in enumerate(fanout, start=1):
            print(f"\n{idx}. [{q.tool.value.upper()}]")
            print(f"   Goal:   {q.goal}")
            print(f"   Query:  {q.query}")
            if q.reason:
                print(f"   Reason: {q.reason}")
        print()

        # 3. Execute Google Places Tasks
        places_tasks = [q for q in fanout if q.tool == ToolName.GOOGLE_PLACES]
        raw_candidate_groups: list[list[Candidate]] = []
        raw_candidates_flat: list[Candidate] = []

        for task in places_tasks:
            candidates = await search_places(task, max_results=10)
            raw_candidate_groups.append(candidates)
            raw_candidates_flat.extend(candidates)

        # 4. Candidate Normalization
        canonical_candidates = normalize_candidates(raw_candidate_groups)

        # 5. Execute Google Search Grounding Tasks
        search_tasks = [q for q in fanout if q.tool == ToolName.GOOGLE_SEARCH]
        search_results: list[SearchGroundingResult] = []

        for task in search_tasks:
            res = await search_web(task)
            search_results.append(res)

        # 6. Evidence Aggregation
        aggregation = aggregate_evidence(canonical_candidates, search_results)

        print("=" * 60)
        print("RETRIEVAL SUMMARY")
        print("=" * 60)
        print(f"Places tasks executed:                 {len(places_tasks)}")
        print(f"Raw Places records retrieved:          {len(raw_candidates_flat)}")
        print(f"Unique Places candidates:              {len(canonical_candidates)}")
        print(f"Search Grounding tasks executed:       {len(search_tasks)}")
        print("=" * 60)
        print()

        with_search = [ce for ce in aggregation.candidates if ce.search_evidence]
        places_only = [ce for ce in aggregation.candidates if not ce.search_evidence]

        print("=" * 60)
        print("EVIDENCE SUMMARY")
        print("=" * 60)
        print(f"Canonical candidates:                  {len(aggregation.candidates)}")
        print(f"Candidates with search evidence:       {len(with_search)}")
        print(f"Candidates with only Places evidence:  {len(places_only)}")
        print(
            f"Unmatched search evidence records:     {len(aggregation.unmatched_search_evidence)}"
        )
        print("=" * 60)
        print()

        print("SAMPLE CANDIDATE EVIDENCE RECORDS:\n")
        # Display candidates with search evidence first, then a couple places-only
        sample_candidates = with_search[:3] + places_only[:2]

        for idx, ce in enumerate(sample_candidates, start=1):
            c = ce.candidate
            print(f"CANDIDATE {idx}: {c.name} (Place ID: {c.place_id})")
            print("-" * 50)
            print("PLACES EVIDENCE:")
            for pe in ce.structured_evidence:
                print(f"  - [{pe.attribute}] {pe.claim}")

            print("\nSEARCH EVIDENCE:")
            if ce.search_evidence:
                for se in ce.search_evidence:
                    print(f"  - \"{se.claim}\"")
                    if se.planner_query:
                        print(f"    Planner Query: {se.planner_query}")
                    if se.source_title:
                        print(f"    Source Title:  {se.source_title}")
                    if se.source_url:
                        print(f"    Source URL:    {se.source_url}")
            else:
                print("  (none matched)")
            print("=" * 60)

        if aggregation.unmatched_search_evidence:
            print("\nSAMPLE UNMATCHED SEARCH EVIDENCE (first 3):")
            print("-" * 50)
            for ue in aggregation.unmatched_search_evidence[:3]:
                print(f"- \"{ue.claim}\"")
                if ue.source_title:
                    print(f"  Source: {ue.source_title} ({ue.source_url})")

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
