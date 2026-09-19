"""Unit tests for Gemini Grounded Final Answer module."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_search_journey.answer import (
    GeminiGroundedAnswerResponse,
    GeminiRecommendationItem,
    _format_candidate_evidence_payload,
    _validate_and_assemble_grounded_answer,
    generate_grounded_answer,
)
from ai_search_journey.models import (
    Candidate,
    ConstraintResult,
    ConstraintStatus,
    ConstraintSupport,
    RankedCandidate,
    SearchIntent,
)


def _make_candidate(
    place_id: str,
    name: str,
    rank: int,
    score: float = 40.0,
    google_maps_url: str = "https://maps.google.com/?cid=123",
) -> RankedCandidate:
    cand = Candidate(
        place_id=place_id,
        name=name,
        formatted_address="123 Main St, San Antonio, TX",
        latitude=29.4260,
        longitude=-98.4930,
        google_maps_url=google_maps_url,
    )
    return RankedCandidate(
        candidate=cand,
        rank=rank,
        score=score,
        constraint_results=[
            ConstraintResult(
                constraint="Open after 20:00",
                status=ConstraintStatus.SUPPORTED,
                supporting_evidence=[
                    ConstraintSupport(source_type="google_places", fanout_task_ids=["F1"])
                ],
            ),
            ConstraintResult(
                constraint="Group size 6",
                status=ConstraintStatus.UNKNOWN,
            ),
            ConstraintResult(
                constraint="quiet (Preference)",
                status=ConstraintStatus.SUPPORTED,
                supporting_evidence=[
                    ConstraintSupport(
                        source_type="google_search",
                        fanout_task_ids=["F3"],
                        source_title="Study Guide SA",
                        source_url="https://example.com/study",
                    )
                ],
            ),
        ],
        distance_miles=0.5,
        proximity_score=8.0,
        quality_score=7.5,
    )


def test_format_candidate_evidence_payload() -> None:
    """Verify clean compact payload creation for Top candidates."""
    candidates = [
        _make_candidate("c1", "Place Alpha", 1),
        _make_candidate("c2", "Place Beta", 2),
        _make_candidate("c3", "Place Gamma", 3),
        _make_candidate("c4", "Place Delta", 4),
    ]

    payload = _format_candidate_evidence_payload(candidates, max_candidates=3)
    assert len(payload) == 3
    assert payload[0]["candidate_name"] == "Place Alpha"
    assert payload[0]["rank"] == 1
    assert len(payload[0]["supported_constraints"]) == 2
    assert payload[0]["unknown_constraints"] == ["Group size 6"]


def test_validate_and_assemble_grounded_answer_success() -> None:
    """Verify validation passes when Gemini preserves exact names, ranks, and maps URLs."""
    candidates = [
        _make_candidate("c1", "Place Alpha", 1, google_maps_url="https://maps.google.com/1"),
        _make_candidate("c2", "Place Beta", 2, google_maps_url="https://maps.google.com/2"),
        _make_candidate("c3", "Place Gamma", 3, google_maps_url="https://maps.google.com/3"),
    ]

    raw = GeminiGroundedAnswerResponse(
        answer_summary="Summary of findings.",
        recommendations=[
            GeminiRecommendationItem(
                rank=1,
                candidate_name="Place Alpha",
                summary="Top match summary.",
                why_it_matches=["Open late (Google Places [F1])"],
                unknowns=["Group size 6 unverified"],
                conflicts=[],
                evidence_sources=["Google Places [F1]"],
            ),
            GeminiRecommendationItem(
                rank=2,
                candidate_name="Place Beta",
                summary="Second match summary.",
                why_it_matches=["Open late (Google Places [F1])"],
                unknowns=[],
                conflicts=[],
                evidence_sources=["Google Places [F1]"],
            ),
            GeminiRecommendationItem(
                rank=3,
                candidate_name="Place Gamma",
                summary="Third match summary.",
                why_it_matches=["Open late (Google Places [F1])"],
                unknowns=[],
                conflicts=[],
                evidence_sources=["Google Places [F1]"],
            ),
        ],
        caveats=["Check hours beforehand."],
    )

    answer = _validate_and_assemble_grounded_answer(raw, candidates, max_candidates=3)
    assert answer.summary == "Summary of findings."
    assert len(answer.recommendations) == 3
    assert answer.recommendations[0].candidate_name == "Place Alpha"
    assert answer.recommendations[0].rank == 1
    assert answer.recommendations[0].maps_url == "https://maps.google.com/1"
    assert answer.recommendations[1].maps_url == "https://maps.google.com/2"
    assert "https://example.com/study" in answer.citations


def test_reject_reordered_candidates() -> None:
    """Verify ValueError is raised if Gemini swaps candidate order."""
    candidates = [
        _make_candidate("c1", "Place Alpha", 1),
        _make_candidate("c2", "Place Beta", 2),
    ]

    raw_reordered = GeminiGroundedAnswerResponse(
        answer_summary="Summary.",
        recommendations=[
            GeminiRecommendationItem(
                rank=1,
                candidate_name="Place Beta",  # Swapped
                summary="Beta summary.",
            ),
            GeminiRecommendationItem(
                rank=2,
                candidate_name="Place Alpha",
                summary="Alpha summary.",
            ),
        ],
    )

    with pytest.raises(ValueError, match="Gemini introduced unknown or reordered candidate name"):
        _validate_and_assemble_grounded_answer(raw_reordered, candidates, max_candidates=2)


def test_reject_hallucinated_candidate_name() -> None:
    """Verify ValueError is raised if Gemini invents a new business."""
    candidates = [
        _make_candidate("c1", "Place Alpha", 1),
    ]

    raw_hallucinated = GeminiGroundedAnswerResponse(
        answer_summary="Summary.",
        recommendations=[
            GeminiRecommendationItem(
                rank=1,
                candidate_name="Starbucks Hallucinated",
                summary="Invented place.",
            ),
        ],
    )

    with pytest.raises(ValueError, match="Gemini introduced unknown or reordered candidate name"):
        _validate_and_assemble_grounded_answer(raw_hallucinated, candidates, max_candidates=1)


def test_reject_altered_rank_numbers() -> None:
    """Verify ValueError is raised if Gemini changes rank numbers."""
    candidates = [
        _make_candidate("c1", "Place Alpha", 1),
    ]

    raw_bad_rank = GeminiGroundedAnswerResponse(
        answer_summary="Summary.",
        recommendations=[
            GeminiRecommendationItem(
                rank=5,  # Altered rank number
                candidate_name="Place Alpha",
                summary="Summary.",
            ),
        ],
    )

    with pytest.raises(ValueError, match="Gemini altered candidate rank"):
        _validate_and_assemble_grounded_answer(raw_bad_rank, candidates, max_candidates=1)


def test_reject_wrong_recommendation_count() -> None:
    """Verify ValueError is raised if recommendation list length does not match Top N."""
    candidates = [
        _make_candidate("c1", "Place Alpha", 1),
        _make_candidate("c2", "Place Beta", 2),
    ]

    raw_short = GeminiGroundedAnswerResponse(
        answer_summary="Summary.",
        recommendations=[
            GeminiRecommendationItem(
                rank=1,
                candidate_name="Place Alpha",
                summary="Summary.",
            ),
        ],
    )

    with pytest.raises(ValueError, match="Gemini returned 1 recommendations; expected exactly 2"):
        _validate_and_assemble_grounded_answer(raw_short, candidates, max_candidates=2)


@pytest.mark.asyncio
async def test_generate_grounded_answer_mocked_gemini() -> None:
    """Verify generate_grounded_answer executes cleanly with mocked Gemini client."""
    candidates = [
        _make_candidate("c1", "Kafe Krave", 1),
        _make_candidate("c2", "Halcyon Southtown", 2),
    ]
    intent = SearchIntent(category="coffee shop")

    mock_parsed = GeminiGroundedAnswerResponse(
        answer_summary="Found 2 top matches.",
        recommendations=[
            GeminiRecommendationItem(
                rank=1,
                candidate_name="Kafe Krave",
                summary="Closest late-night option.",
                why_it_matches=["Open after 20:00 (Google Places [F1])"],
                unknowns=["Group size 6 is unverified"],
            ),
            GeminiRecommendationItem(
                rank=2,
                candidate_name="Halcyon Southtown",
                summary="Spacious work-friendly option.",
                why_it_matches=["Open after 20:00 (Google Places [F1])"],
                unknowns=["Group size 6 is unverified"],
            ),
        ],
        caveats=["Call ahead for large group seating."],
    )

    mock_response = MagicMock()
    mock_response.parsed = mock_parsed

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

    answer = await generate_grounded_answer(
        question="Find coffee shop near Geekdom",
        intent=intent,
        ranked_candidates=candidates,
        max_candidates=2,
        client=mock_client,
    )

    assert answer.summary == "Found 2 top matches."
    assert len(answer.recommendations) == 2
    assert answer.recommendations[0].candidate_name == "Kafe Krave"
    assert answer.recommendations[1].candidate_name == "Halcyon Southtown"
    assert "Group size 6 is unverified" in answer.recommendations[0].unknowns
    mock_client.aio.models.generate_content.assert_called_once()
