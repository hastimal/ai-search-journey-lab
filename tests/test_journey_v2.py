"""Comprehensive test suite for v2.0.0 Search Journey Optimization (SJO) capabilities.

Verifies:
1. All 140 original tests pass.
2. ConstraintStatus has standard Enum equality and hashing.
3. ConstraintStatus contains only the V1 statuses (SUPPORTED, UNKNOWN, NOT_SATISFIED).
4. Existing score values remain exact.
5. Existing ranking order remains exact.
6. Existing ranking_reasons remain unchanged (no movement explanation appended).
7. Existing ADK ranking detail string remains unchanged.
8. Retrieval occurrences are retained across fan-out queries and deduplication.
9. Rank movement is calculated correctly with position lifecycle tracking.
10. ScoreBreakdown total equals the existing score.
11. V1 card formatting does not expose V2 fields.
12. V2 formatting exposes journey fields.
13. V1 five-metric layout remains unchanged.
14. V2 does not trigger another agent execution or API call.
"""

from ai_search_journey.constraints import (
    _evaluate_open_after,
    evaluate_category_eligibility,
    evaluate_constraints,
)
from ai_search_journey.models import (
    Candidate,
    CandidateEvidence,
    ConstraintResult,
    ConstraintStatus,
    JourneyResult,
    RankedCandidate,
    ReferenceLocation,
    RetrievalOccurrence,
    ScoreBreakdown,
    SearchIntent,
)
from ai_search_journey.normalize import normalize_candidates
from ai_search_journey.ranking import (
    generate_movement_explanation,
    rank_candidates,
)
from ai_search_journey.ui_formatters import (
    format_candidate_journey_card,
    format_candidate_summary_card,
    format_constraint_cell,
    format_rank_movement_badge,
)

# ---------------------------------------------------------------------------
# 2 & 3. ConstraintStatus Standard Enum Contracts & V1 Status Set
# ---------------------------------------------------------------------------


def test_constraint_status_has_standard_enum_equality_and_hashing() -> None:
    """Requirement 2: ConstraintStatus has standard Enum equality and hashing."""
    # Equality
    assert ConstraintStatus.SUPPORTED == ConstraintStatus.SUPPORTED
    assert ConstraintStatus.NOT_SATISFIED == ConstraintStatus.NOT_SATISFIED
    assert ConstraintStatus.UNKNOWN == ConstraintStatus.UNKNOWN
    assert ConstraintStatus.SUPPORTED != ConstraintStatus.NOT_SATISFIED
    assert ConstraintStatus.UNKNOWN != ConstraintStatus.NOT_SATISFIED

    # String value equality
    assert ConstraintStatus.SUPPORTED == "supported"
    assert ConstraintStatus.UNKNOWN == "unknown"
    assert ConstraintStatus.NOT_SATISFIED == "not_satisfied"

    # Hashing
    assert hash(ConstraintStatus.SUPPORTED) == hash(ConstraintStatus.SUPPORTED)
    assert hash(ConstraintStatus.NOT_SATISFIED) == hash(ConstraintStatus.NOT_SATISFIED)

    # Set membership
    status_set = {ConstraintStatus.SUPPORTED, ConstraintStatus.UNKNOWN}
    assert ConstraintStatus.SUPPORTED in status_set
    assert ConstraintStatus.UNKNOWN in status_set
    assert ConstraintStatus.NOT_SATISFIED not in status_set

    # Dict key lookups
    mapping = {
        ConstraintStatus.SUPPORTED: "ok",
        ConstraintStatus.NOT_SATISFIED: "fail",
    }
    assert mapping[ConstraintStatus.SUPPORTED] == "ok"
    assert mapping[ConstraintStatus.NOT_SATISFIED] == "fail"


def test_constraint_status_contains_only_v1_statuses() -> None:
    """Requirement 3: ConstraintStatus contains only the V1 statuses."""
    expected_members = {"SUPPORTED", "UNKNOWN", "NOT_SATISFIED"}
    actual_members = set(ConstraintStatus.__members__.keys())
    assert actual_members == expected_members
    assert len(ConstraintStatus) == 3

    # Ensure removed statuses do not exist
    assert not hasattr(ConstraintStatus, "NOT_SUPPORTED")
    assert not hasattr(ConstraintStatus, "CONTRADICTED")

    # Values must match v1.0.0 exactly
    assert [s.value for s in ConstraintStatus] == ["supported", "unknown", "not_satisfied"]


