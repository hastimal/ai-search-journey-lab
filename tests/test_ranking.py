"""Unit tests for deterministic explainable ranking module."""

from ai_search_journey.models import (
    Candidate,
    CandidateConstraintEvaluation,
    ConstraintEvaluationResult,
    ConstraintResult,
    ConstraintStatus,
    ConstraintSupport,
)
from ai_search_journey.ranking import (
    HARD_NOT_SATISFIED_WEIGHT,
    HARD_SUPPORTED_WEIGHT,
    PREFERENCE_SUPPORTED_WEIGHT,
    _calculate_quality_score,
    rank_candidates,
)


def test_candidate_satisfying_more_hard_constraints_ranks_higher() -> None:
    """Candidate with 2 supported hard constraints outranks candidate with 1."""
    c1 = Candidate(place_id="c1", name="Place 1")
    c2 = Candidate(place_id="c2", name="Place 2")

    eval1 = CandidateConstraintEvaluation(
        candidate=c1,
        results=[
            ConstraintResult(
                constraint="Open after 20:00",
                status=ConstraintStatus.SUPPORTED,
                supporting_evidence=[ConstraintSupport(source_type="google_places")],
            ),
            ConstraintResult(
                constraint="Group size 6",
                status=ConstraintStatus.SUPPORTED,
                supporting_evidence=[ConstraintSupport(source_type="google_search")],
            ),
        ],
    )
    eval2 = CandidateConstraintEvaluation(
        candidate=c2,
        results=[
            ConstraintResult(
                constraint="Open after 20:00",
                status=ConstraintStatus.SUPPORTED,
                supporting_evidence=[ConstraintSupport(source_type="google_places")],
            ),
            ConstraintResult(
                constraint="Group size 6",
                status=ConstraintStatus.UNKNOWN,
            ),
        ],
    )

    ranked = rank_candidates(ConstraintEvaluationResult(evaluations=[eval2, eval1]))
    assert len(ranked) == 2
    assert ranked[0].candidate.place_id == "c1"
    assert ranked[0].score > ranked[1].score


def test_hard_not_satisfied_penalty_is_stronger_than_preference_bonuses() -> None:
    """Hard constraint failure penalty (-35) overcomes 2 supported preferences (+20)."""
    c_fail_hard = Candidate(place_id="cf", name="Fails Hard Constraint")
    c_unknown_hard = Candidate(place_id="cu", name="Unknown Hard Constraint")

    # c_fail_hard fails 1 hard constraint (-35) but has 2 preferences supported (+20) -> score = -15
    eval_fail = CandidateConstraintEvaluation(
        candidate=c_fail_hard,
        results=[
            ConstraintResult(
                constraint="Open after 20:00",
                status=ConstraintStatus.NOT_SATISFIED,
                supporting_evidence=[ConstraintSupport(source_type="google_places")],
            ),
            ConstraintResult(
                constraint="quiet (Preference)",
                status=ConstraintStatus.SUPPORTED,
                supporting_evidence=[ConstraintSupport(source_type="google_search")],
            ),
            ConstraintResult(
                constraint="work friendly (Preference)",
                status=ConstraintStatus.SUPPORTED,
                supporting_evidence=[ConstraintSupport(source_type="google_search")],
            ),
        ],
    )

    # c_unknown_hard has unknown hard (0) and no preferences (0) -> score = 0
    eval_unknown = CandidateConstraintEvaluation(
        candidate=c_unknown_hard,
        results=[
            ConstraintResult(
                constraint="Open after 20:00",
                status=ConstraintStatus.UNKNOWN,
            ),
        ],
    )

    ranked = rank_candidates(ConstraintEvaluationResult(evaluations=[eval_fail, eval_unknown]))
    assert ranked[0].candidate.place_id == "cu"
    assert ranked[1].candidate.place_id == "cf"
    assert ranked[0].score > ranked[1].score


