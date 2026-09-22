"""Unit tests for in-memory visibility scan repository (V3 Milestone 3)."""

from datetime import datetime, timezone

import pytest

from ai_search_journey.visibility.models import (
    BrandObservation,
    BrandRole,
    CitationObservation,
    FanoutObservation,
    ScanStatus,
    VisibilityScan,
    VisibilityScanBundle,
)
from ai_search_journey.visibility.repository import (
    DuplicateScanError,
    InMemoryVisibilityRepository,
    InvalidRepositoryFilterError,
    VisibilityRepository,
)

# ======================================================================
# Helpers
# ======================================================================


def _make_scan(
    scan_id: str = "scan_001",
    started_at: datetime | None = None,
    status: ScanStatus = ScanStatus.COMPLETED,
    project_id: str = "proj_001",
    brand_id: str = "brand_target",
    prompt_id: str = "prompt_001",
    batch_id: str = "batch_001",
    error_message: str | None = None,
) -> VisibilityScan:
    t = started_at or datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    completed_at = t if status in (ScanStatus.COMPLETED, ScanStatus.FAILED) else None
    err_msg = error_message or ("Execution failed" if status == ScanStatus.FAILED else None)
    return VisibilityScan(
        scan_id=scan_id,
        batch_id=batch_id,
        project_id=project_id,
        brand_id=brand_id,
        brand_name_snapshot="Target Brand",
        brand_domain_snapshot="target.com",
        prompt_id=prompt_id,
        prompt_text_snapshot="best artisan coffee",
        model_name="gemini-2.5-flash",
        started_at=t,
        completed_at=completed_at,
        status=status,
        error_message=err_msg,
    )


def _make_brand_obs(
    scan_id: str = "scan_001",
    brand_id: str = "brand_target",
    role: BrandRole = BrandRole.TARGET,
    mentioned: bool = False,
    mention_count: int = 0,
    first_mention_position: int | None = None,
    retrieved: bool = False,
    best_retrieval_position: int | None = None,
    recommended: bool = False,
    recommendation_position: int | None = None,
    cited: bool = False,
    citation_urls: list[str] | None = None,
    citation_domains: list[str] | None = None,
) -> BrandObservation:
    if mentioned and mention_count == 0:
        mention_count = 1
    if mentioned and first_mention_position is None:
        first_mention_position = 10
    if not mentioned:
        mention_count = 0
        first_mention_position = None

    if retrieved and best_retrieval_position is None:
        best_retrieval_position = 1
    if not retrieved:
        best_retrieval_position = None

    if recommended and recommendation_position is None:
        recommendation_position = 1
    if not recommended:
        recommendation_position = None

    urls = citation_urls or (["https://target.com"] if cited else [])
    domains = citation_domains or (["target.com"] if cited else [])

    return BrandObservation(
        scan_id=scan_id,
        brand_id=brand_id,
        role=role,
        mentioned=mentioned,
        mention_count=mention_count,
        first_mention_position=first_mention_position,
        retrieved=retrieved,
        best_retrieval_position=best_retrieval_position,
        recommended=recommended,
        recommendation_position=recommendation_position,
        cited=cited,
        citation_urls=urls,
        citation_domains=domains,
    )


def _make_bundle(
    scan: VisibilityScan,
    brand_observations: list[BrandObservation] | None = None,
    fanout_observations: list[FanoutObservation] | None = None,
    citations: list[CitationObservation] | None = None,
) -> VisibilityScanBundle:
    if brand_observations is None:
        brand_observations = [_make_brand_obs(scan_id=scan.scan_id, brand_id=scan.brand_id)]
    return VisibilityScanBundle(
        scan=scan,
        brand_observations=brand_observations,
        fanout_observations=fanout_observations or [],
        citations=citations or [],
    )


# ======================================================================
# Repository Tests (Requirements 1-25)
# ======================================================================


def test_save_and_retrieve() -> None:
    """1. Save a bundle and retrieve it by scan_id."""
    repo = InMemoryVisibilityRepository()
    bundle = _make_bundle(_make_scan("scan_101"))

    repo.save_bundle(bundle)
    retrieved = repo.get_bundle("scan_101")

    assert retrieved is not None
    assert retrieved.scan.scan_id == "scan_101"
    assert retrieved.scan.project_id == "proj_001"
    assert len(retrieved.brand_observations) == 1
    assert isinstance(repo, VisibilityRepository)