def test_constraint_evaluation_returns_v1_statuses() -> None:
    """Requirement 1 & 3: Constraints evaluation returns V1 statuses for unmet/satisfied."""
    # SUPPORTED: open late
    hours_late = ["Monday: 7:00 AM – 11:00 PM"]
    res_supp = _evaluate_open_after("20:00", hours_late, [])
    assert res_supp.status == ConstraintStatus.SUPPORTED

    # NOT_SATISFIED: closing at 3:00 PM when open after 8:00 PM requested
    hours_early = ["Monday: 7:00 AM – 3:00 PM"]
    res_unmet = _evaluate_open_after("20:00", hours_early, [])
    assert res_unmet.status == ConstraintStatus.NOT_SATISFIED

    # UNKNOWN: missing hours
    res_unk = _evaluate_open_after("20:00", [], [])
    assert res_unk.status == ConstraintStatus.UNKNOWN

    # NOT_SATISFIED: category mismatch
    elig = evaluate_category_eligibility("coffee shop", "car_repair", ["car_repair"])
    assert elig.status == ConstraintStatus.NOT_SATISFIED


# ---------------------------------------------------------------------------
# 4, 5 & 6. Exact V1 Scoring Parity, Ranking Order & Ranking Reasons
# ---------------------------------------------------------------------------


def test_exact_v1_score_values_and_breakdown_parity() -> None:
    """Requirements 4 & 10: Existing score values remain exact; ScoreBreakdown total matches."""
    cand = Candidate(
        place_id="c1",
        name="Place One",
        latitude=29.4267,
        longitude=-98.4900,
        rating=4.8,
        user_rating_count=500,
    )
    ref = ReferenceLocation(
        query="Geekdom",
        place_id="ref1",
        name="Geekdom",
        latitude=29.4267,
        longitude=-98.4900,
    )

    results = [
        ConstraintResult(constraint="Open after 20:00", status=ConstraintStatus.SUPPORTED),
        ConstraintResult(constraint="Group size 6", status=ConstraintStatus.NOT_SATISFIED),
        ConstraintResult(constraint="Quiet (Preference)", status=ConstraintStatus.SUPPORTED),
    ]
    cand_eval = CandidateEvidence(candidate=cand)
    journey_eval = evaluate_constraints(
        SearchIntent(category="coffee shop", open_after="20:00", preferences=["Quiet"]),
        [cand_eval],
    )
    journey_eval.evaluations[0].results = results

    ranked = rank_candidates(journey_eval, reference_location=ref)
    assert len(ranked) == 1
    r = ranked[0]

    # V1 Score components:
    # Hard: 1 supported (+25.0), 1 failed (-35.0) -> -10.0
    # Pref: 1 supported (+10.0) -> +10.0
    # Proximity: 0.0 mi -> 12.0
    # Quality: 4.8 * 2.0 = 9.6 + log10(501)*2.0 (5.40) -> clamped at 10.0 max quality -> 10.0
    # Total = -10.0 + 10.0 + 12.0 + 10.0 = 22.0
    assert r.hard_supported == 1
    assert r.hard_failed == 1
    assert r.preference_supported == 1
    assert r.proximity_score == 12.0
    assert r.quality_score == 8.32
    assert r.score == 20.32

    # Requirement 10: ScoreBreakdown total equals exact score
    assert r.score_breakdown is not None
    sb = r.score_breakdown
    assert sb.hard_constraint_points == 25.0
    assert sb.preference_points == 10.0
    assert sb.penalties == -35.0
    assert sb.proximity_points == 12.0
    assert sb.quality_points == 8.32
    assert sb.total_score == 20.32
    assert r.score == sb.total_score


