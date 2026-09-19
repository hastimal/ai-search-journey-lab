"""Deterministic, explainable ranking module for AI Search Journey."""

import math
from typing import Optional

from ai_search_journey.models import (
    CandidateConstraintEvaluation,
    CategoryEligibility,
    ConstraintEvaluationResult,
    ConstraintResult,
    ConstraintStatus,
    RankedCandidate,
    ReferenceLocation,
)

# Deterministic Scoring Constants
HARD_SUPPORTED_WEIGHT: float = 25.0
HARD_UNKNOWN_WEIGHT: float = 0.0
HARD_NOT_SATISFIED_WEIGHT: float = -35.0

PREFERENCE_SUPPORTED_WEIGHT: float = 10.0
PREFERENCE_UNKNOWN_WEIGHT: float = 0.0
PREFERENCE_NOT_SATISFIED_WEIGHT: float = -10.0

MAX_RATING_BONUS: float = 6.0
MAX_REVIEWS_BONUS: float = 4.0
SATURATION_REVIEW_COUNT: float = 5000.0

MAX_PROXIMITY_BONUS: float = 12.0


def calculate_haversine_distance_miles(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Calculate the great circle distance in miles between two latitude/longitude points."""
    r_earth = 3958.8  # Earth radius in miles
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2.0) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(r_earth * c, 2)


def calculate_proximity_score(distance_miles: float) -> float:
    """Calculate smooth bounded proximity bonus from distance in miles (max 12.0 pts).

    Formula: bonus = MAX_PROXIMITY_BONUS / (1.0 + distance_miles)
    - 0.0 mi  -> 12.00 pts
    - 0.5 mi  -> 8.00 pts
    - 1.0 mi  -> 6.00 pts
    - 2.0 mi  -> 4.00 pts
    - 5.0 mi  -> 2.00 pts
    - 190 mi  -> 0.06 pts (Houston vs San Antonio)
    """
    if distance_miles < 0.0:
        return 0.0
    bonus = MAX_PROXIMITY_BONUS / (1.0 + distance_miles)
    return round(bonus, 2)


def _calculate_quality_score(
    rating: Optional[float],
    user_rating_count: Optional[int],
) -> float:
    """Calculate bounded secondary quality bonus from rating and review count (max ~10 pts)."""
    rating_bonus = 0.0
    if rating is not None:
        normalized_rating = max(0.0, min(1.0, (rating - 3.0) / 2.0))
        rating_bonus = normalized_rating * MAX_RATING_BONUS

    reviews_bonus = 0.0
    if user_rating_count is not None and user_rating_count > 0:
        log_rev = math.log10(user_rating_count + 1)
        log_max = math.log10(SATURATION_REVIEW_COUNT + 1)
        reviews_bonus = min(1.0, log_rev / log_max) * MAX_REVIEWS_BONUS

    return round(rating_bonus + reviews_bonus, 2)


def _format_source_label(result: ConstraintResult) -> str:
    """Format human-readable source label with task IDs."""
    if not result.supporting_evidence:
        return "unspecified evidence"
    sources: list[str] = []
    for s in result.supporting_evidence:
        src_name = "Google Places" if s.source_type == "google_places" else "Google Search"
        task_str = f" [{','.join(s.fanout_task_ids)}]" if s.fanout_task_ids else ""
        sources.append(f"{src_name}{task_str}")
    return ", ".join(sources)


def _evaluate_single_candidate(
    candidate_eval: CandidateConstraintEvaluation,
    reference_location: Optional[ReferenceLocation] = None,
) -> RankedCandidate:
    """Score a candidate against constraints, proximity, and quality."""
    candidate = candidate_eval.candidate
    results = candidate_eval.results

    hard_supported = 0
    hard_unknown = 0
    hard_failed = 0
    preference_supported = 0
    preference_unknown = 0
    preference_failed = 0

    score = 0.0
    reasons: list[str] = []

    for r in results:
        is_pref = "(preference)" in r.constraint.lower()
        clean_name = r.constraint.replace(" (Preference)", "").strip()

        if is_pref:
            if r.status == ConstraintStatus.SUPPORTED:
                preference_supported += 1
                score += PREFERENCE_SUPPORTED_WEIGHT
                src_label = _format_source_label(r)
                reasons.append(f"Satisfies preference '{clean_name}' (supported by {src_label}).")
            elif r.status == ConstraintStatus.NOT_SATISFIED:
                preference_failed += 1
                score += PREFERENCE_NOT_SATISFIED_WEIGHT
                reasons.append(f"Fails preference '{clean_name}'.")
            else:
                preference_unknown += 1
                score += PREFERENCE_UNKNOWN_WEIGHT
        else:
            if r.status == ConstraintStatus.SUPPORTED:
                hard_supported += 1
                score += HARD_SUPPORTED_WEIGHT
                src_label = _format_source_label(r)
                reasons.append(
                    f"Supports hard constraint '{clean_name}' (supported by {src_label})."
                )
            elif r.status == ConstraintStatus.NOT_SATISFIED:
                hard_failed += 1
                score += HARD_NOT_SATISFIED_WEIGHT
                reasons.append(
                    f"Penalized because hard constraint '{clean_name}' is not satisfied "
                    f"({r.explanation or 'contradicted by evidence'})."
                )
            else:
                hard_unknown += 1
                score += HARD_UNKNOWN_WEIGHT
                reasons.append(f"Hard constraint '{clean_name}' evidence is unknown / unverified.")

    # Proximity calculation
    distance_miles: Optional[float] = None
    proximity_score: float = 0.0
    if (
        reference_location is not None
        and candidate.latitude is not None
        and candidate.longitude is not None
    ):
        dist = calculate_haversine_distance_miles(
            reference_location.latitude,
            reference_location.longitude,
            candidate.latitude,
            candidate.longitude,
        )
        distance_miles = dist
        proximity_score = calculate_proximity_score(dist)
        score += proximity_score
        reasons.append(
            f"{dist:.2f} miles from {reference_location.name} "
            f"(+{proximity_score:.2f} proximity points)."
        )

    # Quality calculation
    quality_score = _calculate_quality_score(candidate.rating, candidate.user_rating_count)
    score += quality_score

    if candidate.rating is not None and candidate.user_rating_count is not None:
        reasons.append(
            f"Quality signal: {candidate.rating}★ from {candidate.user_rating_count:,} reviews "
            f"(+{quality_score:.1f} pts)."
        )
    elif candidate.rating is not None:
        reasons.append(
            f"Quality signal: {candidate.rating}★ (+{quality_score:.1f} pts)."
        )

    # Find category eligibility if present in results
    category_eligibility = None
    for r in results:
        if r.constraint.startswith("Category:"):
            category_eligibility = CategoryEligibility(
                status=r.status,
                requested_category=r.constraint.replace("Category:", "").strip(),
                primary_type=candidate.primary_type,
                place_types=candidate.place_types,
                explanation=r.explanation or "",
            )
            break

    return RankedCandidate(
        candidate=candidate,
        score=round(score, 2),
        rank=1,
        constraint_results=results,
        category_eligibility=category_eligibility,
        hard_supported=hard_supported,
        hard_unknown=hard_unknown,
        hard_failed=hard_failed,
        preference_supported=preference_supported,
        preference_unknown=preference_unknown,
        preference_failed=preference_failed,
        distance_miles=distance_miles,
        proximity_score=proximity_score,
        quality_score=quality_score,
        ranking_reasons=reasons,
    )


def rank_candidates(
    evaluation_result: ConstraintEvaluationResult,
    *,
    reference_location: Optional[ReferenceLocation] = None,
    top_n: Optional[int] = None,
) -> list[RankedCandidate]:
    """Rank candidates deterministically based on constraints, proximity, and quality signals.

    Ranking Principles:
    - Pure deterministic Python computation without Gemini or external API calls.
    - Hard constraints have strong positive (+25) and negative (-35) weights.
    - Preferences provide modest positive (+10) and negative (-10) adjustments.
    - Proximity provides a smooth bounded bonus (max +15.0 pts) based on Haversine distance.
    - Rating and review count contribute a bounded quality bonus (max ~10 pts).
    - Multi-source evidence does not double-count constraint scores.
    - Deterministic tie-breaking: score -> fewer hard fails -> more hard supported
      -> closer distance -> rating -> review count -> candidate name.

    Args:
        evaluation_result: The candidate-by-constraint evaluation result matrix.
        reference_location: Optional resolved ReferenceLocation for proximity scoring.
        top_n: Optional limit to return the top N ranked candidates (default: all).

    Returns:
        List of RankedCandidate objects with ranks assigned.
    """
    if not evaluation_result.evaluations:
        return []

    ranked = [
        _evaluate_single_candidate(cand_eval, reference_location=reference_location)
        for cand_eval in evaluation_result.evaluations
    ]

    # Deterministic multi-tier sort
    ranked.sort(
        key=lambda r: (
            r.score,
            -r.hard_failed,
            r.hard_supported,
            -(r.distance_miles if r.distance_miles is not None else 9999.0),
            r.candidate.rating or 0.0,
            r.candidate.user_rating_count or 0,
            # Reverse name for ascending alphabetical order in descending sort
            tuple(-ord(c) for c in r.candidate.name),
        ),
        reverse=True,
    )

    # Assign 1-indexed ranks
    for idx, r in enumerate(ranked, 1):
        r.rank = idx

    if top_n is not None and top_n > 0:
        return ranked[:top_n]

    return ranked

