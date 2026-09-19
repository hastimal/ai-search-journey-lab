"""Unit tests for deterministic constraint evaluation module."""

from ai_search_journey.constraints import (
    _evaluate_group_size,
    _evaluate_open_after,
    _evaluate_qualitative_constraint,
    evaluate_constraints,
)
from ai_search_journey.models import (
    Candidate,
    CandidateEvidence,
    ConstraintResult,
    ConstraintStatus,
    ConstraintSupport,
    Evidence,
    EvidenceSource,
    SearchIntent,
)


def test_opening_hours_supporting_open_after_returns_supported() -> None:
    """Opening hours extending past target time evaluate to SUPPORTED with PLACES provenance."""
    hours = [
        "Monday: 8:00 AM – 10:00 PM",
        "Tuesday: 8:00 AM – 10:00 PM",
        "Friday: 8:00 AM – 12:00 AM",
    ]
    ev = [
        Evidence(
            candidate_id="c1",
            attribute="opening_hours",
            claim=f"Opening Hours: {'; '.join(hours)}",
            source=EvidenceSource.GOOGLE_PLACES,
            fanout_task_id="F2",
        )
    ]

    res = _evaluate_open_after("20:00", hours, ev)
    assert res.status == ConstraintStatus.SUPPORTED
    assert res.source_type == "google_places"
    assert res.fanout_task_id == "F2"


def test_opening_hours_clearly_closing_before_open_after_returns_not_satisfied() -> None:
    """Opening hours closing strictly before target time evaluate to NOT_SATISFIED."""
    hours = [
        "Monday: 7:00 AM – 3:00 PM",
        "Tuesday: 7:00 AM – 3:00 PM",
    ]
    ev = [
        Evidence(
            candidate_id="c1",
            attribute="opening_hours",
            claim="Opening Hours: Monday: 7:00 AM – 3:00 PM",
            source=EvidenceSource.GOOGLE_PLACES,
            fanout_task_id="F1",
        )
    ]

    res = _evaluate_open_after("20:00", hours, ev)
    assert res.status == ConstraintStatus.NOT_SATISFIED
    assert res.source_type == "google_places"
    assert res.fanout_task_id == "F1"


def test_missing_opening_hours_returns_unknown() -> None:
    """Missing or unparseable hours evaluate to UNKNOWN without converting to NOT_SATISFIED."""
    res = _evaluate_open_after("20:00", [], [])
    assert res.status == ConstraintStatus.UNKNOWN


def test_search_evidence_supporting_quiet_returns_supported() -> None:
    """Search evidence explicitly confirming quiet/low-noise atmosphere evaluates to SUPPORTED."""
    ev = [
        Evidence(
            candidate_id="c1",
            attribute="search_grounding_finding",
            claim="Quiet, focus-oriented atmosphere with low noise levels.",
            source=EvidenceSource.GOOGLE_SEARCH,
            source_title="SA Guide",
            source_url="https://example.com/guide",
            planner_query="quiet coffee spots",
            fanout_task_id="F3",
        )
    ]

    res = _evaluate_qualitative_constraint("quiet", ev, is_preference=True)
    assert res.status == ConstraintStatus.SUPPORTED
    assert res.source_type == "google_search"
    assert res.fanout_task_id == "F3"
    assert res.source_title == "SA Guide"
    assert res.source_url == "https://example.com/guide"
    assert res.planner_query == "quiet coffee spots"


def test_no_quiet_evidence_returns_unknown() -> None:
    """Lack of quietness evidence evaluates to UNKNOWN."""
    res = _evaluate_qualitative_constraint("quiet", [], is_preference=True)
    assert res.status == ConstraintStatus.UNKNOWN


def test_group_size_evidence_supporting_capacity_returns_supported() -> None:
    """Evidence explicitly supporting groups of 6 or 8 evaluates to SUPPORTED."""
    ev = [
        Evidence(
            candidate_id="c1",
            attribute="search_grounding_finding",
            claim="Features large communal tables that accommodate a group of 6 people.",
            source=EvidenceSource.GOOGLE_SEARCH,
            fanout_task_id="F4",
            planner_query="coffee shops for 6 people",
        )
    ]

    res = _evaluate_group_size(6, ev)
    assert res.status == ConstraintStatus.SUPPORTED
    assert res.source_type == "google_search"
    assert res.fanout_task_id == "F4"


