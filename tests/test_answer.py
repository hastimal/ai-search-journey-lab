"""Unit tests for Gemini Grounded Final Answer module."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_search_journey.answer import (
    GeminiGroundedAnswerResponse,
    GeminiRecommendationItem,
    _format_candidate_evidence_payload,
    _validate_and_assemble_grounded_answer,
    generate_grounded_answer,
    is_transient_error,
    redact_secrets,
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
async def test_generate_grounded_answer_primary_success() -> None:
    """Verify primary model succeeds on first attempt and records trace."""
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

    trace_events: list[str] = []
    answer = await generate_grounded_answer(
        question="Find coffee shop near Geekdom",
        intent=intent,
        ranked_candidates=candidates,
        max_candidates=2,
        client=mock_client,
        on_trace=trace_events.append,
    )

    assert answer.summary == "Found 2 top matches."
    assert len(answer.recommendations) == 2
    assert mock_client.aio.models.generate_content.call_count == 1
    call_kwargs = mock_client.aio.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-3.6-flash"
    assert any("primary model 'gemini-3.6-flash'" in ev for ev in trace_events)
    assert any("successfully generated" in ev for ev in trace_events)


@pytest.mark.asyncio
async def test_generate_grounded_answer_primary_transient_retry_success() -> None:
    """Verify primary model retries upon transient 429/503 error and succeeds on second attempt."""
    candidates = [
        _make_candidate("c1", "Kafe Krave", 1),
        _make_candidate("c2", "Halcyon Southtown", 2),
    ]
    intent = SearchIntent(category="coffee shop")

    mock_parsed = GeminiGroundedAnswerResponse(
        answer_summary="Found 2 top matches after retry.",
        recommendations=[
            GeminiRecommendationItem(
                rank=1,
                candidate_name="Kafe Krave",
                summary="Late night spot.",
            ),
            GeminiRecommendationItem(
                rank=2,
                candidate_name="Halcyon Southtown",
                summary="Spacious lounge.",
            ),
        ],
    )

    mock_success = MagicMock()
    mock_success.parsed = mock_parsed

    mock_client = MagicMock()
    # Attempt 1: 429 Rate Limit error; Attempt 2: Success
    transient_error = RuntimeError("429 RESOURCE_EXHAUSTED: Rate limit exceeded")
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=[transient_error, mock_success]
    )

    trace_events: list[str] = []
    answer = await generate_grounded_answer(
        question="Find coffee",
        intent=intent,
        ranked_candidates=candidates,
        max_candidates=2,
        client=mock_client,
        initial_delay=0.0,  # Fast tests without sleeping
        on_trace=trace_events.append,
    )

    assert answer.summary == "Found 2 top matches after retry."
    assert mock_client.aio.models.generate_content.call_count == 2
    # Both calls should be on the primary model
    for c in mock_client.aio.models.generate_content.call_args_list:
        assert c.kwargs["model"] == "gemini-3.6-flash"

    # Verify trace mentions attempt 1 transient error, retrying, and final success
    assert any("attempt 1 failed with transient error" in ev for ev in trace_events)
    assert any("Retrying attempt 2/2" in ev for ev in trace_events)
    assert any("successfully generated" in ev for ev in trace_events)


@pytest.mark.asyncio
async def test_generate_grounded_answer_fallback_success() -> None:
    """Verify fallback model is used after max primary transient retries fail."""
    candidates = [
        _make_candidate("c1", "Kafe Krave", 1),
        _make_candidate("c2", "Halcyon Southtown", 2),
    ]
    intent = SearchIntent(category="coffee shop")

    mock_parsed = GeminiGroundedAnswerResponse(
        answer_summary="Synthesized via fallback model.",
        recommendations=[
            GeminiRecommendationItem(
                rank=1,
                candidate_name="Kafe Krave",
                summary="Top choice.",
            ),
            GeminiRecommendationItem(
                rank=2,
                candidate_name="Halcyon Southtown",
                summary="Runner up.",
            ),
        ],
    )

    mock_fallback_success = MagicMock()
    mock_fallback_success.parsed = mock_parsed

    mock_client = MagicMock()
    # Primary attempt 1 & 2 fail with 503 UNAVAILABLE, Fallback succeeds
    err1 = RuntimeError("503 Service Unavailable: overloaded")
    err2 = RuntimeError("504 Gateway Timeout: deadline exceeded")
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=[err1, err2, mock_fallback_success]
    )

    trace_events: list[str] = []
    answer = await generate_grounded_answer(
        question="Find coffee",
        intent=intent,
        ranked_candidates=candidates,
        max_candidates=2,
        client=mock_client,
        initial_delay=0.0,
        on_trace=trace_events.append,
    )

    assert answer.summary == "Synthesized via fallback model."
    assert mock_client.aio.models.generate_content.call_count == 3
    calls = mock_client.aio.models.generate_content.call_args_list
    assert calls[0].kwargs["model"] == "gemini-3.6-flash"
    assert calls[1].kwargs["model"] == "gemini-3.6-flash"
    assert calls[2].kwargs["model"] == "gemini-3.5-flash-lite"

    assert any("Switching to fallback model 'gemini-3.5-flash-lite'" in ev for ev in trace_events)
    assert any(
        "Fallback model 'gemini-3.5-flash-lite' successfully generated" in ev
        for ev in trace_events
    )


@pytest.mark.asyncio
async def test_generate_grounded_answer_non_retryable_error() -> None:
    """Verify non-retryable 4xx/auth errors fail immediately without retry or fallback."""
    candidates = [_make_candidate("c1", "Kafe Krave", 1)]
    intent = SearchIntent(category="coffee shop")

    mock_client = MagicMock()
    auth_error = RuntimeError("401 UNAUTHENTICATED: API key not valid")
    mock_client.aio.models.generate_content = AsyncMock(side_effect=auth_error)

    trace_events: list[str] = []
    with pytest.raises(RuntimeError, match="with non-retryable error"):
        await generate_grounded_answer(
            question="Find coffee",
            intent=intent,
            ranked_candidates=candidates,
            max_candidates=1,
            client=mock_client,
            initial_delay=0.0,
            on_trace=trace_events.append,
        )

    # Exactly 1 call made (no retry, no fallback)
    assert mock_client.aio.models.generate_content.call_count == 1
    assert any("non-retryable error" in ev for ev in trace_events)
    assert any("Skipping retry and fallback" in ev for ev in trace_events)


@pytest.mark.asyncio
async def test_generate_grounded_answer_both_models_fail() -> None:
    """Verify RuntimeError is raised when primary retries and fallback all fail."""
    candidates = [_make_candidate("c1", "Kafe Krave", 1)]
    intent = SearchIntent(category="coffee shop")

    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=[
            RuntimeError("429 RESOURCE_EXHAUSTED"),
            RuntimeError("429 RESOURCE_EXHAUSTED"),
            RuntimeError("503 Service Unavailable"),
        ]
    )

    trace_events: list[str] = []
    with pytest.raises(RuntimeError, match="failed on both primary.*and fallback"):
        await generate_grounded_answer(
            question="Find coffee",
            intent=intent,
            ranked_candidates=candidates,
            max_candidates=1,
            client=mock_client,
            initial_delay=0.0,
            on_trace=trace_events.append,
        )

    assert mock_client.aio.models.generate_content.call_count == 3
    assert any("Fallback model 'gemini-3.5-flash-lite' failed" in ev for ev in trace_events)


@pytest.mark.asyncio
async def test_generate_grounded_answer_redacts_secrets_in_trace() -> None:
    """Verify API keys and credentials are never exposed in developer trace."""
    candidates = [_make_candidate("c1", "Kafe Krave", 1)]
    intent = SearchIntent(category="coffee shop")

    secret_key = "AIzaSyDummySecretKey1234567890abcdef"
    mock_client = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(
        side_effect=RuntimeError(f"429 Quota exceeded for key={secret_key}")
    )

    trace_events: list[str] = []
    with pytest.raises(RuntimeError):
        await generate_grounded_answer(
            question="Find coffee",
            intent=intent,
            ranked_candidates=candidates,
            max_candidates=1,
            client=mock_client,
            initial_delay=0.0,
            on_trace=trace_events.append,
        )

    full_trace_str = " ".join(trace_events)
    assert secret_key not in full_trace_str
    assert "[REDACTED" in full_trace_str


def test_is_transient_error_classification() -> None:
    """Verify is_transient_error correctly categorizes error conditions."""
    # Transient errors
    assert is_transient_error(RuntimeError("429 RESOURCE_EXHAUSTED")) is True
    assert is_transient_error(RuntimeError("503 Service Unavailable")) is True
    assert is_transient_error(RuntimeError("504 Gateway Timeout")) is True
    assert is_transient_error(TimeoutError("Connection timed out")) is True
    assert is_transient_error(ConnectionError("Connection reset by peer")) is True

    # Non-retryable errors
    assert is_transient_error(RuntimeError("401 UNAUTHENTICATED: API key invalid")) is False
    assert is_transient_error(RuntimeError("403 PERMISSION_DENIED")) is False
    assert is_transient_error(RuntimeError("400 INVALID_ARGUMENT")) is False
    assert is_transient_error(RuntimeError("404 NOT_FOUND")) is False
    assert is_transient_error(RuntimeError("500 INTERNAL_SERVER_ERROR")) is False
    assert is_transient_error(RuntimeError("502 BAD_GATEWAY")) is False
    assert is_transient_error(RuntimeError("Content blocked due to SAFETY policy")) is False
    assert is_transient_error(ValueError("Invalid schema")) is False
    assert is_transient_error(TypeError("Unexpected argument")) is False


def test_redact_secrets() -> None:
    """Verify redact_secrets properly masks sensitive API keys."""
    raw = "Request failed for key=AIzaSyA_TestKey1234567890ABCDEF12345 with token=secret123"
    sanitized = redact_secrets(raw)
    assert "AIzaSyA_TestKey1234567890ABCDEF12345" not in sanitized
    assert "secret123" not in sanitized
    assert redact_secrets("") == ""
