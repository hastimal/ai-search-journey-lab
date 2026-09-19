"""Minimal demo script for Explainable Deterministic Ranking."""

import asyncio
import sys

from ai_search_journey.constraints import evaluate_constraints
from ai_search_journey.evidence import aggregate_evidence
from ai_search_journey.fanout import generate_fanout
from ai_search_journey.models import (
    Candidate,
    ConstraintResult,
    ConstraintStatus,
    RankedCandidate,
    ReferenceLocation,
    SearchGroundingResult,
    SearchIntent,
    ToolName,
)
from ai_search_journey.normalize import normalize_candidates
from ai_search_journey.places import resolve_reference_location, search_places
from ai_search_journey.planner import extract_intent
from ai_search_journey.ranking import rank_candidates
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


def print_top_candidate_card(
    ranked_cand: RankedCandidate,
    reference_location: ReferenceLocation | None = None,
) -> None:
    """Print clean formatted card for a top-ranked candidate."""
    cand = ranked_cand.candidate
    print(f"\n#{ranked_cand.rank} {cand.name}")
    print(f"Score: {ranked_cand.score:.2f}")
    if cand.formatted_address:
        print(f"Address: {cand.formatted_address}")

    if ranked_cand.distance_miles is not None:
        ref_name = reference_location.name if reference_location else "reference location"
        print(f"Distance from {ref_name}: {ranked_cand.distance_miles:.2f} miles")
        print(f"Proximity Bonus: +{ranked_cand.proximity_score:.2f} pts")

    print("\nConstraint Summary:")
    print("  Hard Constraints:")
    print(f"    Supported: {ranked_cand.hard_supported}")
    print(f"    Unknown:   {ranked_cand.hard_unknown}")
    print(f"    Failed:    {ranked_cand.hard_failed}")

    print("  Preferences:")
    print(f"    Supported: {ranked_cand.preference_supported}")
    print(f"    Unknown:   {ranked_cand.preference_unknown}")
    print(f"    Failed:    {ranked_cand.preference_failed}")

    print("\nQuality:")
    rating_str = f"{cand.rating}★" if cand.rating is not None else "N/A"
    rev_str = f"{cand.user_rating_count:,} reviews" if cand.user_rating_count is not None else "N/A"
    print(f"  Rating:  {rating_str}")
    print(f"  Reviews: {rev_str}")
    print(f"  Quality Bonus: +{ranked_cand.quality_score:.1f} pts")

    print("\nSupported Constraints & Provenance:")
    supported_results = [
        r for r in ranked_cand.constraint_results if r.status == ConstraintStatus.SUPPORTED
    ]
    if supported_results:
        for r in supported_results:
            cell_prov = format_status_provenance(r)
            print(f"  {cell_prov:<22} {r.constraint}")
            for s in r.supporting_evidence:
                if s.evidence_text:
                    snippet = s.evidence_text[:110].replace("\n", " ")
                    print(f"    Evidence: \"{snippet}...\"")
    else:
        print("  (none)")

    print("\nWhy Ranked Here:")
    for reason in ranked_cand.ranking_reasons:
        print(f"  - {reason}")
    print("-" * 65)


async def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUESTION
    print("\n--- EXPLAINABLE RANKING DEMO ---\n")
    print(f"QUESTION:\n{question}\n")

    try:
        # 1. Intent Extraction
        intent = await extract_intent(question)
        print(format_intent(intent))
        print()

        # 1b. Resolve Reference Location (if present)
        ref_loc: ReferenceLocation | None = None
        if intent.reference_location:
            print("=" * 65)
            print("REFERENCE LOCATION RESOLUTION")
            print("=" * 65)
            ref_loc = await resolve_reference_location(intent.reference_location)
            if ref_loc:
                print(f"Reference Location: {ref_loc.query}")
                print(f"Name:               {ref_loc.name}")
                if ref_loc.formatted_address:
                    print(f"Address:            {ref_loc.formatted_address}")
                print(f"Latitude:           {ref_loc.latitude:.5f}")
                print(f"Longitude:          {ref_loc.longitude:.5f}")
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
            if q.reason:
                print(f"   Reason: {q.reason}")
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

        print("=" * 85)
        print("CONSTRAINT MATRIX")
        print("=" * 85)

        if eval_matrix.evaluations:
            headers = [r.constraint for r in eval_matrix.evaluations[0].results]
            col_width = 24
            header_str = f"{'Candidate':<28}" + "".join(f"{h:<{col_width}}" for h in headers)
            print(header_str)
            print("-" * len(header_str))

            for ev in eval_matrix.evaluations:
                row_str = f"{ev.candidate.name[:26]:<28}"
                for r in ev.results:
                    cell = format_status_provenance(r)
                    row_str += f"{cell:<{col_width}}"
                print(row_str)
        print("=" * 85)
        print("Legend: ✓ = SUPPORTED   ? = UNKNOWN   ✗ = NOT_SATISFIED")
        print("=" * 85)
        print()

        # 8. Deterministic Ranking
        ranked_all = rank_candidates(eval_matrix, reference_location=ref_loc)
        top_candidates = ranked_all[:3]

        print("=" * 65)
        print(f"RANKING (Top {len(top_candidates)} of {len(ranked_all)} Candidates)")
        print("=" * 65)

        for top_cand in top_candidates:
            print_top_candidate_card(top_cand, reference_location=ref_loc)

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
