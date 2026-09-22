"""Unit tests for deterministic AI visibility metrics and trend calculations (V3 Milestone 3)."""

from datetime import datetime, timezone

import pytest

from ai_search_journey.visibility.metrics import (
    VisibilityTrendPoint,
    calculate_competitor_comparison,
    calculate_visibility_metrics,
    calculate_visibility_trend,
)
from ai_search_journey.visibility.models import (
    BrandObservation,
    BrandRole,
    CitationObservation,
    FanoutObservation,
    ScanStatus,
    VisibilityScan,
    VisibilityScanBundle,
)

# ======================================================================
# Fixtures and Helpers
# ======================================================================


def _make_scan(
    scan_id: str = "scan_001",
    started_at: datetime | None = None,
    status: ScanStatus = ScanStatus.COMPLETED,
    project_id: str = "proj_001",
    brand_id: str = "brand_target",
    prompt_id: str = "prompt_001",
    batch_id: str = "batch_001",
) -> VisibilityScan:
    t = started_at or datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
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
        completed_at=t,
        status=status,
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
    # Maintain model invariants
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
    brand_observations: list[BrandObservation],
    fanout_observations: list[FanoutObservation] | None = None,
    citations: list[CitationObservation] | None = None,
) -> VisibilityScanBundle:
    return VisibilityScanBundle(
        scan=scan,
        brand_observations=brand_observations,
        fanout_observations=fanout_observations or [],
        citations=citations or [],
    )


# ======================================================================
# Metric Tests (Requirements 1-18)
# ======================================================================


def test_zero_scans() -> None:
    """1. Zero scans returns zeroed metrics and None average position."""
    metrics = calculate_visibility_metrics([], "brand_target")
    assert metrics.brand_id == "brand_target"
    assert metrics.total_scans == 0
    assert metrics.mention_rate == 0.0
    assert metrics.recommendation_rate == 0.0
    assert metrics.citation_rate == 0.0
    assert metrics.average_recommendation_position is None
    assert metrics.share_of_voice == 0.0
    assert metrics.fanout_coverage == 0.0


def test_one_tracked_scan() -> None:
    """2. One tracked scan calculates rates with denominator of 1."""
    scan = _make_scan("s1")
    obs = _make_brand_obs(
        "s1",
        "brand_target",
        role=BrandRole.TARGET,
        mentioned=True,
        mention_count=2,
        first_mention_position=5,
        retrieved=True,
        best_retrieval_position=1,
        recommended=True,
        recommendation_position=2,
        cited=True,
    )
    fanout = FanoutObservation(
        scan_id="s1",
        task_id="t1",
        query_text="craft coffee",
        tool="google_places",
        brand_id="brand_target",
        brand_found=True,
        position_in_task=1,
    )
    bundle = _make_bundle(scan, [obs], fanout_observations=[fanout])

    metrics = calculate_visibility_metrics([bundle], "brand_target")
    assert metrics.total_scans == 1
    assert metrics.mention_rate == 1.0
    assert metrics.recommendation_rate == 1.0
    assert metrics.citation_rate == 1.0
    assert metrics.average_recommendation_position == 2.0
    assert metrics.share_of_voice == 1.0
    assert metrics.fanout_coverage == 1.0


def test_brand_absent_from_bundle_excluded_from_denominator() -> None:
    """3. Brand absent from a bundle does not enter its denominator."""
    # Bundle 1 tracks target and competitor
    b1_scan = _make_scan("s1")
    b1_target = _make_brand_obs("s1", "brand_target", role=BrandRole.TARGET, mentioned=True)
    b1_comp = _make_brand_obs("s1", "brand_comp", role=BrandRole.COMPETITOR, mentioned=False)
    bundle1 = _make_bundle(b1_scan, [b1_target, b1_comp])

    # Bundle 2 tracks target and competitor
    b2_scan = _make_scan("s2")
    b2_target = _make_brand_obs("s2", "brand_target", role=BrandRole.TARGET, mentioned=False)
    b2_comp = _make_brand_obs("s2", "brand_comp", role=BrandRole.COMPETITOR, mentioned=True)
    bundle2 = _make_bundle(b2_scan, [b2_target, b2_comp])

    # Bundle 3 tracks only competitor (as TARGET) and a third brand, does NOT track brand_target
    b3_scan = _make_scan("s3", brand_id="brand_comp")
    b3_comp = _make_brand_obs("s3", "brand_comp", role=BrandRole.TARGET, mentioned=True)
    b3_other = _make_brand_obs("s3", "brand_other", role=BrandRole.COMPETITOR, mentioned=False)
    bundle3 = _make_bundle(b3_scan, [b3_comp, b3_other])

    # For brand_target, only bundle1 and bundle2 are tracked
    metrics = calculate_visibility_metrics([bundle1, bundle2, bundle3], "brand_target")
    assert metrics.total_scans == 2
    assert metrics.mention_rate == 0.5  # 1 out of 2