def test_missing_scan_returns_none() -> None:
    """2. get_bundle returns None for nonexistent scan_id."""
    repo = InMemoryVisibilityRepository()
    assert repo.get_bundle("nonexistent_id") is None
    assert repo.get_bundle("") is None


def test_exact_duplicate_save_is_idempotent() -> None:
    """3. Saving the exact same bundle again is a no-op."""
    repo = InMemoryVisibilityRepository()
    bundle = _make_bundle(_make_scan("scan_dup"))

    repo.save_bundle(bundle)
    repo.save_bundle(bundle)

    bundles = repo.list_bundles()
    assert len(bundles) == 1
    assert bundles[0].scan.scan_id == "scan_dup"


def test_conflicting_duplicate_raises_duplicate_scan_error() -> None:
    """4. Saving a conflicting bundle under an existing scan_id raises DuplicateScanError."""
    repo = InMemoryVisibilityRepository()
    b1 = _make_bundle(_make_scan("scan_conflict", prompt_id="p1"))
    b2 = _make_bundle(_make_scan("scan_conflict", prompt_id="p2"))

    repo.save_bundle(b1)
    with pytest.raises(DuplicateScanError, match="Conflicting scan bundle already exists"):
        repo.save_bundle(b2)


def test_defensive_copy_on_save() -> None:
    """5. Mutating input bundle after save does not affect repository storage."""
    repo = InMemoryVisibilityRepository()
    bundle = _make_bundle(_make_scan("scan_copy_save"))
    repo.save_bundle(bundle)

    # Mutate caller bundle
    bundle.scan.prompt_id = "mutated_prompt"
    bundle.brand_observations[0].mentioned = True
    bundle.brand_observations[0].mention_count = 50

    stored = repo.get_bundle("scan_copy_save")
    assert stored is not None
    assert stored.scan.prompt_id == "prompt_001"
    assert stored.brand_observations[0].mentioned is False
    assert stored.brand_observations[0].mention_count == 0


def test_defensive_copy_on_retrieval() -> None:
    """6. Mutating retrieved bundle does not affect repository storage."""
    repo = InMemoryVisibilityRepository()
    bundle = _make_bundle(_make_scan("scan_copy_read"))
    repo.save_bundle(bundle)

    first = repo.get_bundle("scan_copy_read")
    assert first is not None
    first.scan.prompt_id = "mutated_read"

    second = repo.get_bundle("scan_copy_read")
    assert second is not None
    assert second.scan.prompt_id == "prompt_001"


def test_independent_repository_instances() -> None:
    """7. Each repository instance has isolated state."""
    repo1 = InMemoryVisibilityRepository()
    repo2 = InMemoryVisibilityRepository()

    bundle = _make_bundle(_make_scan("scan_isolated"))
    repo1.save_bundle(bundle)

    assert repo1.get_bundle("scan_isolated") is not None
    assert repo2.get_bundle("scan_isolated") is None
    assert len(repo2.list_bundles()) == 0


def test_deterministic_order() -> None:
    """8. list_bundles sorts chronologically by started_at ascending."""
    repo = InMemoryVisibilityRepository()
    t1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 1, 3, 10, 0, 0, tzinfo=timezone.utc)

    # Save out of order
    repo.save_bundle(_make_bundle(_make_scan("s3", started_at=t3)))
    repo.save_bundle(_make_bundle(_make_scan("s1", started_at=t1)))
    repo.save_bundle(_make_bundle(_make_scan("s2", started_at=t2)))

    results = repo.list_bundles()
    assert [b.scan.scan_id for b in results] == ["s1", "s2", "s3"]


