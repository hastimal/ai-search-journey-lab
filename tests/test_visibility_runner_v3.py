"""Unit tests for visibility scan runner (V3 Milestone 5)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import ai_search_journey.visibility.runner
from ai_search_journey.models import (
    Candidate,
    FanoutQuery,
    FinalRecommendation,
    GroundedAnswer,
    JourneyExecutionTrace,
    JourneyResult,
    JourneyStepTiming,
    RankedCandidate,
    RetrievalOccurrence,
    SearchIntent,
    StepExecutionStatus,
    ToolName,
)
from ai_search_journey.visibility.extractor import AmbiguousBrandMatchError
from ai_search_journey.visibility.models import (
    BrandProfile,
    PromptDefinition,
    ScanStatus,
    VisibilityProject,
    VisibilityScan,
)
from ai_search_journey.visibility.repository import (
    DuplicateScanError,
    InMemoryVisibilityRepository,
)
from ai_search_journey.visibility.runner import (
    IncompleteJourneyError,
    InconsistentScanError,
    run_visibility_scan,
)

# ======================================================================
# Test Fixtures
# ======================================================================


def _make_journey_fixture(
    *,
    question: str = "best coffee in Austin",
    is_complete: bool = True,
    failed_step: str | None = None,
) -> JourneyResult:
    intent = SearchIntent(
        category="coffee shop",
        reference_location="Austin",
        group_size=2,
    )
    t1 = FanoutQuery(
        task_id="task_1",
        goal="Discover coffee shops",
        query="coffee shops Austin",
        tool=ToolName.GOOGLE_PLACES,
    )
    c1 = Candidate(
        place_id="place_target",
        name="Target Coffee",
        website="https://targetcoffee.com",
        retrieval_occurrences=[
            RetrievalOccurrence(
                query_task_id="task_1",
                query_text="coffee shops Austin",
                position=1,
                place_id="place_target",
            )
        ],
    )
    c2 = Candidate(
        place_id="place_comp",
        name="Competitor Coffee",
        website="https://compcoffee.com",
        retrieval_occurrences=[
            RetrievalOccurrence(
                query_task_id="task_1",
                query_text="coffee shops Austin",
                position=2,
                place_id="place_comp",
            )
        ],
    )
    ranked1 = RankedCandidate(candidate=c1, score=9.0, rank=1)
    ranked2 = RankedCandidate(candidate=c2, score=8.0, rank=2)
    answer = GroundedAnswer(
        summary="Target Coffee is recommended.",
        recommendations=[
            FinalRecommendation(rank=1, candidate_name="Target Coffee", summary="Great place"),
        ],
    )

    steps = [
        JourneyStepTiming(
            key="intent",
            label="Intent",
            status=(
                StepExecutionStatus.FAILED
                if failed_step == "intent"
                else StepExecutionStatus.COMPLETED
            ),
            error="Failed intent" if failed_step == "intent" else None,
        ),
        JourneyStepTiming(
            key="retrieval",
            label="Retrieval",
            status=(
                StepExecutionStatus.FAILED
                if failed_step == "retrieval"
                else StepExecutionStatus.COMPLETED
            ),
            error="Failed retrieval" if failed_step == "retrieval" else None,
        ),
    ]
    trace = JourneyExecutionTrace(
        steps=steps,
        is_complete=is_complete,
        failed_step_key=failed_step,
    )

    return JourneyResult(
        question=question,
        intent=intent,
        fanout=[t1],
        candidates=[c1, c2],
        ranking=[ranked1, ranked2],
        answer=answer,
        execution_trace=trace,
    )


def _make_profiles() -> tuple[
    BrandProfile, list[BrandProfile], VisibilityProject, PromptDefinition
]:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    target = BrandProfile(
        brand_id="target_brand",
        name="Target Coffee",
        domain="targetcoffee.com",
        place_ids=["place_target"],
    )
    comp = BrandProfile(
        brand_id="comp_brand",
        name="Competitor Coffee",
        domain="compcoffee.com",
        place_ids=["place_comp"],
    )
    project = VisibilityProject(
        project_id="proj_austin",
        name="Austin Coffee",
        target_brand_id="target_brand",
        competitor_brand_ids=["comp_brand"],
        created_at=now,
    )
    prompt = PromptDefinition(
        prompt_id="prompt_1",
        prompt_text="best coffee in Austin",
        category="coffee",
        enabled=True,
        created_at=now,
    )
    return target, [comp], project, prompt


# ======================================================================
# Runner Tests
# ======================================================================


def test_runner_calls_extractor_once_and_saves_once() -> None:
    """1. Verify runner extracts bundle exactly once and saves through repository exactly once."""
    target, comps, project, prompt = _make_profiles()
    journey = _make_journey_fixture()
    repo = InMemoryVisibilityRepository()

    with patch(
        "ai_search_journey.visibility.runner.extract_visibility_scan_bundle",
        side_effect=ai_search_journey.visibility.runner.extract_visibility_scan_bundle,
    ) as spy_extract:
        result = run_visibility_scan(
            journey=journey,
            target_brand=target,
            competitor_brands=comps,
            repository=repo,
            project=project,
            prompt=prompt,
            scan_id="scan_test_001",
        )

        assert spy_extract.call_count == 1
        assert result.saved is True
        assert result.scan_id == "scan_test_001"
        assert result.scan.status == ScanStatus.COMPLETED

        # Verify saved in repository
        retrieved = repo.get_bundle("scan_test_001")
        assert retrieved is not None
        assert retrieved.scan.scan_id == "scan_test_001"
        assert len(retrieved.brand_observations) == 2


def test_runner_surfaces_duplicate_scan_error() -> None:
    """2. Verify runner propagates DuplicateScanError cleanly when scan_id collides."""
    target, comps, project, prompt = _make_profiles()
    journey = _make_journey_fixture()
    repo = InMemoryVisibilityRepository()

    # First save succeeds
    run_visibility_scan(
        journey=journey,
        target_brand=target,
        competitor_brands=comps,
        repository=repo,
        project=project,
        prompt=prompt,
        scan_id="scan_dup_001",
    )

    # Make second journey different to trigger conflict
    diff_journey = _make_journey_fixture(question="different coffee query")

    with pytest.raises(DuplicateScanError, match="Conflicting scan bundle already exists"):
        run_visibility_scan(
            journey=diff_journey,
            target_brand=target,
            competitor_brands=comps,
            repository=repo,
            project=project,
            prompt=prompt,
            scan_id="scan_dup_001",
        )


def test_runner_rejects_incomplete_journey_before_persistence() -> None:
    """3. Verify incomplete or failed JourneyResult is rejected before any repository save."""
    target, comps, project, prompt = _make_profiles()
    repo = InMemoryVisibilityRepository()
    mock_repo = MagicMock(spec=repo)

    # Incomplete trace
    incomplete_journey = _make_journey_fixture(is_complete=False)
    with pytest.raises(IncompleteJourneyError, match="not complete"):
        run_visibility_scan(
            journey=incomplete_journey,
            target_brand=target,
            competitor_brands=comps,
            repository=mock_repo,
        )
    assert mock_repo.save_bundle.call_count == 0

    # Failed step in trace
    failed_journey = _make_journey_fixture(failed_step="intent")
    with pytest.raises(IncompleteJourneyError, match="failed step|FAILED status"):
        run_visibility_scan(
            journey=failed_journey,
            target_brand=target,
            competitor_brands=comps,
            repository=mock_repo,
        )
    assert mock_repo.save_bundle.call_count == 0

    # Blank question
    blank_journey = _make_journey_fixture(question="   ")
    with pytest.raises(IncompleteJourneyError, match="non-blank question"):
        run_visibility_scan(
            journey=blank_journey,
            target_brand=target,
            competitor_brands=comps,
            repository=mock_repo,
        )
    assert mock_repo.save_bundle.call_count == 0


def test_runner_rejects_invalid_scan_state_before_persistence() -> None:
    """4. Verify invalid scan state is rejected before persistence."""
    target, comps, project, prompt = _make_profiles()
    journey = _make_journey_fixture()
    mock_repo = MagicMock()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    # FAILED scan status
    failed_scan = VisibilityScan(
        scan_id="scan_failed",
        batch_id="batch_01",
        project_id="proj_austin",
        brand_id="target_brand",
        brand_name_snapshot="Target Coffee",
        prompt_id="prompt_1",
        prompt_text_snapshot="best coffee",
        model_name="gemini-2.5-flash",
        started_at=now,
        completed_at=now,
        status=ScanStatus.FAILED,
        error_message="Execution timeout",
    )
    with pytest.raises(InconsistentScanError, match="FAILED status"):
        run_visibility_scan(
            journey=journey,
            target_brand=target,
            competitor_brands=comps,
            repository=mock_repo,
            scan=failed_scan,
        )
    assert mock_repo.save_bundle.call_count == 0

    # Mismatched brand_id in scan
    mismatched_scan = VisibilityScan(
        scan_id="scan_mismatch",
        batch_id="batch_01",
        project_id="proj_austin",
        brand_id="different_brand",
        brand_name_snapshot="Target Coffee",
        prompt_id="prompt_1",
        prompt_text_snapshot="best coffee",
        model_name="gemini-2.5-flash",
        started_at=now,
        completed_at=now,
        status=ScanStatus.COMPLETED,
    )
    with pytest.raises(InconsistentScanError, match="does not match target_brand.brand_id"):
        run_visibility_scan(
            journey=journey,
            target_brand=target,
            competitor_brands=comps,
            repository=mock_repo,
            scan=mismatched_scan,
        )
    assert mock_repo.save_bundle.call_count == 0


def test_runner_rejects_inconsistent_project_and_prompt_inputs() -> None:
    """5. Verify project, prompt, and brand inconsistencies are rejected before persistence."""
    target, comps, project, prompt = _make_profiles()
    journey = _make_journey_fixture()
    mock_repo = MagicMock()

    # Project target brand mismatch
    bad_project = VisibilityProject(
        project_id="proj_bad",
        name="Bad Proj",
        target_brand_id="other_brand",
        competitor_brand_ids=["comp_brand"],
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(InconsistentScanError, match="does not match target_brand.brand_id"):
        run_visibility_scan(
            journey=journey,
            target_brand=target,
            competitor_brands=comps,
            repository=mock_repo,
            project=bad_project,
        )
    assert mock_repo.save_bundle.call_count == 0

    # Competitor not configured in project
    extra_comp = BrandProfile(brand_id="extra_comp", name="Extra Coffee")
    with pytest.raises(InconsistentScanError, match="is not configured in project"):
        run_visibility_scan(
            journey=journey,
            target_brand=target,
            competitor_brands=[comps[0], extra_comp],
            repository=mock_repo,
            project=project,
        )
    assert mock_repo.save_bundle.call_count == 0

    # Disabled prompt
    disabled_prompt = PromptDefinition(
        prompt_id="prompt_disabled",
        prompt_text="test prompt",
        category="coffee",
        enabled=False,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(InconsistentScanError, match="is disabled"):
        run_visibility_scan(
            journey=journey,
            target_brand=target,
            competitor_brands=comps,
            repository=mock_repo,
            prompt=disabled_prompt,
        )
    assert mock_repo.save_bundle.call_count == 0

    # Target brand in competitor list
    with pytest.raises(InconsistentScanError, match="must not appear in competitor_brands"):
        run_visibility_scan(
            journey=journey,
            target_brand=target,
            competitor_brands=[target],
            repository=mock_repo,
        )
    assert mock_repo.save_bundle.call_count == 0


def test_extractor_failure_causes_zero_repository_saves() -> None:
    """6. Verify that an extractor failure aborts cleanly with 0 repository saves."""
    target, comps, project, prompt = _make_profiles()
    journey = _make_journey_fixture()
    mock_repo = MagicMock()

    with patch(
        "ai_search_journey.visibility.runner.extract_visibility_scan_bundle",
        side_effect=AmbiguousBrandMatchError("Multiple brands matched place_id"),
    ):
        with pytest.raises(AmbiguousBrandMatchError, match="Multiple brands matched"):
            run_visibility_scan(
                journey=journey,
                target_brand=target,
                competitor_brands=comps,
                repository=mock_repo,
                project=project,
                prompt=prompt,
            )

    assert mock_repo.save_bundle.call_count == 0


def test_runner_is_deterministic_using_fixture_data() -> None:
    """7. Verify runner execution is fully deterministic given identical inputs."""
    target, comps, project, prompt = _make_profiles()
    journey = _make_journey_fixture()
    t_fixed = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    repo1 = InMemoryVisibilityRepository()
    repo2 = InMemoryVisibilityRepository()

    res1 = run_visibility_scan(
        journey=journey,
        target_brand=target,
        competitor_brands=comps,
        repository=repo1,
        project=project,
        prompt=prompt,
        scan_id="scan_fixed_001",
        started_at=t_fixed,
        completed_at=t_fixed,
    )
    res2 = run_visibility_scan(
        journey=journey,
        target_brand=target,
        competitor_brands=comps,
        repository=repo2,
        project=project,
        prompt=prompt,
        scan_id="scan_fixed_001",
        started_at=t_fixed,
        completed_at=t_fixed,
    )

    b1 = res1.bundle
    b2 = res2.bundle
    assert b1.scan.scan_id == b2.scan.scan_id
    assert len(b1.brand_observations) == len(b2.brand_observations)
    assert len(b1.fanout_observations) == len(b2.fanout_observations)
    assert len(b1.citations) == len(b2.citations)

    # Compare brand observation values
    for o1, o2 in zip(b1.brand_observations, b2.brand_observations, strict=True):
        assert o1.brand_id == o2.brand_id
        assert o1.mentioned == o2.mentioned
        assert o1.recommended == o2.recommended
        assert o1.recommendation_position == o2.recommendation_position


def test_runner_transitions_pending_or_running_scan_to_completed() -> None:
    """8. Verify runner transitions PENDING or RUNNING scans to COMPLETED."""
    target, comps, project, prompt = _make_profiles()
    journey = _make_journey_fixture()
    repo = InMemoryVisibilityRepository()
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    completed_time = datetime(2026, 1, 1, 12, 0, 5, tzinfo=timezone.utc)

    pending_scan = VisibilityScan(
        scan_id="scan_pending_01",
        batch_id="batch_01",
        project_id="proj_austin",
        brand_id="target_brand",
        brand_name_snapshot="Target Coffee",
        prompt_id="prompt_1",
        prompt_text_snapshot="best coffee",
        model_name="gemini-2.5-flash",
        started_at=now,
        status=ScanStatus.PENDING,
    )

    result = run_visibility_scan(
        journey=journey,
        target_brand=target,
        competitor_brands=comps,
        repository=repo,
        scan=pending_scan,
        completed_at=completed_time,
    )

    assert result.scan.status == ScanStatus.COMPLETED
    assert result.scan.completed_at == completed_time
    assert result.scan.duration_seconds == 5.0