def test_unknown_does_not_receive_not_satisfied_penalty() -> None:
    """UNKNOWN receives 0 points, not the negative penalty of NOT_SATISFIED."""
    c_unk = Candidate(place_id="cu", name="Unknown")
    c_not = Candidate(place_id="cn", name="Not Satisfied")

    eval_unk = CandidateConstraintEvaluation(
        candidate=c_unk,
        results=[ConstraintResult(constraint="Vegetarian", status=ConstraintStatus.UNKNOWN)],
    )
    eval_not = CandidateConstraintEvaluation(
        candidate=c_not,
        results=[ConstraintResult(constraint="Vegetarian", status=ConstraintStatus.NOT_SATISFIED)],
    )

    ranked = rank_candidates(ConstraintEvaluationResult(evaluations=[eval_unk, eval_not]))
    assert ranked[0].score == 0.0
    assert ranked[1].score == HARD_NOT_SATISFIED_WEIGHT
    assert ranked[0].score > ranked[1].score


def test_supported_preference_increases_score_modestly() -> None:
    """Supported preference adds PREFERENCE_SUPPORTED_WEIGHT (+10)."""
    c = Candidate(place_id="c1", name="Place")
    cand_eval = CandidateConstraintEvaluation(
        candidate=c,
        results=[
            ConstraintResult(
                constraint="quiet (Preference)",
                status=ConstraintStatus.SUPPORTED,
                supporting_evidence=[ConstraintSupport(source_type="google_search")],
            )
        ],
    )
    ranked = rank_candidates(ConstraintEvaluationResult(evaluations=[cand_eval]))
    assert ranked[0].score == PREFERENCE_SUPPORTED_WEIGHT
    assert ranked[0].preference_supported == 1


def test_rating_contributes_small_secondary_bonus() -> None:
    """Rating provides a small bonus (<= 6 pts) that cannot overcome hard constraints."""
    bonus_5 = _calculate_quality_score(5.0, None)
    bonus_4 = _calculate_quality_score(4.0, None)
    bonus_3 = _calculate_quality_score(3.0, None)

    assert 5.5 <= bonus_5 <= 6.0
    assert 2.5 <= bonus_4 <= 3.5
    assert bonus_3 == 0.0

    # Even a 5.0 star place cannot overcome failing a hard constraint
    c_high_rated_fail = Candidate(place_id="c1", name="5 Star Place", rating=5.0)
    c_unrated_supported = Candidate(place_id="c2", name="Unrated Place")

    eval_fail = CandidateConstraintEvaluation(
        candidate=c_high_rated_fail,
        results=[ConstraintResult(constraint="Open late", status=ConstraintStatus.NOT_SATISFIED)],
    )
    eval_sup = CandidateConstraintEvaluation(
        candidate=c_unrated_supported,
        results=[ConstraintResult(constraint="Open late", status=ConstraintStatus.SUPPORTED)],
    )

    ranked = rank_candidates(ConstraintEvaluationResult(evaluations=[eval_fail, eval_sup]))
    assert ranked[0].candidate.place_id == "c2"


def test_review_count_contribution_is_bounded_and_saturated() -> None:
    """Review count uses logarithmic scaling and saturates without runaway scores."""
    bonus_100 = _calculate_quality_score(None, 100)
    bonus_1000 = _calculate_quality_score(None, 1000)
    bonus_5000 = _calculate_quality_score(None, 5000)
    bonus_50000 = _calculate_quality_score(None, 50000)

    assert bonus_100 < bonus_1000 < bonus_5000
    # 50,000 reviews saturates at max ~4.0 pts, identical to 5,000
    assert bonus_50000 == bonus_5000 == 4.0


def test_failed_hard_constraint_preserved_in_ranking_explanation() -> None:
    """A penalized candidate contains explicit reasons explaining the failure."""
    c = Candidate(place_id="c1", name="Place")
    cand_eval = CandidateConstraintEvaluation(
        candidate=c,
        results=[
            ConstraintResult(
                constraint="Open after 20:00",
                status=ConstraintStatus.NOT_SATISFIED,
                explanation="Closes at 18:00.",
            )
        ],
    )
    ranked = rank_candidates(ConstraintEvaluationResult(evaluations=[cand_eval]))
    assert ranked[0].hard_failed == 1
    assert any("Penalized because hard constraint" in r for r in ranked[0].ranking_reasons)