def test_scan_id_tie_breaker() -> None:
    """9. Scans with identical started_at break ties by scan_id ascending."""
    repo = InMemoryVisibilityRepository()
    t_shared = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    # Save in reverse order of scan_id
    repo.save_bundle(_make_bundle(_make_scan("scan_z", started_at=t_shared)))
    repo.save_bundle(_make_bundle(_make_scan("scan_a", started_at=t_shared)))
    repo.save_bundle(_make_bundle(_make_scan("scan_m", started_at=t_shared)))

    results = repo.list_bundles()
    assert [b.scan.scan_id for b in results] == ["scan_a", "scan_m", "scan_z"]


def test_project_filter() -> None:
    """10. Filter by project_id matches scan.project_id."""
    repo = InMemoryVisibilityRepository()
    repo.save_bundle(_make_bundle(_make_scan("s1", project_id="proj_alpha")))
    repo.save_bundle(_make_bundle(_make_scan("s2", project_id="proj_beta")))
    repo.save_bundle(_make_bundle(_make_scan("s3", project_id="proj_alpha")))

    alpha_bundles = repo.list_bundles(project_id="proj_alpha")
    assert [b.scan.scan_id for b in alpha_bundles] == ["s1", "s3"]


def test_brand_filter() -> None:
    """11. Filter by brand_id returns bundles containing that BrandObservation."""
    repo = InMemoryVisibilityRepository()

    # Bundle 1 tracks target and competitor
    b1 = _make_bundle(
        _make_scan("s1"),
        [
            _make_brand_obs("s1", "brand_target", role=BrandRole.TARGET),
            _make_brand_obs("s1", "brand_comp1", role=BrandRole.COMPETITOR),
        ],
    )
    # Bundle 2 tracks other_target and comp2
    b2 = _make_bundle(
        _make_scan("s2", brand_id="other_target"),
        [
            _make_brand_obs("s2", "other_target", role=BrandRole.TARGET),
            _make_brand_obs("s2", "brand_comp2", role=BrandRole.COMPETITOR),
        ],
    )
    repo.save_bundle(b1)
    repo.save_bundle(b2)

    assert len(repo.list_bundles(brand_id="brand_target")) == 1
    assert repo.list_bundles(brand_id="brand_target")[0].scan.scan_id == "s1"
    assert len(repo.list_bundles(brand_id="brand_comp1")) == 1
    assert repo.list_bundles(brand_id="brand_comp1")[0].scan.scan_id == "s1"
    assert len(repo.list_bundles(brand_id="brand_comp2")) == 1
    assert repo.list_bundles(brand_id="brand_comp2")[0].scan.scan_id == "s2"
    assert len(repo.list_bundles(brand_id="nonexistent")) == 0


def test_prompt_filter() -> None:
    """12. Filter by prompt_id matches scan.prompt_id."""
    repo = InMemoryVisibilityRepository()
    repo.save_bundle(_make_bundle(_make_scan("s1", prompt_id="p1")))
    repo.save_bundle(_make_bundle(_make_scan("s2", prompt_id="p2")))
    repo.save_bundle(_make_bundle(_make_scan("s3", prompt_id="p1")))

    results = repo.list_bundles(prompt_id="p1")
    assert [b.scan.scan_id for b in results] == ["s1", "s3"]


def test_batch_filter() -> None:
    """13. Filter by batch_id matches scan.batch_id."""
    repo = InMemoryVisibilityRepository()
    repo.save_bundle(_make_bundle(_make_scan("s1", batch_id="b1")))
    repo.save_bundle(_make_bundle(_make_scan("s2", batch_id="b2")))
    repo.save_bundle(_make_bundle(_make_scan("s3", batch_id="b1")))

    results = repo.list_bundles(batch_id="b1")
    assert [b.scan.scan_id for b in results] == ["s1", "s3"]


def test_inclusive_start_filter() -> None:
    """14. start_time filter is inclusive (start_time <= scan.started_at)."""
    repo = InMemoryVisibilityRepository()
    t1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 1, 3, 10, 0, 0, tzinfo=timezone.utc)

    repo.save_bundle(_make_bundle(_make_scan("s1", started_at=t1)))
    repo.save_bundle(_make_bundle(_make_scan("s2", started_at=t2)))
    repo.save_bundle(_make_bundle(_make_scan("s3", started_at=t3)))

    results = repo.list_bundles(start_time=t2)
    assert [b.scan.scan_id for b in results] == ["s2", "s3"]


