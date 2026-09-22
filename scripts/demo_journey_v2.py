"""Demonstration script for v2.0.0 Search Journey Optimization (SJO).

Topic: "Search Journey Optimization: From Google Results to AI Recommendations"

Demonstrates:
- Fan-out queries retrieving Places candidates with recorded retrieval positions.
- Deduplication preserving multi-query occurrences.
- Evidence & citation coverage calculations.
- Deterministic constraint evaluation (SUPPORTED, NOT_SATISFIED, UNKNOWN).
- Transparent score breakdown.
- Position lifecycle: Places retrieval position -> Evidence-enriched -> Recommendation.
- Deterministic rank movement explanations.
"""

from ai_search_journey.constraints import evaluate_constraints
from ai_search_journey.evidence import aggregate_evidence
from ai_search_journey.models import (
    Candidate,
    FanoutQuery,
    ReferenceLocation,
    RetrievalOccurrence,
    SearchGroundingResult,
    SearchIntent,
    SearchSource,
    ToolName,
)
from ai_search_journey.normalize import normalize_candidates
from ai_search_journey.ranking import rank_candidates
from ai_search_journey.ui_formatters import (
    format_constraint_cell,
    format_rank_movement_badge,
)


def run_sjo_demo() -> None:
    """Run simulated end-to-end SJO pipeline trace."""
    print("=" * 80)
    print("AI SEARCH JOURNEY LAB — v2.0.0 SJO DEMO")
    print("Topic: Search Journey Optimization: From Google Results to AI Recommendations")
    print("=" * 80)

    # 1. User Intent
    question = (
        "Find a coffee shop near Geekdom San Antonio for 6 people "
        "to work together, preferably quiet, and open after 8 PM."
    )
    print(f"\n[1] USER QUESTION:\n    \"{question}\"\n")

    intent = SearchIntent(
        category="coffee shop",
        reference_location="Geekdom San Antonio",
        group_size=6,
        open_after="20:00",
        hard_constraints=["open after 20:00", "group size 6"],
        preferences=["quiet", "work friendly"],
    )
    ref_loc = ReferenceLocation(
        query="Geekdom San Antonio",
        place_id="ref_geekdom",
        name="Geekdom San Antonio",
        latitude=29.4267,
        longitude=-98.4900,
    )

    # 2. Simulated Fan-Out Retrieval with Places Retrieval Positions
    print("[2] PLACES RETRIEVAL OCCURRENCES (WITH POSITIONS):")
    task_f1 = FanoutQuery(
        task_id="F1",
        goal="Discover nearby coffee shops",
        query="coffee shops near Geekdom San Antonio",
        tool=ToolName.GOOGLE_PLACES,
    )
    task_f2 = FanoutQuery(
        task_id="F2",
        goal="Find evening work cafes",
        query="late night work coffee study San Antonio",
        tool=ToolName.GOOGLE_PLACES,
    )

    # Candidate 1: Halcyon Southtown (At retrieval position 5 in F1, position 1 in F2)
    occ_halcyon_1 = RetrievalOccurrence(
        query_task_id=task_f1.task_id,
        query_text=task_f1.query,
        position=5,
        source_name="google_places",
        place_id="place_halcyon",
    )
    occ_halcyon_2 = RetrievalOccurrence(
        query_task_id=task_f2.task_id,
        query_text=task_f2.query,
        position=1,
        source_name="google_places",
        place_id="place_halcyon",
    )
    cand_halcyon = Candidate(
        place_id="place_halcyon",
        name="Halcyon Southtown",
        formatted_address="1414 S Alamo St, San Antonio, TX",
        latitude=29.4102,
        longitude=-98.4954,
        rating=4.5,
        user_rating_count=1650,
        primary_type="coffee_shop",
        place_types=["coffee_shop", "cafe", "bar"],
        opening_hours=["Monday: 8:00 AM – 12:00 AM", "Tuesday: 8:00 AM – 12:00 AM"],
        retrieval_task_ids=["F1", "F2"],
        retrieval_occurrences=[occ_halcyon_1, occ_halcyon_2],
    )

    # Candidate 2: Early Bird Cafe (Position 1 in F1, but closes at 3 PM)
    occ_early = RetrievalOccurrence(
        query_task_id=task_f1.task_id,
        query_text=task_f1.query,
        position=1,
        source_name="google_places",
        place_id="place_early",
    )
    cand_early = Candidate(
        place_id="place_early",
        name="Early Bird Coffee Bar",
        formatted_address="110 Broadway, San Antonio, TX",
        latitude=29.4270,
        longitude=-98.4890,
        rating=4.8,
        user_rating_count=320,
        primary_type="coffee_shop",
        place_types=["coffee_shop"],
        opening_hours=["Monday: 7:00 AM – 3:00 PM"],
        retrieval_task_ids=["F1"],
        retrieval_occurrences=[occ_early],
    )

    # Candidate 3: Estate Coffee Co (Position 3 in F1)
    occ_estate = RetrievalOccurrence(
        query_task_id=task_f1.task_id,
        query_text=task_f1.query,
        position=3,
        source_name="google_places",
        place_id="place_estate",
    )
    cand_estate = Candidate(
        place_id="place_estate",
        name="Estate Coffee Company",
        formatted_address="1321 E Houston St, San Antonio, TX",
        latitude=29.4241,
        longitude=-98.4735,
        rating=4.7,
        user_rating_count=480,
        primary_type="coffee_shop",
        place_types=["coffee_shop"],
        opening_hours=["Monday: 7:00 AM – 7:00 PM"],
        retrieval_task_ids=["F1"],
        retrieval_occurrences=[occ_estate],
    )

    raw_candidates = [cand_halcyon, cand_early, cand_estate]
    for c in raw_candidates:
        for occ in c.retrieval_occurrences:
            print(f"    - [{occ.query_task_id}] Places Retrieval Pos #{occ.position}: "
                  f"{c.name} (query: \"{occ.query_text}\")")

    # 3. Deduplication and Best Retrieval Position
    print("\n[3] NORMALIZATION & OCCURRENCE DEDUPLICATION:")
    normalized = normalize_candidates(raw_candidates)
    for c in normalized:
        print(f"    - {c.name:<25} | Best Retrieval Pos: #{c.best_retrieval_position} "
              f"| Occurrences: {len(c.retrieval_occurrences)} | Queries: {c.retrieval_queries}")

    # 4. Evidence Aggregation & Coverage
    print("\n[4] EVIDENCE AGGREGATION & COVERAGE METRICS:")
    search_res = SearchGroundingResult(
        task_id="F3",
        planner_query="Halcyon Southtown group seating wifi work",
        grounded_text="Halcyon Southtown has large tables suitable for groups of 6 and fast wifi.",
        sources=[SearchSource(title="San Antonio Express News", url="https://mysa.com/halcyon")],
    )
    aggregation = aggregate_evidence(normalized, [search_res])
    for ce in aggregation.candidates:
        print(f"    - {ce.candidate.name:<25} | Evidence Cov: {ce.evidence_coverage*100:.0f}% "
              f"| Citation Cov: {ce.citation_coverage*100:.0f}%")

    # 5. Constraint Evaluation Matrix
    print("\n[5] DETERMINISTIC CONSTRAINT EVALUATION MATRIX:")
    eval_matrix = evaluate_constraints(intent, aggregation.candidates)
    headers = [r.constraint for r in eval_matrix.evaluations[0].results]
    print(f"    {'Candidate':<26}" + "".join(f"{h:<24}" for h in headers))
    print("    " + "-" * 100)
    for ev in eval_matrix.evaluations:
        row_str = f"    {ev.candidate.name[:24]:<26}"
        for r in ev.results:
            cell = format_constraint_cell(r)
            row_str += f"{cell:<24}"
        print(row_str)

    # 6. Ranking & Position Lifecycle Tracking
    print("\n[6] RANKING, POSITION LIFECYCLE & RANK MOVEMENT:")
    ranked = rank_candidates(eval_matrix, reference_location=ref_loc)
    hdr = (
        f"    {'Final Rank':<12}{'Candidate':<24}"
        f"{'Retrieval Pos':<16}{'Movement':<14}{'Score':<10}"
    )
    print(hdr)
    print("    " + "-" * 78)
    for r in ranked:
        ret_str = f"#{r.best_retrieval_position}" if r.best_retrieval_position else "N/A"
        badge = format_rank_movement_badge(r.rank_movement)
        print(f"    #{r.rank:<11}{r.candidate.name:<26}{ret_str:<16}{badge:<14}{r.score:<10.2f}")

    # 7. Transparent Score Breakdown
    print("\n[7] TRANSPARENT SCORE BREAKDOWN:")
    for r in ranked:
        sb = r.score_breakdown
        if sb:
            print(f"    * {r.candidate.name} (Total: {sb.total_score:.2f} pts):")
            print(f"        Hard Constraints: +{sb.hard_constraint_points:.1f} pts")
            print(f"        Preferences:      +{sb.preference_points:.1f} pts")
            print(f"        Proximity:        +{sb.proximity_points:.1f} pts")
            print(f"        Quality:          +{sb.quality_points:.1f} pts")
            print(f"        Penalties:        {sb.penalties:.1f} pts")

    # 8. SJO Movement Explanations
    print("\n[8] SJO RANK MOVEMENT EXPLANATIONS:")
    for r in ranked:
        print(f"    * {r.candidate.name}:")
        print(f"        \"{r.movement_explanation}\"")

    print("\n" + "=" * 80)
    print("DEMO COMPLETE — SJO TRACE READY FOR PRODUCTION")
    print("=" * 80)


if __name__ == "__main__":
    run_sjo_demo()