def test_explicit_contradictory_group_evidence_returns_not_satisfied() -> None:
    """Evidence explicitly noting inability to seat groups evaluates to NOT_SATISFIED."""
    ev = [
        Evidence(
            candidate_id="c1",
            attribute="search_grounding_finding",
            claim="Small footprint designed for grab-and-go only, unsuitable for group meetings.",
            source=EvidenceSource.GOOGLE_SEARCH,
            fanout_task_id="F4",
        )
    ]

    res = _evaluate_group_size(8, ev)
    assert res.status == ConstraintStatus.NOT_SATISFIED


def test_vegetarian_evidence_returns_supported() -> None:
    """Evidence listing vegetarian menu items evaluates to SUPPORTED."""
    ev = [
        Evidence(
            candidate_id="c1",
            attribute="search_grounding_finding",
            claim="Extensive vegetarian menu including vegetable samosas and paneer.",
            source=EvidenceSource.GOOGLE_SEARCH,
            fanout_task_id="F4",
            source_title="sacurrent.com",
            source_url="https://sacurrent.com/food",
        )
    ]

    res = _evaluate_qualitative_constraint("vegetarian options", ev, is_preference=False)
    assert res.status == ConstraintStatus.SUPPORTED
    assert res.source_title == "sacurrent.com"


def test_missing_vegetarian_evidence_returns_unknown() -> None:
    """Missing vegetarian evidence returns UNKNOWN (not NOT_SATISFIED)."""
    res = _evaluate_qualitative_constraint("vegetarian options", [], is_preference=False)
    assert res.status == ConstraintStatus.UNKNOWN


def test_preferences_remain_distinguishable_from_hard_constraints() -> None:
    """Preferences get marked with '(Preference)' in constraint name."""
    intent = SearchIntent(
        open_after="20:00",
        group_size=6,
        hard_constraints=["open after 20:00"],
        preferences=["quiet"],
    )

    c = Candidate(
        place_id="c1",
        name="Test Place",
        opening_hours=["Monday: 8:00 AM – 11:00 PM"],
    )
    ce = CandidateEvidence(
        candidate=c,
        structured_evidence=[
            Evidence(
                candidate_id="c1",
                attribute="opening_hours",
                claim="Opening Hours: Monday: 8:00 AM – 11:00 PM",
                source=EvidenceSource.GOOGLE_PLACES,
                fanout_task_id="F1",
            )
        ],
        search_evidence=[],
    )

    matrix = evaluate_constraints(intent, [ce])
    assert len(matrix.evaluations) == 1
    eval_item = matrix.evaluations[0]
    names = [r.constraint for r in eval_item.results]

    assert "Open after 20:00" in names
    assert "Group size 6" in names
    assert "quiet (Preference)" in names


def test_opening_hours_boundary_equality_returns_not_satisfied() -> None:
    """Closing exactly at or before target time evaluates strictly to NOT_SATISFIED."""
    # Boundary case 1: Closes exactly at 8:00 PM (20:00)
    hours_exact = [
        "Monday: 7:00 AM – 8:00 PM",
        "Tuesday: 7:00 AM – 8:00 PM",
    ]
    ev_exact = [
        Evidence(
            candidate_id="c1",
            attribute="opening_hours",
            claim="Opening Hours: Monday: 7:00 AM – 8:00 PM",
            source=EvidenceSource.GOOGLE_PLACES,
            fanout_task_id="F1",
        )
    ]
    res_exact = _evaluate_open_after("20:00", hours_exact, ev_exact)
    assert res_exact.status == ConstraintStatus.NOT_SATISFIED

    # Boundary case 2: Closes at 7:30 PM (19:30)
    hours_before = ["Monday: 7:00 AM – 7:30 PM"]
    res_before = _evaluate_open_after("20:00", hours_before, ev_exact)
    assert res_before.status == ConstraintStatus.NOT_SATISFIED

    # Boundary case 3: Closes at 8:30 PM (20:30) -> strictly after
    hours_after = ["Monday: 7:00 AM – 8:30 PM"]
    res_after = _evaluate_open_after("20:00", hours_after, ev_exact)
    assert res_after.status == ConstraintStatus.SUPPORTED


def test_multi_fanout_task_id_provenance_preserved() -> None:
    """Multi-query retrieval task IDs (e.g. F1, F2) are preserved in evaluation result."""
    hours = ["Monday: 8:00 AM – 11:00 PM"]
    ev = [
        Evidence(
            candidate_id="c1",
            attribute="opening_hours",
            claim="Opening Hours: Monday: 8:00 AM – 11:00 PM",
            source=EvidenceSource.GOOGLE_PLACES,
            fanout_task_id="F1, F2",
            fanout_task_ids=["F1", "F2"],
        )
    ]

    res = _evaluate_open_after("20:00", hours, ev)
    assert res.status == ConstraintStatus.SUPPORTED
    assert res.fanout_task_ids == ["F1", "F2"]
    assert "F1" in res.fanout_task_id and "F2" in res.fanout_task_id