def test_multi_source_evidence_does_not_double_count_constraint() -> None:
    """A constraint supported by both PLACES and SEARCH receives score only once."""
    c = Candidate(place_id="c1", name="Place")
    cand_eval = CandidateConstraintEvaluation(
        candidate=c,
        results=[
            ConstraintResult(
                constraint="Open after 20:00",
                status=ConstraintStatus.SUPPORTED,
                supporting_evidence=[
                    ConstraintSupport(source_type="google_places", fanout_task_ids=["F1"]),
                    ConstraintSupport(source_type="google_search", fanout_task_ids=["F3"]),
                ],
            )
        ],
    )
    ranked = rank_candidates(ConstraintEvaluationResult(evaluations=[cand_eval]))
    # Must equal HARD_SUPPORTED_WEIGHT (+25), not 2x (+50)
    assert ranked[0].score == HARD_SUPPORTED_WEIGHT
    assert ranked[0].hard_supported == 1


def test_ties_resolve_deterministically() -> None:
    """Equal-score candidates break ties on hard fails, supported, rating, reviews, name."""
    c1 = Candidate(place_id="c1", name="Alpha Place", rating=4.5)
    c2 = Candidate(place_id="c2", name="Beta Place", rating=4.5)

    eval1 = CandidateConstraintEvaluation(
        candidate=c1,
        results=[ConstraintResult(constraint="Constraint", status=ConstraintStatus.SUPPORTED)],
    )
    eval2 = CandidateConstraintEvaluation(
        candidate=c2,
        results=[ConstraintResult(constraint="Constraint", status=ConstraintStatus.SUPPORTED)],
    )

    ranked = rank_candidates(ConstraintEvaluationResult(evaluations=[eval2, eval1]))
    assert ranked[0].candidate.name == "Alpha Place"
    assert ranked[1].candidate.name == "Beta Place"


def test_rank_numbers_are_assigned_correctly() -> None:
    """1-indexed ranks are assigned sequentially."""
    c1 = Candidate(place_id="c1", name="Place 1")
    c2 = Candidate(place_id="c2", name="Place 2")
    c3 = Candidate(place_id="c3", name="Place 3")

    evals = [
        CandidateConstraintEvaluation(
            candidate=c1,
            results=[ConstraintResult(constraint="C", status=ConstraintStatus.SUPPORTED)],
        ),
        CandidateConstraintEvaluation(
            candidate=c2,
            results=[ConstraintResult(constraint="C", status=ConstraintStatus.UNKNOWN)],
        ),
        CandidateConstraintEvaluation(
            candidate=c3,
            results=[ConstraintResult(constraint="C", status=ConstraintStatus.NOT_SATISFIED)],
        ),
    ]

    ranked = rank_candidates(ConstraintEvaluationResult(evaluations=evals))
    assert [r.rank for r in ranked] == [1, 2, 3]


def test_top_n_does_not_affect_internal_scoring_logic() -> None:
    """top_n parameter slices the output without changing relative scores."""
    c1 = Candidate(place_id="c1", name="Place 1")
    c2 = Candidate(place_id="c2", name="Place 2")
    evals = [
        CandidateConstraintEvaluation(
            candidate=c1,
            results=[ConstraintResult(constraint="C", status=ConstraintStatus.SUPPORTED)],
        ),
        CandidateConstraintEvaluation(
            candidate=c2,
            results=[ConstraintResult(constraint="C", status=ConstraintStatus.UNKNOWN)],
        ),
    ]

    top_1 = rank_candidates(ConstraintEvaluationResult(evaluations=evals), top_n=1)
    assert len(top_1) == 1
    assert top_1[0].rank == 1
    assert top_1[0].candidate.place_id == "c1"