def test_mention_rate() -> None:
    """4. Mention rate equals mentioned scans divided by tracked scans."""
    bundles = []
    for i in range(4):
        sid = f"s{i}"
        scan = _make_scan(sid)
        mentioned = i < 3  # 3 True, 1 False
        obs = _make_brand_obs(sid, "brand_target", mentioned=mentioned)
        bundles.append(_make_bundle(scan, [obs]))

    metrics = calculate_visibility_metrics(bundles, "brand_target")
    assert metrics.total_scans == 4
    assert metrics.mention_rate == 3 / 4


def test_recommendation_rate() -> None:
    """5. Recommendation rate equals recommended scans divided by tracked scans."""
    bundles = []
    for i in range(4):
        sid = f"s{i}"
        scan = _make_scan(sid)
        recommended = i < 2  # 2 True, 2 False
        obs = _make_brand_obs(
            sid,
            "brand_target",
            recommended=recommended,
            recommendation_position=1 if recommended else None,
        )
        bundles.append(_make_bundle(scan, [obs]))

    metrics = calculate_visibility_metrics(bundles, "brand_target")
    assert metrics.total_scans == 4
    assert metrics.recommendation_rate == 2 / 4


def test_owned_citation_rate() -> None:
    """6. Citation rate reflects owned-domain citations across tracked scans."""
    bundles = []
    for i in range(4):
        sid = f"s{i}"
        scan = _make_scan(sid)
        cited = i == 0  # 1 True, 3 False
        obs = _make_brand_obs(sid, "brand_target", cited=cited)
        bundles.append(_make_bundle(scan, [obs]))

    metrics = calculate_visibility_metrics(bundles, "brand_target")
    assert metrics.total_scans == 4
    assert metrics.citation_rate == 1 / 4


def test_average_recommendation_position() -> None:
    """7. Average recommendation position averages positions across recommended scans."""
    positions = [1, 2, 6]
    bundles = []
    for i, pos in enumerate(positions):
        sid = f"s{i}"
        scan = _make_scan(sid)
        obs = _make_brand_obs(sid, "brand_target", recommended=True, recommendation_position=pos)
        bundles.append(_make_bundle(scan, [obs]))

    # Add a non-recommended scan
    s_unrec = _make_scan("s_unrec")
    obs_unrec = _make_brand_obs("s_unrec", "brand_target", recommended=False)
    bundles.append(_make_bundle(s_unrec, [obs_unrec]))

    metrics = calculate_visibility_metrics(bundles, "brand_target")
    assert metrics.total_scans == 4
    assert metrics.recommendation_rate == 3 / 4
    assert metrics.average_recommendation_position == (1 + 2 + 6) / 3 == 3.0


def test_never_recommended_returns_none() -> None:
    """8. Average recommendation position returns None when never recommended."""
    bundles = []
    for i in range(2):
        sid = f"s{i}"
        scan = _make_scan(sid)
        obs = _make_brand_obs(sid, "brand_target", recommended=False)
        bundles.append(_make_bundle(scan, [obs]))

    metrics = calculate_visibility_metrics(bundles, "brand_target")
    assert metrics.total_scans == 2
    assert metrics.recommendation_rate == 0.0
    assert metrics.average_recommendation_position is None