def test_inclusive_end_filter() -> None:
    """15. end_time filter is inclusive (scan.started_at <= end_time)."""
    repo = InMemoryVisibilityRepository()
    t1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 1, 3, 10, 0, 0, tzinfo=timezone.utc)

    repo.save_bundle(_make_bundle(_make_scan("s1", started_at=t1)))
    repo.save_bundle(_make_bundle(_make_scan("s2", started_at=t2)))
    repo.save_bundle(_make_bundle(_make_scan("s3", started_at=t3)))

    results = repo.list_bundles(end_time=t2)
    assert [b.scan.scan_id for b in results] == ["s1", "s2"]


def test_combined_filters_use_and() -> None:
    """16. Multiple filters combine with logical AND."""
    repo = InMemoryVisibilityRepository()
    t1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 1, 3, 10, 0, 0, tzinfo=timezone.utc)

    repo.save_bundle(
        _make_bundle(_make_scan("s1", project_id="pA", prompt_id="pr1", started_at=t1))
    )
    repo.save_bundle(
        _make_bundle(_make_scan("s2", project_id="pA", prompt_id="pr2", started_at=t2))
    )
    repo.save_bundle(
        _make_bundle(_make_scan("s3", project_id="pA", prompt_id="pr1", started_at=t3))
    )
    repo.save_bundle(
        _make_bundle(_make_scan("s4", project_id="pB", prompt_id="pr1", started_at=t2))
    )

    results = repo.list_bundles(project_id="pA", prompt_id="pr1", start_time=t2)
    assert [b.scan.scan_id for b in results] == ["s3"]


def test_naive_datetime_rejected() -> None:
    """17. Naive datetimes raise InvalidRepositoryFilterError."""
    repo = InMemoryVisibilityRepository()
    naive = datetime(2026, 1, 1, 12, 0, 0)

    with pytest.raises(InvalidRepositoryFilterError, match="start_time must be timezone-aware"):
        repo.list_bundles(start_time=naive)

    with pytest.raises(InvalidRepositoryFilterError, match="end_time must be timezone-aware"):
        repo.list_bundles(end_time=naive)

    with pytest.raises(InvalidRepositoryFilterError, match="start_time must be timezone-aware"):
        repo.get_metrics("brand_target", start_time=naive)

    with pytest.raises(InvalidRepositoryFilterError, match="end_time must be timezone-aware"):
        repo.get_trend("brand_target", end_time=naive)

    with pytest.raises(InvalidRepositoryFilterError, match="start_time must be timezone-aware"):
        repo.get_competitor_comparison(["brand_target"], start_time=naive)


def test_start_after_end_rejected() -> None:
    """18. start_time > end_time raises InvalidRepositoryFilterError."""
    repo = InMemoryVisibilityRepository()
    t1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 2, 10, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(
        InvalidRepositoryFilterError, match="start_time .* cannot be later than end_time"
    ):
        repo.list_bundles(start_time=t2, end_time=t1)


def test_valid_limit() -> None:
    """19. Valid limit returns only the first N ordered bundles."""
    repo = InMemoryVisibilityRepository()
    for i in range(5):
        t = datetime(2026, 1, i + 1, 10, 0, 0, tzinfo=timezone.utc)
        repo.save_bundle(_make_bundle(_make_scan(f"s{i}", started_at=t)))

    results = repo.list_bundles(limit=2)
    assert len(results) == 2
    assert [b.scan.scan_id for b in results] == ["s0", "s1"]


def test_zero_negative_limit_rejected() -> None:
    """20. Limit <= 0 raises InvalidRepositoryFilterError."""
    repo = InMemoryVisibilityRepository()

    with pytest.raises(InvalidRepositoryFilterError, match="limit must be >= 1"):
        repo.list_bundles(limit=0)

    with pytest.raises(InvalidRepositoryFilterError, match="limit must be >= 1"):
        repo.list_bundles(limit=-1)