def test_places_and_search_support_together() -> None:
    """When both Places and Search support the same constraint, both are preserved."""
    hours = ["Monday: 8:00 AM – 11:00 PM"]
    structured_ev = [
        Evidence(
            candidate_id="c1",
            attribute="opening_hours",
            claim="Opening Hours: Monday: 8:00 AM – 11:00 PM",
            source=EvidenceSource.GOOGLE_PLACES,
            fanout_task_ids=["F2"],
        )
    ]
    search_ev = [
        Evidence(
            candidate_id="c1",
            attribute="search_grounding_finding",
            claim="Open late past 8 PM with plenty of study space.",
            source=EvidenceSource.GOOGLE_SEARCH,
            fanout_task_ids=["F3"],
            source_title="Guide",
            source_url="https://guide.com",
            planner_query="late night coffee",
        )
    ]

    res = _evaluate_open_after("20:00", hours, structured_ev, search_ev)
    assert res.status == ConstraintStatus.SUPPORTED
    assert len(res.supporting_evidence) == 2
    sources = {s.source_type for s in res.supporting_evidence}
    assert sources == {"google_places", "google_search"}
    assert res.fanout_task_ids == ["F2", "F3"]


def test_unknown_has_empty_support_list() -> None:
    """Constraint evaluation returning UNKNOWN has empty supporting_evidence."""
    res = _evaluate_qualitative_constraint("vegan options", [])
    assert res.status == ConstraintStatus.UNKNOWN
    assert res.supporting_evidence == []


def test_not_satisfied_can_retain_contradictory_evidence() -> None:
    """Constraint evaluation returning NOT_SATISFIED retains contradictory evidence."""
    ev = [
        Evidence(
            candidate_id="c1",
            attribute="search_grounding_finding",
            claim="Small footprint designed for grab-and-go only, cannot accommodate groups.",
            source=EvidenceSource.GOOGLE_SEARCH,
            fanout_task_ids=["F4"],
        )
    ]
    res = _evaluate_group_size(6, ev)
    assert res.status == ConstraintStatus.NOT_SATISFIED
    assert len(res.supporting_evidence) == 1
    assert res.supporting_evidence[0].source_type == "google_search"
    assert res.supporting_evidence[0].fanout_task_ids == ["F4"]


def test_no_duplicate_identical_support_items() -> None:
    """Duplicate identical support items are deduplicated."""
    ev = [
        Evidence(
            candidate_id="c1",
            attribute="search_grounding_finding",
            claim="Quiet workspace.",
            source=EvidenceSource.GOOGLE_SEARCH,
            source_url="https://example.com",
            fanout_task_ids=["F3"],
        ),
        Evidence(
            candidate_id="c1",
            attribute="search_grounding_finding",
            claim="Quiet workspace.",
            source=EvidenceSource.GOOGLE_SEARCH,
            source_url="https://example.com",
            fanout_task_ids=["F3"],
        ),
    ]
    res = _evaluate_qualitative_constraint("quiet", ev)
    assert res.status == ConstraintStatus.SUPPORTED
    assert len(res.supporting_evidence) == 1


def test_matrix_formatting_for_places_and_search() -> None:
    """Verify matrix cell formatting for PLACES + SEARCH multi-source support."""
    from scripts.demo_constraints import format_status_provenance

    r = ConstraintResult(
        constraint="Open after 20:00",
        status=ConstraintStatus.SUPPORTED,
        supporting_evidence=[
            ConstraintSupport(source_type="google_places", fanout_task_ids=["F2"]),
            ConstraintSupport(source_type="google_search", fanout_task_ids=["F3"]),
        ],
    )
    formatted = format_status_provenance(r)
    assert formatted == "✓ PLACES + SEARCH [F2,F3]"


def test_evaluator_is_pure_and_does_not_call_apis() -> None:
    """Verify constraint evaluation executes synchronously and purely in Python."""
    intent = SearchIntent(open_after="21:00", group_size=8)
    c = Candidate(place_id="p1", name="Place")
    ce = CandidateEvidence(candidate=c)

    matrix = evaluate_constraints(intent, [ce])
    assert len(matrix.evaluations) == 1
    assert matrix.evaluations[0].results[0].status == ConstraintStatus.UNKNOWN
    assert matrix.evaluations[0].results[0].supporting_evidence == []
    assert matrix.evaluations[0].results[1].status == ConstraintStatus.UNKNOWN
    assert matrix.evaluations[0].results[1].supporting_evidence == []