def test_share_of_voice_from_mention_counts() -> None:
    """9. Share of voice computed from brand mentions divided by total market mentions."""
    # Bundle 1: Target=3, Comp=7
    s1 = _make_scan("s1")
    t1 = _make_brand_obs(
        "s1", "brand_target", role=BrandRole.TARGET, mentioned=True, mention_count=3
    )
    c1 = _make_brand_obs(
        "s1", "brand_comp", role=BrandRole.COMPETITOR, mentioned=True, mention_count=7
    )
    b1 = _make_bundle(s1, [t1, c1])

    # Bundle 2: Target=1, Comp=9
    s2 = _make_scan("s2")
    t2 = _make_brand_obs(
        "s2", "brand_target", role=BrandRole.TARGET, mentioned=True, mention_count=1
    )
    c2 = _make_brand_obs(
        "s2", "brand_comp", role=BrandRole.COMPETITOR, mentioned=True, mention_count=9
    )
    b2 = _make_bundle(s2, [t2, c2])

    metrics = calculate_visibility_metrics([b1, b2], "brand_target")
    # Target mentions = 3 + 1 = 4
    # Total mentions = (3 + 7) + (1 + 9) = 20
    assert metrics.share_of_voice == 4 / 20 == 0.2


def test_zero_total_mentions_returns_zero_share() -> None:
    """10. Zero total mentions across market returns 0.0 share without ZeroDivisionError."""
    s1 = _make_scan("s1")
    t1 = _make_brand_obs(
        "s1", "brand_target", role=BrandRole.TARGET, mentioned=False, mention_count=0
    )
    c1 = _make_brand_obs(
        "s1", "brand_comp", role=BrandRole.COMPETITOR, mentioned=False, mention_count=0
    )
    b1 = _make_bundle(s1, [t1, c1])

    metrics = calculate_visibility_metrics([b1], "brand_target")
    assert metrics.share_of_voice == 0.0


def test_fanout_coverage() -> None:
    """11. Fan-out coverage calculates ratio of brand_found=True across brand fanouts."""
    scan = _make_scan("s1")
    obs = _make_brand_obs("s1", "brand_target")

    fanouts = [
        FanoutObservation(
            scan_id="s1",
            task_id=f"t{i}",
            query_text=f"q{i}",
            tool="google_places",
            brand_id="brand_target",
            brand_found=(i < 3),  # 3 found, 2 not found
            position_in_task=1 if i < 3 else None,
        )
        for i in range(5)
    ]
    # Also add a fanout observation for a competitor to ensure it's not mixed in
    comp_fanout = FanoutObservation(
        scan_id="s1",
        task_id="t_comp",
        query_text="comp query",
        tool="google_places",
        brand_id="brand_comp",
        brand_found=True,
        position_in_task=2,
    )
    bundle = _make_bundle(scan, [obs], fanout_observations=[*fanouts, comp_fanout])

    metrics = calculate_visibility_metrics([bundle], "brand_target")
    assert metrics.fanout_coverage == 3 / 5 == 0.6


def test_no_fanout_rows_returns_zero_coverage() -> None:
    """12. Zero fan-out observations for brand returns 0.0 coverage."""
    scan = _make_scan("s1")
    obs = _make_brand_obs("s1", "brand_target")
    bundle = _make_bundle(scan, [obs], fanout_observations=[])

    metrics = calculate_visibility_metrics([bundle], "brand_target")
    assert metrics.fanout_coverage == 0.0


def test_full_float_precision_retained() -> None:
    """13. Metric engine retains full float precision without artificial rounding."""
    bundles = []
    for i in range(3):
        sid = f"s{i}"
        scan = _make_scan(sid)
        mentioned = i == 0  # 1 out of 3
        obs = _make_brand_obs(sid, "brand_target", mentioned=mentioned)
        bundles.append(_make_bundle(scan, [obs]))

    metrics = calculate_visibility_metrics(bundles, "brand_target")
    assert metrics.mention_rate == 1 / 3
    assert metrics.mention_rate != 0.33
    assert metrics.mention_rate != 0.3333


def test_trend_ordering() -> None:
    """14. Trend points ordered by started_at ascending, then scan_id ascending."""
    t1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 1, 3, 10, 0, 0, tzinfo=timezone.utc)

    # Intentionally shuffle insertion order and include tie at t2
    b_t2_b = _make_bundle(
        _make_scan("scan_b", started_at=t2),
        [_make_brand_obs("scan_b", "brand_target", mentioned=True)],
    )
    b_t1_z = _make_bundle(
        _make_scan("scan_z", started_at=t1),
        [_make_brand_obs("scan_z", "brand_target", mentioned=False)],
    )
    b_t2_a = _make_bundle(
        _make_scan("scan_a", started_at=t2),
        [_make_brand_obs("scan_a", "brand_target", mentioned=True)],
    )
    b_t3_c = _make_bundle(
        _make_scan("scan_c", started_at=t3),
        [_make_brand_obs("scan_c", "brand_target", mentioned=True)],
    )

    trend = calculate_visibility_trend([b_t2_b, b_t1_z, b_t2_a, b_t3_c], "brand_target")
    assert len(trend) == 4
    assert [p.scan_id for p in trend] == ["scan_z", "scan_a", "scan_b", "scan_c"]
    assert trend[0].started_at == t1
    assert trend[1].started_at == t2
    assert trend[2].started_at == t2
    assert trend[3].started_at == t3
    assert isinstance(trend[0], VisibilityTrendPoint)