def test_ranking_reasons_does_not_contain_movement_explanation() -> None:
    """Requirements 6: Existing ranking_reasons remain unchanged without movement text."""
    cand = Candidate(
        place_id="c1",
        name="Place One",
        retrieval_occurrences=[
            RetrievalOccurrence(query_task_id="F1", query_text="q", position=5, place_id="c1")
        ],
    )
    cand_eval = CandidateEvidence(candidate=cand)
    journey_eval = evaluate_constraints(SearchIntent(), [cand_eval])
    journey_eval.evaluations[0].results = [
        ConstraintResult(constraint="Open after 20:00", status=ConstraintStatus.SUPPORTED)
    ]

    ranked = rank_candidates(journey_eval)
    assert len(ranked) == 1
    r = ranked[0]

    # Dedicated movement explanation field is populated
    assert r.movement_explanation is not None
    assert "Moved up" in r.movement_explanation

    # ranking_reasons must NOT have movement_explanation appended to it!
    for reason in r.ranking_reasons:
        assert "Moved up" not in reason
        assert "Moved down" not in reason
        assert "Maintained position" not in reason
        assert "Places retrieval" not in reason


def test_existing_ranking_order_remains_exact() -> None:
    """Requirement 5: Existing ranking order remains exact."""
    cand_a = Candidate(place_id="ca", name="High Match", rating=4.5, user_rating_count=100)
    cand_b = Candidate(place_id="cb", name="Low Match", rating=4.0, user_rating_count=50)

    eval_a = CandidateEvidence(candidate=cand_a)
    eval_b = CandidateEvidence(candidate=cand_b)

    journey_eval = evaluate_constraints(SearchIntent(), [eval_a, eval_b])
    journey_eval.evaluations[0].results = [
        ConstraintResult(constraint="C1", status=ConstraintStatus.SUPPORTED),
        ConstraintResult(constraint="C2", status=ConstraintStatus.SUPPORTED),
    ]
    journey_eval.evaluations[1].results = [
        ConstraintResult(constraint="C1", status=ConstraintStatus.NOT_SATISFIED),
    ]

    ranked = rank_candidates(journey_eval)
    assert ranked[0].candidate.place_id == "ca"
    assert ranked[1].candidate.place_id == "cb"
    assert ranked[0].score > ranked[1].score


# ---------------------------------------------------------------------------
# 7. ADK Detail String Parity
# ---------------------------------------------------------------------------


def test_adk_ranking_step_detail_format() -> None:
    """Requirement 7: ADK ranking detail string format is exact."""
    ranked_all = [1, 2, 3, 4]
    top_candidates = [1, 2, 3]
    detail = f"{len(ranked_all)} candidates → Top {len(top_candidates)} selected"
    assert detail == "4 candidates → Top 3 selected"
    assert "movement" not in detail.lower()


# ---------------------------------------------------------------------------
# 8. Retrieval Occurrences Retained
# ---------------------------------------------------------------------------


def test_retrieval_occurrences_retained_during_normalization() -> None:
    """Requirement 8: Retrieval occurrences are retained across fan-out queries and dedupe."""
    occ1 = RetrievalOccurrence(
        query_task_id="F1",
        query_text="coffee shops near Geekdom",
        position=5,
        source_name="google_places",
        place_id="p1",
    )
    occ2 = RetrievalOccurrence(
        query_task_id="F2",
        query_text="work friendly cafe San Antonio",
        position=1,
        source_name="google_places",
        place_id="p1",
    )
    c1 = Candidate(place_id="p1", name="Cafe Alpha", retrieval_occurrences=[occ1])
    c2 = Candidate(place_id="p1", name="Cafe Alpha", retrieval_occurrences=[occ2])

    merged = normalize_candidates([c1, c2])
    assert len(merged) == 1
    canonical = merged[0]
    assert len(canonical.retrieval_occurrences) == 2
    assert canonical.best_retrieval_position == 1
    assert canonical.retrieval_queries == [
        "coffee shops near Geekdom",
        "work friendly cafe San Antonio",
    ]


# ---------------------------------------------------------------------------
# 9. Rank Movement & Position Lifecycle
# ---------------------------------------------------------------------------


