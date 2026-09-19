"""Unit tests for core search journey data models."""

import pytest
from pydantic import ValidationError

from ai_search_journey.models import (
    Candidate,
    ConstraintResult,
    ConstraintStatus,
    Evidence,
    EvidenceSource,
    FanoutQuery,
    FinalRecommendation,
    GroundedAnswer,
    IntentType,
    JourneyResult,
    RankedCandidate,
    SearchIntent,
    ToolName,
)


def test_intent_type_enum_values() -> None:
    """Verify IntentType enum members."""
    assert IntentType.INFORMATIONAL.value == "informational"
    assert IntentType.NAVIGATIONAL.value == "navigational"
    assert IntentType.COMMERCIAL.value == "commercial"
    assert IntentType.TRANSACTIONAL.value == "transactional"
    assert IntentType.LOCAL_DISCOVERY.value == "local_discovery"


def test_search_intent_coffee_shop_scenario() -> None:
    """Test creating SearchIntent for coffee shop request."""
    intent = SearchIntent(
        intent_types=[IntentType.COMMERCIAL, IntentType.LOCAL_DISCOVERY],
        category="coffee shop",
        reference_location="Geekdom San Antonio",
        group_size=6,
        open_after="20:00",
        hard_constraints=["open_after_20:00", "fits_group_6"],
        preferences=["quiet", "work-friendly"],
        requested_result_count=3,
    )
    assert IntentType.COMMERCIAL in intent.intent_types
    assert IntentType.LOCAL_DISCOVERY in intent.intent_types
    assert intent.category == "coffee shop"
    assert intent.reference_location == "Geekdom San Antonio"
    assert intent.group_size == 6
    assert intent.open_after == "20:00"
    assert "quiet" in intent.preferences
    assert intent.requested_result_count == 3


def test_search_intent_indian_restaurant_scenario() -> None:
    """Test creating SearchIntent for Indian restaurant request (generic schema verification)."""
    intent = SearchIntent(
        intent_types=[IntentType.COMMERCIAL, IntentType.LOCAL_DISCOVERY],
        category="Indian restaurant",
        reference_location="Trinity University",
        group_size=8,
        open_after="21:00",
        hard_constraints=["open_after_21:00", "fits_group_8"],
        preferences=["vegetarian options"],
        requested_result_count=3,
    )
    assert IntentType.COMMERCIAL in intent.intent_types
    assert IntentType.LOCAL_DISCOVERY in intent.intent_types
    assert intent.category == "Indian restaurant"
    assert intent.reference_location == "Trinity University"
    assert intent.group_size == 8
    assert intent.open_after == "21:00"
    assert "vegetarian options" in intent.preferences


def test_invalid_group_size_rejected() -> None:
    """Verify group_size <= 0 raises ValidationError."""
    with pytest.raises(ValidationError):
        SearchIntent(group_size=0)

    with pytest.raises(ValidationError):
        SearchIntent(group_size=-5)


def test_invalid_latitude_longitude_rejected() -> None:
    """Verify invalid latitude/longitude ranges raise ValidationError."""
    with pytest.raises(ValidationError):
        Candidate(place_id="p1", name="Place", latitude=95.0)

    with pytest.raises(ValidationError):
        Candidate(place_id="p1", name="Place", longitude=-200.0)


def test_constraint_status_enum_values() -> None:
    """Verify ConstraintStatus enum values."""
    assert ConstraintStatus.SUPPORTED.value == "supported"
    assert ConstraintStatus.UNKNOWN.value == "unknown"
    assert ConstraintStatus.NOT_SATISFIED.value == "not_satisfied"

    # Verify UNKNOWN is distinct
    assert ConstraintStatus.UNKNOWN != ConstraintStatus.NOT_SATISFIED
    assert ConstraintStatus.UNKNOWN != ConstraintStatus.SUPPORTED


def test_full_journey_result_construction() -> None:
    """Verify constructing a full nested JourneyResult with synthetic data."""
    intent = SearchIntent(
        intent_types=[IntentType.COMMERCIAL, IntentType.LOCAL_DISCOVERY],
        category="coffee shop",
        reference_location="Geekdom San Antonio",
        group_size=6,
        open_after="20:00",
        hard_constraints=["open_after_20:00"],
        preferences=["quiet"],
    )

    fanout = [
        FanoutQuery(
            goal="Find nearby coffee shops",
            query="coffee shop near Geekdom San Antonio",
            tool=ToolName.GOOGLE_PLACES,
        ),
        FanoutQuery(
            goal="Check quiet atmosphere reviews",
            query="quiet study coffee shop Geekdom San Antonio reviews",
            tool=ToolName.GOOGLE_SEARCH,
        ),
    ]

    candidate = Candidate(
        place_id="place_123",
        name="Local Roast Coffee",
        formatted_address="112 E Pecan St, San Antonio, TX 78205",
        latitude=29.4267,
        longitude=-98.4900,
        rating=4.7,
        user_rating_count=350,
        google_maps_url="https://maps.google.com/?cid=123",
        opening_hours=["Monday: 7:00 AM - 10:00 PM"],
    )

    evidence = [
        Evidence(
            candidate_id="place_123",
            attribute="hours",
            claim="Open until 10 PM daily",
            source=EvidenceSource.GOOGLE_PLACES,
        ),
        Evidence(
            candidate_id="place_123",
            attribute="atmosphere",
            claim="Plenty of space for group study and quiet seating area in back",
            source=EvidenceSource.GOOGLE_SEARCH,
            source_url="https://example.com/review",
        ),
    ]

    constraint_results = [
        ConstraintResult(
            constraint="open_after_20:00",
            status=ConstraintStatus.SUPPORTED,
            reason="Place closes at 10 PM (22:00)",
            evidence=[evidence[0]],
        ),
        ConstraintResult(
            constraint="quiet",
            status=ConstraintStatus.SUPPORTED,
            reason="Reviews confirm quiet seating area",
            evidence=[evidence[1]],
        ),
    ]

    ranked_candidate = RankedCandidate(
        candidate=candidate,
        score=0.95,
        constraint_results=constraint_results,
        ranking_reasons=["Satisfies all hard constraints", "High user rating"],
    )

    recommendation = FinalRecommendation(
        rank=1,
        candidate_name="Local Roast Coffee",
        summary="Matches group work and late night criteria.",
        why_it_matches=["Open after 20:00 (Google Places)"],
        unknowns=[],
        conflicts=[],
        evidence_sources=["Google Places"],
        maps_url="https://maps.google.com/?cid=123",
    )

    answer = GroundedAnswer(
        summary="Found 1 excellent coffee shop matching all requirements.",
        recommendations=[recommendation],
        citations=["https://maps.google.com/?cid=123", "https://example.com/review"],
    )

    journey = JourneyResult(
        question=(
            "Find a coffee shop near Geekdom San Antonio for 6 people "
            "to work together, preferably quiet, and open after 8 PM."
        ),
        intent=intent,
        fanout=fanout,
        candidates=[candidate],
        evidence=evidence,
        ranking=[ranked_candidate],
        answer=answer,
    )

    assert journey.question.startswith("Find a coffee shop")
    assert journey.intent.group_size == 6
    assert len(journey.fanout) == 2
    assert journey.candidates[0].name == "Local Roast Coffee"
    assert journey.ranking[0].score == 0.95
    assert journey.answer is not None
    assert len(journey.answer.recommendations) == 1