def test_competitor_comparison_preserves_supplied_id_order() -> None:
    """15. Competitor comparison preserves supplied brand_ids order exactly."""
    s1 = _make_scan("s1")
    t1 = _make_brand_obs("s1", "brand_c", role=BrandRole.TARGET, mentioned=True)
    c1 = _make_brand_obs("s1", "brand_a", role=BrandRole.COMPETITOR, mentioned=False)
    c2 = _make_brand_obs("s1", "brand_b", role=BrandRole.COMPETITOR, mentioned=True)
    bundle = _make_bundle(s1, [t1, c1, c2])

    supplied_order = ["brand_b", "brand_c", "brand_a"]
    comparison = calculate_competitor_comparison([bundle], supplied_order)

    assert len(comparison) == 3
    assert [m.brand_id for m in comparison] == supplied_order
    assert comparison[0].brand_id == "brand_b"
    assert comparison[1].brand_id == "brand_c"
    assert comparison[2].brand_id == "brand_a"


def test_blank_brand_id_rejected() -> None:
    """16. Blank brand IDs are rejected across metric functions."""
    bundle = _make_bundle(_make_scan("s1"), [_make_brand_obs("s1", "brand_target")])

    with pytest.raises(ValueError, match="brand_id cannot be blank"):
        calculate_visibility_metrics([bundle], "")

    with pytest.raises(ValueError, match="brand_id cannot be blank"):
        calculate_visibility_metrics([bundle], "   ")

    with pytest.raises(ValueError, match="brand_id cannot be blank"):
        calculate_visibility_trend([bundle], "")

    with pytest.raises(ValueError, match="brand_id cannot be blank"):
        calculate_visibility_trend([bundle], " \t ")

    with pytest.raises(ValueError, match="brand_id in brand_ids cannot be blank"):
        calculate_competitor_comparison([bundle], ["brand_target", ""])

    with pytest.raises(ValueError, match="brand_id in brand_ids cannot be blank"):
        calculate_competitor_comparison([bundle], ["   "])


def test_inputs_not_mutated() -> None:
    """17. Metric functions do not mutate bundles or observations."""
    s1 = _make_scan("s1")
    t1 = _make_brand_obs(
        "s1",
        "brand_target",
        role=BrandRole.TARGET,
        mentioned=True,
        mention_count=3,
        recommended=True,
        recommendation_position=1,
        cited=True,
    )
    bundle = _make_bundle(s1, [t1])
    original_dump = bundle.model_dump()

    _ = calculate_visibility_metrics([bundle], "brand_target")
    _ = calculate_visibility_trend([bundle], "brand_target")
    _ = calculate_competitor_comparison([bundle], ["brand_target"])

    assert bundle.model_dump() == original_dump


def test_third_party_citations_do_not_affect_citation_rate() -> None:
    """18. Third-party citations without matched brand ID do not count toward citation rate."""
    s1 = _make_scan("s1")
    # Brand itself was NOT cited (owned domain not cited)
    t1 = _make_brand_obs("s1", "brand_target", role=BrandRole.TARGET, cited=False)

    # Citation observations in bundle from external domain (yelp, wikipedia, etc.)
    cit1 = CitationObservation(
        scan_id="s1",
        url="https://en.wikipedia.org/wiki/Coffee",
        domain="wikipedia.org",
        source_type="gemini_grounding",
        matched_brand_ids=[],
    )
    cit2 = CitationObservation(
        scan_id="s1",
        url="https://www.yelp.com/biz/some-cafe",
        domain="yelp.com",
        source_type="gemini_grounding",
        matched_brand_ids=[],
    )

    bundle = _make_bundle(s1, [t1], citations=[cit1, cit2])

    metrics = calculate_visibility_metrics([bundle], "brand_target")
    assert metrics.citation_rate == 0.0