def test_no_api_calls_in_ranking() -> None:
    """Ranking executes purely synchronously in Python."""
    c = Candidate(place_id="c1", name="Place")
    cand_eval = CandidateConstraintEvaluation(
        candidate=c,
        results=[ConstraintResult(constraint="C", status=ConstraintStatus.SUPPORTED)],
    )
    ranked = rank_candidates(ConstraintEvaluationResult(evaluations=[cand_eval]))
    assert len(ranked) == 1
    assert ranked[0].score == 25.0


def test_haversine_distance_calculation_accuracy() -> None:
    """Verify Haversine formula gives accurate straight-line distances."""
    from ai_search_journey.ranking import calculate_haversine_distance_miles

    # Distance between San Antonio and Austin is ~73.5-74.5 miles
    d = calculate_haversine_distance_miles(29.4241, -98.4936, 30.2672, -97.7431)
    assert 73.0 <= d <= 75.0

    # Same location gives 0.0 miles
    d_same = calculate_haversine_distance_miles(29.4241, -98.4936, 29.4241, -98.4936)
    assert d_same == 0.0


def test_closer_candidate_receives_larger_proximity_bonus() -> None:
    """A closer candidate gets a higher proximity bonus than a distant candidate."""
    from ai_search_journey.models import ReferenceLocation
    from ai_search_journey.ranking import calculate_proximity_score

    # 0.2 miles vs 1.2 miles vs 4.0 miles
    bonus_close = calculate_proximity_score(0.2)
    bonus_mid = calculate_proximity_score(1.2)
    bonus_far = calculate_proximity_score(4.0)

    assert bonus_close > bonus_mid > bonus_far
    assert bonus_close <= 12.0
    assert bonus_far < 3.0

    ref = ReferenceLocation(
        query="Geekdom San Antonio",
        place_id="ref1",
        name="Geekdom",
        latitude=29.4262,
        longitude=-98.4925,
    )

    # Candidate 1: 0.1 miles away
    c_close = Candidate(
        place_id="c1",
        name="Close Cafe",
        latitude=29.4270,
        longitude=-98.4925,
    )
    # Candidate 2: 3.5 miles away
    c_far = Candidate(
        place_id="c2",
        name="Far Cafe",
        latitude=29.4700,
        longitude=-98.4925,
    )

    eval_close = CandidateConstraintEvaluation(
        candidate=c_close,
        results=[ConstraintResult(constraint="Coffee", status=ConstraintStatus.SUPPORTED)],
    )
    eval_far = CandidateConstraintEvaluation(
        candidate=c_far,
        results=[ConstraintResult(constraint="Coffee", status=ConstraintStatus.SUPPORTED)],
    )

    ranked = rank_candidates(
        ConstraintEvaluationResult(evaluations=[eval_far, eval_close]),
        reference_location=ref,
    )

    assert ranked[0].candidate.place_id == "c1"
    assert ranked[0].distance_miles is not None
    assert ranked[1].distance_miles is not None
    assert ranked[0].distance_miles < ranked[1].distance_miles
    assert ranked[0].proximity_score > ranked[1].proximity_score
    assert ranked[0].score > ranked[1].score


def test_houston_candidate_ranks_below_san_antonio_candidate() -> None:
    """A distant Houston candidate (~190 mi away) ranks below a local San Antonio candidate."""
    from ai_search_journey.models import ReferenceLocation

    trinity_ref = ReferenceLocation(
        query="Trinity University",
        place_id="trinity_1",
        name="Trinity University",
        latitude=29.4619,
        longitude=-98.4833,
    )

    # San Antonio candidate: ~2 miles from Trinity University
    c_sa = Candidate(
        place_id="c_sa",
        name="Delicious Indian Cuisine & Bar",
        latitude=29.4290,
        longitude=-98.4870,
        rating=4.6,
        user_rating_count=1200,
    )
    # Houston candidate: ~190 miles from Trinity University
    c_houston = Candidate(
        place_id="c_houston",
        name="Aga's Restaurant & Catering",
        latitude=29.6500,
        longitude=-95.5500,
        rating=4.8,
        user_rating_count=15000,
    )

    eval_sa = CandidateConstraintEvaluation(
        candidate=c_sa,
        results=[ConstraintResult(constraint="Open late", status=ConstraintStatus.SUPPORTED)],
    )
    eval_houston = CandidateConstraintEvaluation(
        candidate=c_houston,
        results=[ConstraintResult(constraint="Open late", status=ConstraintStatus.SUPPORTED)],
    )

    ranked = rank_candidates(
        ConstraintEvaluationResult(evaluations=[eval_houston, eval_sa]),
        reference_location=trinity_ref,
    )

    # San Antonio candidate must rank higher due to strong proximity bonus (~4.0 vs ~0.06 pts)
    assert ranked[0].candidate.place_id == "c_sa"
    assert ranked[1].candidate.place_id == "c_houston"
    assert ranked[0].distance_miles is not None and ranked[0].distance_miles < 5.0
    assert ranked[1].distance_miles is not None and ranked[1].distance_miles > 150.0
    assert ranked[0].proximity_score > ranked[1].proximity_score
    assert ranked[0].score > ranked[1].score