def test_metrics_method_reuses_filtered_bundles() -> None:
    """21. get_metrics passes filtered bundles to pure metric calculation."""
    repo = InMemoryVisibilityRepository()
    # prompt 1: mentioned=True
    b1 = _make_bundle(
        _make_scan("s1", prompt_id="p1"),
        [_make_brand_obs("s1", "brand_target", mentioned=True)],
    )
    # prompt 2: mentioned=False
    b2 = _make_bundle(
        _make_scan("s2", prompt_id="p2"),
        [_make_brand_obs("s2", "brand_target", mentioned=False)],
    )
    repo.save_bundle(b1)
    repo.save_bundle(b2)

    # Filtered by prompt_id="p1" -> only b1 -> mention_rate == 1.0
    metrics_p1 = repo.get_metrics("brand_target", prompt_id="p1")
    assert metrics_p1.total_scans == 1
    assert metrics_p1.mention_rate == 1.0

    # Filtered by prompt_id="p2" -> only b2 -> mention_rate == 0.0
    metrics_p2 = repo.get_metrics("brand_target", prompt_id="p2")
    assert metrics_p2.total_scans == 1
    assert metrics_p2.mention_rate == 0.0

    # Unfiltered -> both -> mention_rate == 0.5
    metrics_all = repo.get_metrics("brand_target")
    assert metrics_all.total_scans == 2
    assert metrics_all.mention_rate == 0.5


def test_competitor_comparison() -> None:
    """22. get_competitor_comparison computes metrics for all requested brands in order."""
    repo = InMemoryVisibilityRepository()
    s1 = _make_scan("s1")
    t1 = _make_brand_obs("s1", "brand_b", role=BrandRole.TARGET, mentioned=True)
    c1 = _make_brand_obs("s1", "brand_a", role=BrandRole.COMPETITOR, mentioned=False)
    repo.save_bundle(_make_bundle(s1, [t1, c1]))

    comparison = repo.get_competitor_comparison(["brand_a", "brand_b"])
    assert len(comparison) == 2
    assert comparison[0].brand_id == "brand_a"
    assert comparison[0].mention_rate == 0.0
    assert comparison[1].brand_id == "brand_b"
    assert comparison[1].mention_rate == 1.0


def test_trend_retrieval() -> None:
    """23. get_trend retrieves chronological trend points for brand."""
    repo = InMemoryVisibilityRepository()
    t1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 2, 10, 0, 0, tzinfo=timezone.utc)

    repo.save_bundle(
        _make_bundle(
            _make_scan("s2", started_at=t2),
            [_make_brand_obs("s2", "brand_target", mentioned=True)],
        )
    )
    repo.save_bundle(
        _make_bundle(
            _make_scan("s1", started_at=t1),
            [_make_brand_obs("s1", "brand_target", mentioned=False)],
        )
    )

    trend = repo.get_trend("brand_target")
    assert len(trend) == 2
    assert [p.scan_id for p in trend] == ["s1", "s2"]
    assert trend[0].mentioned is False
    assert trend[1].mentioned is True


def test_completed_scan_required() -> None:
    """24. save_bundle requires scan.status to be COMPLETED and scan_id non-blank."""
    repo = InMemoryVisibilityRepository()

    pending_scan = _make_scan("s_pending", status=ScanStatus.PENDING)
    with pytest.raises(ValueError, match="Only COMPLETED scans can be saved"):
        repo.save_bundle(_make_bundle(pending_scan))

    failed_scan = _make_scan("s_failed", status=ScanStatus.FAILED)
    with pytest.raises(ValueError, match="Only COMPLETED scans can be saved"):
        repo.save_bundle(_make_bundle(failed_scan))


def test_no_file_network_io() -> None:
    """25. InMemoryVisibilityRepository performs no filesystem or network I/O."""
    repo = InMemoryVisibilityRepository()
    bundle = _make_bundle(_make_scan("s1"))
    repo.save_bundle(bundle)

    # Repository must only use an internal in-memory dictionary
    assert hasattr(repo, "_bundles")
    assert isinstance(repo._bundles, dict)
    assert len(repo._bundles) == 1
    # Verify no persistent files or connections were attached
    assert not hasattr(repo, "client")
    assert not hasattr(repo, "connection")
    assert not hasattr(repo, "filepath")