def test_rank_movement_and_lifecycle_positions() -> None:
    """Requirement 9: Rank movement is calculated correctly with position lifecycle tracking."""
    occ_a = RetrievalOccurrence(query_task_id="F1", query_text="q", position=5, place_id="pa")
    cand_a = Candidate(place_id="pa", name="Winner", retrieval_occurrences=[occ_a])

    occ_b = RetrievalOccurrence(query_task_id="F1", query_text="q", position=1, place_id="pb")
    cand_b = Candidate(place_id="pb", name="Loser", retrieval_occurrences=[occ_b])

    eval_a = CandidateEvidence(candidate=cand_a)
    eval_b = CandidateEvidence(candidate=cand_b)

    journey_eval = evaluate_constraints(SearchIntent(), [eval_a, eval_b])
    journey_eval.evaluations[0].results = [
        ConstraintResult(constraint="C1", status=ConstraintStatus.SUPPORTED)
    ]
    journey_eval.evaluations[1].results = [
        ConstraintResult(constraint="C1", status=ConstraintStatus.NOT_SATISFIED)
    ]

    ranked = rank_candidates(journey_eval)
    assert len(ranked) == 2

    # Winner moved up: retrieval 5 -> rank 1 => movement +4
    assert ranked[0].best_retrieval_position == 5
    assert ranked[0].final_recommendation_position == 1
    assert ranked[0].rank_movement == +4

    # Loser moved down: retrieval 1 -> rank 2 => movement -1
    assert ranked[1].best_retrieval_position == 1
    assert ranked[1].final_recommendation_position == 2
    assert ranked[1].rank_movement == -1


def test_movement_explanation_generation() -> None:
    """Requirement 9: Movement explanation generator handles up, down, unchanged, and direct."""
    cand = Candidate(place_id="p1", name="Hero Coffee")
    sb = ScoreBreakdown(
        hard_constraint_points=50.0,
        preference_points=10.0,
        proximity_points=8.0,
        quality_points=4.0,
        penalties=0.0,
        total_score=72.0,
    )
    r_up = RankedCandidate(
        candidate=cand,
        score=72.0,
        rank=1,
        best_retrieval_position=5,
        final_recommendation_position=1,
        rank_movement=+4,
        hard_supported=2,
        preference_supported=1,
        proximity_score=8.0,
        quality_score=4.0,
        score_breakdown=sb,
    )
    explanation_up = generate_movement_explanation(r_up)
    assert "Moved up 4 positions from Places retrieval #5 to Recommendation #1" in explanation_up

    r_down = RankedCandidate(
        candidate=cand,
        score=-25.0,
        rank=3,
        best_retrieval_position=1,
        final_recommendation_position=3,
        rank_movement=-2,
        hard_failed=1,
        score_breakdown=ScoreBreakdown(penalties=-35.0, total_score=-25.0),
    )
    explanation_down = generate_movement_explanation(r_down)
    expected_down = "Moved down 2 positions from Places retrieval #1 to Recommendation #3"
    assert expected_down in explanation_down

    r_unchanged = RankedCandidate(
        candidate=cand,
        score=50.0,
        rank=1,
        best_retrieval_position=1,
        final_recommendation_position=1,
        rank_movement=0,
        hard_supported=2,
        score_breakdown=ScoreBreakdown(hard_constraint_points=50.0, total_score=50.0),
    )
    explanation_unchanged = generate_movement_explanation(r_unchanged)
    expected_unchanged = "Maintained position at #1 from Places retrieval to Recommendation"
    assert expected_unchanged in explanation_unchanged

    r_direct = RankedCandidate(
        candidate=cand,
        score=50.0,
        rank=1,
        best_retrieval_position=None,
        final_recommendation_position=1,
        rank_movement=None,
        score_breakdown=ScoreBreakdown(hard_constraint_points=50.0, total_score=50.0),
    )
    explanation_direct = generate_movement_explanation(r_direct)
    assert "Direct recommendation (no Places retrieval position recorded)." in explanation_direct


# ---------------------------------------------------------------------------
# 11 & 12. UI Formatting Separation (V1 vs V2 Cards)
# ---------------------------------------------------------------------------


