"""Unit tests for AI Visibility (V3) domain models and enums."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ai_search_journey.models import ToolName
from ai_search_journey.visibility import (
    BrandObservation,
    BrandProfile,
    BrandRole,
    CitationObservation,
    FanoutObservation,
    PromptDefinition,
    ScanStatus,
    VisibilityMetrics,
    VisibilityProject,
    VisibilityScan,
    VisibilityScanBundle,
    normalize_domain,
)

# ======================================================================
# Fixtures and Helpers
# ======================================================================


@pytest.fixture
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_valid_scan(
    utc_now: datetime,
    scan_id: str = "scan_001",
    status: ScanStatus = ScanStatus.PENDING,
    completed_at: datetime | None = None,
    duration_seconds: float | None = None,
    error_message: str | None = None,
) -> VisibilityScan:
    return VisibilityScan(
        scan_id=scan_id,
        batch_id="batch_001",
        project_id="proj_001",
        brand_id="brand_target",
        brand_name_snapshot="Target Coffee",
        brand_domain_snapshot="targetcoffee.com",
        prompt_id="prompt_001",
        prompt_text_snapshot="best artisan coffee in Austin",
        model_name="gemini-2.5-flash",
        location_snapshot="Austin, TX",
        started_at=utc_now,
        completed_at=completed_at,
        status=status,
        duration_seconds=duration_seconds,
        error_message=error_message,
    )


# ======================================================================
# 1. Default Construction
# ======================================================================


def test_default_construction(utc_now: datetime) -> None:
    """Verify default fields are initialized correctly without mutable defaults."""
    # BrandProfile
    profile = BrandProfile(brand_id="b1", name="Brand")
    assert profile.domain is None
    assert profile.aliases == []
    assert profile.place_ids == []
    assert profile.domain_aliases == []

    # VisibilityProject
    project = VisibilityProject(
        project_id="p1", name="Austin Coffee", target_brand_id="b1", created_at=utc_now
    )
    assert project.competitor_brand_ids == []

    # PromptDefinition
    prompt = PromptDefinition(
        prompt_id="pr1",
        prompt_text="quiet coffee shops",
        category="coffee",
        created_at=utc_now,
    )
    assert prompt.reference_location is None
    assert prompt.enabled is True

    # VisibilityScan
    scan = _make_valid_scan(utc_now)
    assert scan.status == ScanStatus.PENDING
    assert scan.completed_at is None
    assert scan.duration_seconds is None
    assert scan.error_code is None
    assert scan.error_message is None

    # CitationObservation
    cit = CitationObservation(
        scan_id="s1",
        url="https://austinmonthly.com/coffee",
        domain="austinmonthly.com",
        source_type="web",
    )
    assert cit.matched_brand_ids == []

    # BrandObservation
    target_obs = BrandObservation(scan_id="s1", brand_id="b1", role=BrandRole.TARGET)
    assert target_obs.mentioned is False
    assert target_obs.mention_count == 0
    assert target_obs.first_mention_position is None
    assert target_obs.retrieved is False
    assert target_obs.best_retrieval_position is None
    assert target_obs.recommended is False
    assert target_obs.recommendation_position is None
    assert target_obs.cited is False
    assert target_obs.citation_urls == []
    assert target_obs.citation_domains == []

    # FanoutObservation
    fanout = FanoutObservation(
        scan_id="s1",
        task_id="t1",
        query_text="craft coffee Austin",
        tool="google_places",
        brand_id="b1",
    )
    assert fanout.brand_found is False
    assert fanout.position_in_task is None

    # VisibilityScanBundle
    bundle_scan = _make_valid_scan(utc_now, scan_id="s1")
    bundle = VisibilityScanBundle(scan=bundle_scan, brand_observations=[target_obs])
    assert bundle.fanout_observations == []
    assert bundle.citations == []


# ======================================================================
# 2. Serialization & Deserialization
# ======================================================================


def test_serialization_round_trip(utc_now: datetime) -> None:
    """Verify serialization to dict and JSON round-trips without data loss."""
    scan = _make_valid_scan(
        utc_now,
        scan_id="scan_100",
        status=ScanStatus.COMPLETED,
        completed_at=utc_now,
    )
    scan.duration_seconds = 4.25

    target_obs = BrandObservation(
        scan_id="scan_100",
        brand_id="brand_target",
        role=BrandRole.TARGET,
        mentioned=True,
        mention_count=3,
        first_mention_position=42,
        retrieved=True,
        best_retrieval_position=2,
        recommended=True,
        recommendation_position=1,
        cited=True,
        citation_urls=["https://targetcoffee.com"],
        citation_domains=["targetcoffee.com"],
    )

    cit = CitationObservation(
        scan_id="scan_100",
        url="https://targetcoffee.com",
        domain="targetcoffee.com",
        source_type="web",
        matched_brand_ids=["brand_target"],
    )

    fo = FanoutObservation(
        scan_id="scan_100",
        task_id="task_1",
        query_text="best coffee Austin",
        tool="google_places",
        brand_id="brand_target",
        brand_found=True,
        position_in_task=2,
    )

    bundle = VisibilityScanBundle(
        scan=scan,
        brand_observations=[target_obs],
        fanout_observations=[fo],
        citations=[cit],
    )

    # JSON round trip
    json_str = bundle.model_dump_json()
    reconstructed = VisibilityScanBundle.model_validate_json(json_str)

    assert reconstructed.scan.scan_id == "scan_100"
    assert reconstructed.scan.status == ScanStatus.COMPLETED
    assert reconstructed.scan.duration_seconds == 4.25
    assert len(reconstructed.brand_observations) == 1
    assert reconstructed.brand_observations[0].role == BrandRole.TARGET
    assert reconstructed.brand_observations[0].first_mention_position == 42
    assert reconstructed.citations[0].domain == "targetcoffee.com"
    assert reconstructed.fanout_observations[0].position_in_task == 2


# ======================================================================
# 3. Standard Enum Equality and Hashing
# ======================================================================


def test_standard_enum_equality_and_hashing() -> None:
    """Verify standard string Enum equality and hashing semantics."""
    assert BrandRole.TARGET == "target"
    assert BrandRole.COMPETITOR == "competitor"
    assert isinstance(BrandRole.TARGET, str)

    assert ScanStatus.PENDING == "pending"
    assert ScanStatus.RUNNING == "running"
    assert ScanStatus.COMPLETED == "completed"
    assert ScanStatus.FAILED == "failed"

    # Standard hashing in sets and dict keys
    role_set = {BrandRole.TARGET, BrandRole.COMPETITOR, BrandRole.TARGET}
    assert len(role_set) == 2

    status_dict = {ScanStatus.COMPLETED: 1, ScanStatus.PENDING: 0}
    assert status_dict[ScanStatus.COMPLETED] == 1


# ======================================================================
# 4. Blank Required Fields Rejected
# ======================================================================


def test_blank_required_fields_rejected(utc_now: datetime) -> None:
    """Verify all required ID, name, query, and category fields reject blank strings."""
    # BrandProfile
    with pytest.raises(ValidationError):
        BrandProfile(brand_id="  ", name="Brand")
    with pytest.raises(ValidationError):
        BrandProfile(brand_id="b1", name="")

    # VisibilityProject
    with pytest.raises(ValidationError):
        VisibilityProject(
            project_id=" ", name="Proj", target_brand_id="b1", created_at=utc_now
        )
    with pytest.raises(ValidationError):
        VisibilityProject(
            project_id="p1", name="", target_brand_id="b1", created_at=utc_now
        )
    with pytest.raises(ValidationError):
        VisibilityProject(
            project_id="p1", name="Proj", target_brand_id="   ", created_at=utc_now
        )

    # PromptDefinition
    with pytest.raises(ValidationError):
        PromptDefinition(
            prompt_id="", prompt_text="query", category="cat", created_at=utc_now
        )
    with pytest.raises(ValidationError):
        PromptDefinition(
            prompt_id="p", prompt_text="   ", category="cat", created_at=utc_now
        )
    with pytest.raises(ValidationError):
        PromptDefinition(
            prompt_id="p", prompt_text="query", category="", created_at=utc_now
        )

    # VisibilityScan
    with pytest.raises(ValidationError):
        VisibilityScan(
            scan_id="",
            batch_id="b",
            project_id="p",
            brand_id="b",
            brand_name_snapshot="n",
            prompt_id="pr",
            prompt_text_snapshot="q",
            model_name="m",
            started_at=utc_now,
        )

    # CitationObservation
    with pytest.raises(ValidationError):
        CitationObservation(
            scan_id="", url="http://a.com", domain="a.com", source_type="web"
        )
    with pytest.raises(ValidationError):
        CitationObservation(
            scan_id="s1", url=" ", domain="a.com", source_type="web"
        )
    with pytest.raises(ValidationError):
        CitationObservation(
            scan_id="s1", url="http://a.com", domain="a.com", source_type=""
        )

    # BrandObservation
    with pytest.raises(ValidationError):
        BrandObservation(scan_id="", brand_id="b1", role=BrandRole.TARGET)
    with pytest.raises(ValidationError):
        BrandObservation(scan_id="s1", brand_id="  ", role=BrandRole.TARGET)

    # FanoutObservation
    with pytest.raises(ValidationError):
        FanoutObservation(
            scan_id="", task_id="t1", query_text="q", tool="google_places", brand_id="b1"
        )
    with pytest.raises(ValidationError):
        FanoutObservation(
            scan_id="s1", task_id="", query_text="q", tool="google_places", brand_id="b1"
        )
    with pytest.raises(ValidationError):
        FanoutObservation(
            scan_id="s1", task_id="t1", query_text=" ", tool="google_places", brand_id="b1"
        )
    with pytest.raises(ValidationError):
        FanoutObservation(
            scan_id="s1", task_id="t1", query_text="q", tool="", brand_id="b1"
        )
    with pytest.raises(ValidationError):
        FanoutObservation(
            scan_id="s1", task_id="t1", query_text="q", tool="google_places", brand_id=""
        )

    # VisibilityMetrics
    with pytest.raises(ValidationError):
        VisibilityMetrics(
            brand_id="",
            total_scans=0,
            mention_rate=0.0,
            recommendation_rate=0.0,
            citation_rate=0.0,
            share_of_voice=0.0,
            fanout_coverage=0.0,
        )


# ======================================================================
# 5. Timezone-Aware Datetime Enforcement
# ======================================================================


def test_timezone_aware_datetime_enforcement() -> None:
    """Verify naive datetimes are rejected across all models requiring timestamps."""
    naive_dt = datetime(2026, 9, 22, 12, 0, 0)
    aware_dt = datetime(2026, 9, 22, 12, 0, 0, tzinfo=timezone.utc)

    # VisibilityProject
    with pytest.raises(ValidationError, match="timezone-aware"):
        VisibilityProject(
            project_id="p1", name="P", target_brand_id="b1", created_at=naive_dt
        )
    assert (
        VisibilityProject(
            project_id="p1", name="P", target_brand_id="b1", created_at=aware_dt
        ).created_at
        == aware_dt
    )

    # PromptDefinition
    with pytest.raises(ValidationError, match="timezone-aware"):
        PromptDefinition(
            prompt_id="p1",
            prompt_text="q",
            category="c",
            created_at=naive_dt,
        )

    # VisibilityScan started_at
    with pytest.raises(ValidationError, match="timezone-aware"):
        VisibilityScan(
            scan_id="s1",
            batch_id="b",
            project_id="p",
            brand_id="b",
            brand_name_snapshot="n",
            prompt_id="pr",
            prompt_text_snapshot="q",
            model_name="m",
            started_at=naive_dt,
        )

    # VisibilityScan completed_at
    with pytest.raises(ValidationError, match="timezone-aware"):
        VisibilityScan(
            scan_id="s1",
            batch_id="b",
            project_id="p",
            brand_id="b",
            brand_name_snapshot="n",
            prompt_id="pr",
            prompt_text_snapshot="q",
            model_name="m",
            started_at=aware_dt,
            completed_at=naive_dt,
            status=ScanStatus.COMPLETED,
        )


# ======================================================================
# 6. Domain Normalization
# ======================================================================


def test_domain_normalization() -> None:
    """Verify all domain normalization rules: lowercase, scheme, path, leading www, trailing dot."""
    assert (
        normalize_domain("HTTPS://WWW.Example.COM/path/to/page?q=1#frag")
        == "example.com"
    )
    assert normalize_domain("http://example.org.") == "example.org"
    assert normalize_domain("www.coffeeco.uk") == "coffeeco.uk"
    assert normalize_domain("coffee.com/about/") == "coffee.com"
    assert normalize_domain("user:pass@sub.domain.com:8080/path") == "sub.domain.com"
    assert normalize_domain("sub.brand.com...") == "sub.brand.com"
    assert normalize_domain(None) is None

    with pytest.raises(ValueError):
        normalize_domain("")
    with pytest.raises(ValueError):
        normalize_domain("   ")

    # In BrandProfile
    p = BrandProfile(
        brand_id="b1",
        name="Brand",
        domain="HTTPS://WWW.MyBrand.COM/home",
    )
    assert p.domain == "mybrand.com"

    # In CitationObservation
    c = CitationObservation(
        scan_id="s1",
        url="https://www.source.org/doc?id=5",
        domain="HTTPS://WWW.SOURCE.ORG/",
        source_type="web",
    )
    assert c.domain == "source.org"
    # Preserves original URL exactly
    assert c.url == "https://www.source.org/doc?id=5"


# ======================================================================
# 7. Alias, Place ID and Domain-Alias Deduplication
# ======================================================================


def test_alias_place_id_and_domain_alias_deduplication() -> None:
    """Verify aliases and place IDs deduplicate preserving order,
    and domain aliases normalize and deduplicate.
    """
    profile = BrandProfile(
        brand_id="b1",
        name="Cafe Rosa",
        aliases=["Rosa Coffee", "Cafe Rosa", "Rosa Coffee", "Rosa's"],
        place_ids=["place_1", "place_2", "place_1"],
        domain_aliases=[
            "https://www.caferosa.com/menu",
            "CAFEROSA.COM",
            "http://alt-domain.org/",
        ],
    )
    assert profile.aliases == ["Rosa Coffee", "Cafe Rosa", "Rosa's"]
    assert profile.place_ids == ["place_1", "place_2"]
    assert profile.domain_aliases == ["caferosa.com", "alt-domain.org"]

    # Blank alias rejected
    with pytest.raises(ValidationError):
        BrandProfile(brand_id="b1", name="B", aliases=["Good", " "])

    # Blank place_id rejected
    with pytest.raises(ValidationError):
        BrandProfile(brand_id="b1", name="B", place_ids=[""])


# ======================================================================
# 8. VisibilityProject Target/Competitor Validation
# ======================================================================


def test_visibility_project_target_competitor_validation(utc_now: datetime) -> None:
    """Verify target brand cannot be in competitors and competitor IDs deduplicate."""
    # Target in competitors rejected
    with pytest.raises(ValidationError, match="target_brand_id 'brand_a' must not appear"):
        VisibilityProject(
            project_id="p1",
            name="Austin",
            target_brand_id="brand_a",
            competitor_brand_ids=["brand_b", "brand_a"],
            created_at=utc_now,
        )

    # Competitor IDs deduplicate preserving order
    project = VisibilityProject(
        project_id="p1",
        name="Austin",
        target_brand_id="brand_a",
        competitor_brand_ids=["brand_b", "brand_c", "brand_b"],
        created_at=utc_now,
    )
    assert project.competitor_brand_ids == ["brand_b", "brand_c"]

    # Blank competitor ID rejected
    with pytest.raises(ValidationError):
        VisibilityProject(
            project_id="p1",
            name="Austin",
            target_brand_id="brand_a",
            competitor_brand_ids=["brand_b", "   "],
            created_at=utc_now,
        )


# ======================================================================
# 9. VisibilityScan Status Invariants
# ======================================================================


def test_visibility_scan_status_invariants(utc_now: datetime) -> None:
    """Verify scan status constraints: COMPLETED, FAILED, PENDING, RUNNING rules."""
    # COMPLETED requires completed_at
    with pytest.raises(ValidationError, match="COMPLETED scan requires completed_at"):
        _make_valid_scan(utc_now, status=ScanStatus.COMPLETED, completed_at=None)

    # COMPLETED cannot contain error fields
    with pytest.raises(ValidationError, match="COMPLETED scan cannot contain error fields"):
        _make_valid_scan(
            utc_now,
            status=ScanStatus.COMPLETED,
            completed_at=utc_now,
            error_message="unexpected error",
        )

    # FAILED requires completed_at
    with pytest.raises(ValidationError, match="FAILED scan requires completed_at"):
        _make_valid_scan(
            utc_now,
            status=ScanStatus.FAILED,
            completed_at=None,
            error_message="timeout",
        )

    # FAILED requires error_message
    with pytest.raises(ValidationError, match="FAILED scan requires error_message"):
        _make_valid_scan(
            utc_now,
            status=ScanStatus.FAILED,
            completed_at=utc_now,
            error_message=None,
        )

    # PENDING cannot contain completed_at
    with pytest.raises(ValidationError, match="PENDING scan must not contain completed_at"):
        _make_valid_scan(
            utc_now,
            status=ScanStatus.PENDING,
            completed_at=utc_now,
        )

    # RUNNING cannot contain completed_at
    with pytest.raises(ValidationError, match="RUNNING scan must not contain completed_at"):
        _make_valid_scan(
            utc_now,
            status=ScanStatus.RUNNING,
            completed_at=utc_now,
        )

    # completed_at earlier than started_at rejected
    earlier = datetime(2026, 9, 21, 10, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValidationError, match="completed_at cannot be earlier than started_at"):
        _make_valid_scan(
            utc_now,
            status=ScanStatus.COMPLETED,
            completed_at=earlier,
        )

    # Negative duration rejected
    with pytest.raises(ValidationError, match="duration_seconds cannot be negative"):
        _make_valid_scan(
            utc_now,
            status=ScanStatus.COMPLETED,
            completed_at=utc_now,
            duration_seconds=-1.0,
        )


# ======================================================================
# 10. Mention Invariants
# ======================================================================


def test_mention_invariants() -> None:
    """Verify mentioned=False requires count=0, pos=None;
    mentioned=True requires count>0, pos>=0.
    """
    # mentioned=False with count > 0 rejected
    with pytest.raises(ValidationError, match="mentioned=False requires mention_count=0"):
        BrandObservation(
            scan_id="s1",
            brand_id="b1",
            role=BrandRole.TARGET,
            mentioned=False,
            mention_count=2,
        )

    # mentioned=False with first_mention_position rejected
    with pytest.raises(ValidationError, match="mentioned=False requires"):
        BrandObservation(
            scan_id="s1",
            brand_id="b1",
            role=BrandRole.TARGET,
            mentioned=False,
            first_mention_position=0,
        )

    # mentioned=True with count=0 rejected
    with pytest.raises(ValidationError, match="mentioned=True requires mention_count>0"):
        BrandObservation(
            scan_id="s1",
            brand_id="b1",
            role=BrandRole.TARGET,
            mentioned=True,
            mention_count=0,
            first_mention_position=10,
        )

    # mentioned=True with pos=None rejected
    with pytest.raises(ValidationError, match="mentioned=True requires mention_count>0"):
        BrandObservation(
            scan_id="s1",
            brand_id="b1",
            role=BrandRole.TARGET,
            mentioned=True,
            mention_count=1,
            first_mention_position=None,
        )

    # first_mention_position 0 is valid (0-based offset)
    obs = BrandObservation(
        scan_id="s1",
        brand_id="b1",
        role=BrandRole.TARGET,
        mentioned=True,
        mention_count=1,
        first_mention_position=0,
    )
    assert obs.first_mention_position == 0

    # Negative first_mention_position rejected
    with pytest.raises(ValidationError):
        BrandObservation(
            scan_id="s1",
            brand_id="b1",
            role=BrandRole.TARGET,
            mentioned=True,
            mention_count=1,
            first_mention_position=-1,
        )


# ======================================================================
# 11. Retrieval-Position Invariants
# ======================================================================


def test_retrieval_position_invariants() -> None:
    """Verify retrieved=False requires position=None; retrieved=True requires position>=1."""
    # retrieved=False with position rejected
    with pytest.raises(
        ValidationError,
        match="retrieved=False requires best_retrieval_position=None",
    ):
        BrandObservation(
            scan_id="s1",
            brand_id="b1",
            role=BrandRole.TARGET,
            retrieved=False,
            best_retrieval_position=1,
        )

    # retrieved=True without position rejected
    with pytest.raises(ValidationError, match="retrieved=True requires best_retrieval_position"):
        BrandObservation(
            scan_id="s1",
            brand_id="b1",
            role=BrandRole.TARGET,
            retrieved=True,
            best_retrieval_position=None,
        )

    # Position 0 rejected (must be >= 1)
    with pytest.raises(ValidationError, match="Positions must be at least 1"):
        BrandObservation(
            scan_id="s1",
            brand_id="b1",
            role=BrandRole.TARGET,
            retrieved=True,
            best_retrieval_position=0,
        )

    # Valid retrieved=True
    obs = BrandObservation(
        scan_id="s1",
        brand_id="b1",
        role=BrandRole.TARGET,
        retrieved=True,
        best_retrieval_position=3,
    )
    assert obs.best_retrieval_position == 3


# ======================================================================
# 12. Recommendation-Position Invariants
# ======================================================================


def test_recommendation_position_invariants() -> None:
    """Verify recommended=False requires position=None; recommended=True requires position>=1."""
    # recommended=False with position rejected
    with pytest.raises(
        ValidationError,
        match="recommended=False requires recommendation_position=None",
    ):
        BrandObservation(
            scan_id="s1",
            brand_id="b1",
            role=BrandRole.TARGET,
            recommended=False,
            recommendation_position=1,
        )

    # recommended=True without position rejected
    with pytest.raises(ValidationError, match="recommended=True requires recommendation_position"):
        BrandObservation(
            scan_id="s1",
            brand_id="b1",
            role=BrandRole.TARGET,
            recommended=True,
            recommendation_position=None,
        )

    # Position 0 rejected (must be >= 1)
    with pytest.raises(ValidationError, match="Positions must be at least 1"):
        BrandObservation(
            scan_id="s1",
            brand_id="b1",
            role=BrandRole.TARGET,
            recommended=True,
            recommendation_position=0,
        )

    # Valid recommended=True
    obs = BrandObservation(
        scan_id="s1",
        brand_id="b1",
        role=BrandRole.TARGET,
        recommended=True,
        recommendation_position=1,
    )
    assert obs.recommendation_position == 1


# ======================================================================
# 13. Citation Invariants
# ======================================================================


def test_citation_invariants() -> None:
    """Verify cited=False requires empty lists; cited=True requires non-empty lists."""
    # cited=False with URLs rejected
    with pytest.raises(ValidationError, match="cited=False requires empty citation lists"):
        BrandObservation(
            scan_id="s1",
            brand_id="b1",
            role=BrandRole.TARGET,
            cited=False,
            citation_urls=["https://brand.com"],
        )

    # cited=True with empty URLs rejected
    with pytest.raises(ValidationError, match="cited=True requires at least one"):
        BrandObservation(
            scan_id="s1",
            brand_id="b1",
            role=BrandRole.TARGET,
            cited=True,
            citation_urls=[],
            citation_domains=["brand.com"],
        )

    # cited=True with empty domains rejected
    with pytest.raises(ValidationError, match="cited=True requires at least one"):
        BrandObservation(
            scan_id="s1",
            brand_id="b1",
            role=BrandRole.TARGET,
            cited=True,
            citation_urls=["https://brand.com"],
            citation_domains=[],
        )

    # Valid cited=True with deduplication
    obs = BrandObservation(
        scan_id="s1",
        brand_id="b1",
        role=BrandRole.TARGET,
        cited=True,
        citation_urls=["https://brand.com", "https://brand.com"],
        citation_domains=["HTTPS://WWW.BRAND.COM/", "brand.com"],
    )
    assert obs.citation_urls == ["https://brand.com"]
    assert obs.citation_domains == ["brand.com"]


# ======================================================================
# 14. Fan-Out Invariants
# ======================================================================


def test_fanout_invariants() -> None:
    """Verify fan-out observation invariants across Google Places and Google Search."""
    # Places found with position -> accepted
    fo_places = FanoutObservation(
        scan_id="s1",
        task_id="t1",
        query_text="coffee",
        tool="google_places",
        brand_id="b1",
        brand_found=True,
        position_in_task=2,
    )
    assert fo_places.brand_found is True
    assert fo_places.position_in_task == 2
    assert fo_places.tool == "google_places"

    # Places found without position -> rejected
    with pytest.raises(
        ValidationError,
        match="brand_found=True for Google Places requires position_in_task >= 1",
    ):
        FanoutObservation(
            scan_id="s1",
            task_id="t1",
            query_text="coffee",
            tool="google_places",
            brand_id="b1",
            brand_found=True,
            position_in_task=None,
        )

    # Search found without position -> accepted
    fo_search_none = FanoutObservation(
        scan_id="s1",
        task_id="t2",
        query_text="coffee reviews",
        tool="google_search",
        brand_id="b1",
        brand_found=True,
        position_in_task=None,
    )
    assert fo_search_none.brand_found is True
    assert fo_search_none.position_in_task is None
    assert fo_search_none.tool == "google_search"

    # Search found with positive position -> accepted
    fo_search_pos = FanoutObservation(
        scan_id="s1",
        task_id="t2",
        query_text="coffee reviews",
        tool="google_search",
        brand_id="b1",
        brand_found=True,
        position_in_task=3,
    )
    assert fo_search_pos.brand_found is True
    assert fo_search_pos.position_in_task == 3

    # Search found with position 0 -> rejected
    with pytest.raises(ValidationError, match="position_in_task must be at least 1"):
        FanoutObservation(
            scan_id="s1",
            task_id="t2",
            query_text="coffee reviews",
            tool="google_search",
            brand_id="b1",
            brand_found=True,
            position_in_task=0,
        )

    # Not found with position -> rejected (Places)
    with pytest.raises(
        ValidationError,
        match="brand_found=False requires position_in_task=None",
    ):
        FanoutObservation(
            scan_id="s1",
            task_id="t1",
            query_text="coffee",
            tool="google_places",
            brand_id="b1",
            brand_found=False,
            position_in_task=1,
        )

    # Not found with position -> rejected (Search)
    with pytest.raises(
        ValidationError,
        match="brand_found=False requires position_in_task=None",
    ):
        FanoutObservation(
            scan_id="s1",
            task_id="t2",
            query_text="coffee",
            tool="google_search",
            brand_id="b1",
            brand_found=False,
            position_in_task=1,
        )

    # Not found without position -> accepted (Places and Search)
    fo_nf_places = FanoutObservation(
        scan_id="s1",
        task_id="t1",
        query_text="coffee",
        tool="google_places",
        brand_id="b1",
        brand_found=False,
        position_in_task=None,
    )
    assert fo_nf_places.brand_found is False
    assert fo_nf_places.position_in_task is None

    fo_nf_search = FanoutObservation(
        scan_id="s1",
        task_id="t2",
        query_text="coffee",
        tool="google_search",
        brand_id="b1",
        brand_found=False,
        position_in_task=None,
    )
    assert fo_nf_search.brand_found is False
    assert fo_nf_search.position_in_task is None

    # Existing ToolName serialized values are handled correctly
    fo_enum_places = FanoutObservation(
        scan_id="s1",
        task_id="t1",
        query_text="coffee",
        tool=ToolName.GOOGLE_PLACES,
        brand_id="b1",
        brand_found=True,
        position_in_task=1,
    )
    assert fo_enum_places.tool == "google_places"

    fo_enum_search = FanoutObservation(
        scan_id="s1",
        task_id="t2",
        query_text="coffee",
        tool=ToolName.GOOGLE_SEARCH,
        brand_id="b1",
        brand_found=True,
    )
    assert fo_enum_search.tool == "google_search"

    # Case-insensitive string normalization
    fo_case = FanoutObservation(
        scan_id="s1",
        task_id="t1",
        query_text="coffee",
        tool="GOOGLE_PLACES",
        brand_id="b1",
        brand_found=True,
        position_in_task=1,
    )
    assert fo_case.tool == "google_places"

    # Unsupported and fuzzy tool names rejected
    with pytest.raises(ValidationError, match="Unsupported tool 'places'"):
        FanoutObservation(
            scan_id="s1",
            task_id="t1",
            query_text="coffee",
            tool="places",
            brand_id="b1",
        )

    with pytest.raises(ValidationError, match="Unsupported tool 'search'"):
        FanoutObservation(
            scan_id="s1",
            task_id="t2",
            query_text="coffee",
            tool="search",
            brand_id="b1",
        )


# ======================================================================
# 15. Metric Ranges and Zero-Scan Behavior
# ======================================================================


def test_metric_ranges_and_zero_scan_behavior() -> None:
    """Verify metric rate bounds [0.0, 1.0], avg position >= 1.0, and zero-scan invariants."""
    # Rate > 1.0 rejected
    with pytest.raises(ValidationError, match="Rates must be between 0.0 and 1.0"):
        VisibilityMetrics(
            brand_id="b1",
            total_scans=10,
            mention_rate=1.1,
            recommendation_rate=0.5,
            citation_rate=0.5,
            share_of_voice=0.5,
            fanout_coverage=0.5,
        )

    # Rate < 0.0 rejected
    with pytest.raises(ValidationError, match="Rates must be between 0.0 and 1.0"):
        VisibilityMetrics(
            brand_id="b1",
            total_scans=10,
            mention_rate=-0.1,
            recommendation_rate=0.5,
            citation_rate=0.5,
            share_of_voice=0.5,
            fanout_coverage=0.5,
        )

    # Average recommendation position < 1.0 rejected
    with pytest.raises(
        ValidationError,
        match="average_recommendation_position must be at least 1.0",
    ):
        VisibilityMetrics(
            brand_id="b1",
            total_scans=10,
            mention_rate=0.5,
            recommendation_rate=0.5,
            citation_rate=0.5,
            average_recommendation_position=0.8,
            share_of_voice=0.5,
            fanout_coverage=0.5,
        )

    # total_scans=0 with non-zero rate rejected
    with pytest.raises(ValidationError, match="When total_scans=0, mention_rate must be 0.0"):
        VisibilityMetrics(
            brand_id="b1",
            total_scans=0,
            mention_rate=0.5,
            recommendation_rate=0.0,
            citation_rate=0.0,
            share_of_voice=0.0,
            fanout_coverage=0.0,
        )

    # total_scans=0 with average position provided rejected
    with pytest.raises(
        ValidationError,
        match="When total_scans=0, average_recommendation_position must be None",
    ):
        VisibilityMetrics(
            brand_id="b1",
            total_scans=0,
            mention_rate=0.0,
            recommendation_rate=0.0,
            citation_rate=0.0,
            average_recommendation_position=1.5,
            share_of_voice=0.0,
            fanout_coverage=0.0,
        )

    # Valid total_scans=0
    zero_metrics = VisibilityMetrics(
        brand_id="b1",
        total_scans=0,
        mention_rate=0.0,
        recommendation_rate=0.0,
        citation_rate=0.0,
        share_of_voice=0.0,
        fanout_coverage=0.0,
    )
    assert zero_metrics.total_scans == 0
    assert zero_metrics.average_recommendation_position is None


# ======================================================================
# 16. ScanBundle Scan-ID Consistency
# ======================================================================


def test_scan_bundle_scan_id_consistency(utc_now: datetime) -> None:
    """Verify all child observations must share the same scan_id as scan.scan_id."""
    scan = _make_valid_scan(utc_now, scan_id="scan_main")

    # Mismatched BrandObservation
    mismatched_brand = BrandObservation(
        scan_id="scan_other", brand_id="b1", role=BrandRole.TARGET
    )
    with pytest.raises(ValidationError, match="does not match scan.scan_id 'scan_main'"):
        VisibilityScanBundle(scan=scan, brand_observations=[mismatched_brand])

    # Mismatched FanoutObservation
    valid_brand = BrandObservation(
        scan_id="scan_main", brand_id="b1", role=BrandRole.TARGET
    )
    mismatched_fanout = FanoutObservation(
        scan_id="scan_other",
        task_id="t1",
        query_text="coffee",
        tool="google_places",
        brand_id="b1",
    )
    with pytest.raises(
        ValidationError,
        match="FanoutObservation scan_id 'scan_other' does not match",
    ):
        VisibilityScanBundle(
            scan=scan,
            brand_observations=[valid_brand],
            fanout_observations=[mismatched_fanout],
        )

    # Mismatched CitationObservation
    mismatched_citation = CitationObservation(
        scan_id="scan_other",
        url="https://a.com",
        domain="a.com",
        source_type="web",
    )
    with pytest.raises(
        ValidationError,
        match="CitationObservation scan_id 'scan_other' does not match",
    ):
        VisibilityScanBundle(
            scan=scan,
            brand_observations=[valid_brand],
            citations=[mismatched_citation],
        )


# ======================================================================
# 17. Exactly One TARGET Observation
# ======================================================================


def test_scan_bundle_exactly_one_target_observation(utc_now: datetime) -> None:
    """Verify VisibilityScanBundle requires exactly one BrandObservation with role TARGET."""
    scan = _make_valid_scan(utc_now, scan_id="s1")

    # Zero TARGET observations rejected
    competitor_obs = BrandObservation(
        scan_id="s1", brand_id="comp_1", role=BrandRole.COMPETITOR
    )
    with pytest.raises(
        ValidationError,
        match="Exactly one BrandObservation must have role TARGET, found 0",
    ):
        VisibilityScanBundle(scan=scan, brand_observations=[competitor_obs])

    # Two TARGET observations rejected
    target_1 = BrandObservation(
        scan_id="s1", brand_id="t1", role=BrandRole.TARGET
    )
    target_2 = BrandObservation(
        scan_id="s1", brand_id="t2", role=BrandRole.TARGET
    )
    with pytest.raises(
        ValidationError,
        match="Exactly one BrandObservation must have role TARGET, found 2",
    ):
        VisibilityScanBundle(scan=scan, brand_observations=[target_1, target_2])

    # Exactly one TARGET observation succeeds
    bundle = VisibilityScanBundle(
        scan=scan, brand_observations=[target_1, competitor_obs]
    )
    assert len(bundle.brand_observations) == 2


# ======================================================================
# 18. Duplicate Brand Observation Rejection
# ======================================================================


def test_scan_bundle_duplicate_brand_observation_rejected(utc_now: datetime) -> None:
    """Verify a brand ID may appear only once in brand_observations."""
    scan = _make_valid_scan(utc_now, scan_id="s1")
    target = BrandObservation(
        scan_id="s1", brand_id="brand_x", role=BrandRole.TARGET
    )
    duplicate_brand = BrandObservation(
        scan_id="s1", brand_id="brand_x", role=BrandRole.COMPETITOR
    )
    with pytest.raises(
        ValidationError,
        match="A brand ID may appear only once in brand_observations",
    ):
        VisibilityScanBundle(scan=scan, brand_observations=[target, duplicate_brand])


# ======================================================================
# 19. Duplicate Fan-out Observation Rejection
# ======================================================================


def test_scan_bundle_duplicate_fanout_observation_rejected(utc_now: datetime) -> None:
    """Verify fan-out observations must be unique by (scan_id, task_id, brand_id)."""
    scan = _make_valid_scan(utc_now, scan_id="s1")
    target = BrandObservation(scan_id="s1", brand_id="b1", role=BrandRole.TARGET)

    fo1 = FanoutObservation(
        scan_id="s1",
        task_id="task_1",
        query_text="coffee",
        tool="google_places",
        brand_id="b1",
    )
    fo2 = FanoutObservation(
        scan_id="s1",
        task_id="task_1",
        query_text="coffee shops",
        tool="google_places",
        brand_id="b1",
    )
    with pytest.raises(ValidationError, match="Duplicate fanout observation found"):
        VisibilityScanBundle(
            scan=scan,
            brand_observations=[target],
            fanout_observations=[fo1, fo2],
        )

    # Different task_id or brand_id succeeds
    fo3 = FanoutObservation(
        scan_id="s1", task_id="task_2", query_text="coffee", tool="google_places", brand_id="b1"
    )
    bundle = VisibilityScanBundle(
        scan=scan,
        brand_observations=[target],
        fanout_observations=[fo1, fo3],
    )
    assert len(bundle.fanout_observations) == 2


# ======================================================================
# 20. Duplicate Citation Rejection
# ======================================================================


def test_scan_bundle_duplicate_citation_rejected(utc_now: datetime) -> None:
    """Verify citations must be unique by (scan_id, url, source_type)."""
    scan = _make_valid_scan(utc_now, scan_id="s1")
    target = BrandObservation(scan_id="s1", brand_id="b1", role=BrandRole.TARGET)

    c1 = CitationObservation(
        scan_id="s1",
        url="https://example.com/guide",
        domain="example.com",
        source_type="web",
    )
    c2 = CitationObservation(
        scan_id="s1",
        url="https://example.com/guide",
        domain="example.com",
        source_type="WEB",  # case-insensitive source_type normalized
    )
    with pytest.raises(ValidationError, match="Duplicate citation found"):
        VisibilityScanBundle(
            scan=scan,
            brand_observations=[target],
            citations=[c1, c2],
        )

    # Different URL or source_type succeeds
    c3 = CitationObservation(
        scan_id="s1",
        url="https://example.com/guide2",
        domain="example.com",
        source_type="web",
    )
    bundle = VisibilityScanBundle(
        scan=scan,
        brand_observations=[target],
        citations=[c1, c3],
    )
    assert len(bundle.citations) == 2