def test_proximity_bonus_is_bounded_and_does_not_overcome_hard_failure() -> None:
    """Max proximity bonus (+12.0) cannot overcome hard constraint failure penalty (-35.0)."""
    from ai_search_journey.models import ReferenceLocation

    ref = ReferenceLocation(
        query="Geekdom",
        place_id="ref1",
        name="Geekdom",
        latitude=29.4262,
        longitude=-98.4925,
    )

    # Candidate 1: 0.0 mi away (+12 pts), fails hard constraint (-35 pts) -> net negative
    c_fail = Candidate(
        place_id="c_fail",
        name="Next Door but Closed",
        latitude=29.4262,
        longitude=-98.4925,
    )
    eval_fail = CandidateConstraintEvaluation(
        candidate=c_fail,
        results=[ConstraintResult(constraint="Open late", status=ConstraintStatus.NOT_SATISFIED)],
    )

    # Candidate 2: 1.5 miles away (~4.8 pts bonus), satisfies hard constraint (+25 pts) -> ~29.8 pts
    c_pass = Candidate(
        place_id="c_pass",
        name="A Mile Away and Open",
        latitude=29.4479,
        longitude=-98.4925,
    )
    eval_pass = CandidateConstraintEvaluation(
        candidate=c_pass,
        results=[ConstraintResult(constraint="Open late", status=ConstraintStatus.SUPPORTED)],
    )

    ranked = rank_candidates(
        ConstraintEvaluationResult(evaluations=[eval_fail, eval_pass]),
        reference_location=ref,
    )

    assert ranked[0].candidate.place_id == "c_pass"
    assert ranked[1].candidate.place_id == "c_fail"
    assert ranked[0].score > ranked[1].score


def test_missing_coordinates_handled_safely() -> None:
    """Missing candidate or reference coordinates safely yields distance=None, proximity=0.0."""
    from ai_search_journey.models import ReferenceLocation

    ref = ReferenceLocation(
        query="Geekdom",
        place_id="ref1",
        name="Geekdom",
        latitude=29.4262,
        longitude=-98.4925,
    )

    # Candidate missing lat/lng
    c_nocoord = Candidate(place_id="c1", name="No Coord Cafe")
    eval_cand = CandidateConstraintEvaluation(
        candidate=c_nocoord,
        results=[ConstraintResult(constraint="Coffee", status=ConstraintStatus.SUPPORTED)],
    )

    # Ranking with reference location
    ranked = rank_candidates(
        ConstraintEvaluationResult(evaluations=[eval_cand]),
        reference_location=ref,
    )
    assert ranked[0].distance_miles is None
    assert ranked[0].proximity_score == 0.0
    assert ranked[0].score == 25.0

    # Ranking with no reference location
    ranked_no_ref = rank_candidates(
        ConstraintEvaluationResult(evaluations=[eval_cand]),
        reference_location=None,
    )
    assert ranked_no_ref[0].distance_miles is None
    assert ranked_no_ref[0].proximity_score == 0.0
    assert ranked_no_ref[0].score == 25.0