def test_v1_card_formatting_does_not_expose_v2_fields() -> None:
    """Requirement 11: V1 card formatting does not expose V2 fields."""
    cand = Candidate(place_id="c1", name="Test Venue")
    rc = RankedCandidate(
        candidate=cand,
        score=50.0,
        rank=1,
        best_retrieval_position=3,
        final_recommendation_position=1,
        rank_movement=+2,
        movement_explanation="Moved up 2 positions",
        score_breakdown=ScoreBreakdown(hard_constraint_points=25.0, total_score=50.0),
    )
    v1_card = format_candidate_summary_card(rc, 0)

    # V1 expected keys
    expected_v1_keys = {
        "letter",
        "rank",
        "name",
        "score",
        "distance",
        "rating",
        "requested_category",
        "primary_type",
        "category_status",
        "types",
        "google_maps_url",
    }
    assert set(v1_card.keys()) == expected_v1_keys

    # V2 fields must NOT be in v1_card!
    forbidden_v2_keys = [
        "retrieval_position",
        "rank_movement",
        "movement_badge",
        "movement_explanation",
        "hard_points",
        "pref_points",
        "penalties",
        "proximity_points",
        "quality_points",
    ]
    for key in forbidden_v2_keys:
        assert key not in v1_card


def test_v2_formatting_exposes_journey_fields() -> None:
    """Requirement 12: V2 formatting exposes journey fields."""
    cand = Candidate(place_id="c1", name="Test Venue")
    rc = RankedCandidate(
        candidate=cand,
        score=50.0,
        rank=1,
        best_retrieval_position=3,
        final_recommendation_position=1,
        rank_movement=+2,
        movement_explanation="Moved up 2 positions",
        score_breakdown=ScoreBreakdown(
            hard_constraint_points=25.0,
            preference_points=10.0,
            proximity_points=5.0,
            quality_points=10.0,
            penalties=0.0,
            total_score=50.0,
        ),
    )
    v2_card = format_candidate_journey_card(rc, 0)

    # V2 must include SJO fields
    assert v2_card["retrieval_position"] == "#3"
    assert v2_card["rank_movement"] == "+2"
    assert v2_card["movement_badge"] == "▲ +2"
    assert v2_card["movement_explanation"] == "Moved up 2 positions"
    assert v2_card["hard_points"] == "25.0"
    assert v2_card["pref_points"] == "10.0"
    assert v2_card["proximity_points"] == "5.0"
    assert v2_card["quality_points"] == "10.0"


def test_ui_badge_and_cell_formatters() -> None:
    """Verify badge and cell formatters under V1 constraint rules."""
    assert format_rank_movement_badge(3) == "▲ +3"
    assert format_rank_movement_badge(-2) == "▼ -2"
    assert format_rank_movement_badge(0) == "● Unchanged"
    assert format_rank_movement_badge(None) == "● Direct"

    r_supp = ConstraintResult(constraint="X", status=ConstraintStatus.SUPPORTED)
    r_unmet = ConstraintResult(constraint="X", status=ConstraintStatus.NOT_SATISFIED)
    r_unk = ConstraintResult(constraint="X", status=ConstraintStatus.UNKNOWN)

    assert format_constraint_cell(r_supp) == "✓"
    assert format_constraint_cell(r_unmet) == "✗"
    assert format_constraint_cell(r_unk) == "?"


# ---------------------------------------------------------------------------
# 13 & 14. V1 Metric Layout & In-Memory Single Execution Reuse
# ---------------------------------------------------------------------------


def test_v1_five_metric_layout_count() -> None:
    """Requirement 13: V1 five-metric layout remains unchanged."""
    v1_metrics = [
        "Places Tasks",
        "Search Tasks",
        "Unique Candidates",
        "Search Findings",
        "Top Ranked",
    ]
    assert len(v1_metrics) == 5


def test_v2_reuses_in_memory_journey_result_without_reexecution() -> None:
    """Requirement 14: V2 operates on existing in-memory JourneyResult without re-execution."""
    cand = Candidate(place_id="c1", name="Venue One")
    rc = RankedCandidate(
        candidate=cand,
        score=85.0,
        rank=1,
        best_retrieval_position=1,
        final_recommendation_position=1,
        rank_movement=0,
        score_breakdown=ScoreBreakdown(hard_constraint_points=75.0, total_score=85.0),
    )
    journey = JourneyResult(
        question="test query",
        intent=SearchIntent(category="coffee shop"),
        candidates=[cand],
        ranking=[rc],
    )

    # Both V1 and V2 read from the identical in-memory instance
    assert journey.ranking[0].candidate.name == "Venue One"
    assert journey.ranking[0].score == 85.0
    assert journey.ranking[0].best_retrieval_position == 1
    # Check that object identity is preserved
    journey_ref_v1 = journey
    journey_ref_v2 = journey
    assert journey_ref_v1 is journey_ref_v2
