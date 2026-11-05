"""Tests for local persistent visibility history and backend factory (Issue #31)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pytest

from ai_search_journey.config import settings
from ai_search_journey.visibility.bigquery_repository import BigQueryVisibilityRepository
from ai_search_journey.visibility.history_factory import (
    get_configured_backend,
    get_visibility_analytics_repository,
    get_visibility_repository,
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
from ai_search_journey.visibility.sqlite_repository import SQLiteVisibilityRepository
from ai_search_journey.visibility.v4_analytics import (
    AvailableHistoryRequest,
    BigQueryVisibilityAnalyticsRepository,
    BrandTrendRequest,
    CitationAnalysisRequest,
    CompetitorComparisonRequest,
    FanoutGapRequest,
    VisibilitySummaryRequest,
)


def _make_bundle(
    scan_id: str,
    brand_id: str = "austin_artisan",
    brand_name: str = "Austin Artisan Coffee",
    started_at: datetime | None = None,
    mentioned: bool = True,
    recommended: bool = True,
    cited: bool = True,
) -> VisibilityScanBundle:
    if started_at is None:
        started_at = datetime.now(timezone.utc)
    completed_at = datetime.now(timezone.utc)

    scan = VisibilityScan(
        scan_id=scan_id,
        batch_id="batch_001",
        project_id="proj_001",
        brand_id=brand_id,
        brand_name_snapshot=brand_name,
        prompt_id="prompt_001",
        prompt_text_snapshot="Best coffee shop for working",
        model_name="gemini-2.5-flash",
        started_at=started_at,
        completed_at=completed_at,
        status=ScanStatus.COMPLETED,
        duration_seconds=1.5,
    )

    brand_obs = BrandObservation(
        scan_id=scan_id,
        brand_id=brand_id,
        role=BrandRole.TARGET,
        mentioned=mentioned,
        mention_count=2 if mentioned else 0,
        first_mention_position=1 if mentioned else None,
        retrieved=True,
        best_retrieval_position=1,
        recommended=recommended,
        recommendation_position=1 if recommended else None,
        cited=cited,
        citation_urls=["https://austinartisan.com"] if cited else [],
        citation_domains=["austinartisan.com"] if cited else [],
    )

    comp_obs = BrandObservation(
        scan_id=scan_id,
        brand_id="competitor_brew",
        role=BrandRole.COMPETITOR,
        mentioned=True,
        mention_count=1,
        first_mention_position=2,
        retrieved=True,
        best_retrieval_position=2,
        recommended=False,
        recommendation_position=None,
        cited=False,
        citation_urls=[],
        citation_domains=[],
    )

    fanout = FanoutObservation(
        scan_id=scan_id,
        task_id="task_1",
        query_text="quiet coffee shops with wifi",
        tool="google_places",
        brand_id=brand_id,
        brand_found=True,
        position_in_task=1,
    )

    citation = CitationObservation(
        scan_id=scan_id,
        url="https://austinartisan.com/about",
        domain="austinartisan.com",
        source_type="grounding",
        matched_brand_ids=[brand_id],
    )

    return VisibilityScanBundle(
        scan=scan,
        brand_observations=[brand_obs, comp_obs],
        fanout_observations=[fanout],
        citations=[citation],
    )


def test_sqlite_repository_auto_initialization(tmp_path: Path) -> None:
    """1. SQLite repository automatically creates directory, db file, and schema tables."""
    db_file = tmp_path / "sub_dir" / "test_history.db"
    assert not db_file.exists()

    repo = SQLiteVisibilityRepository(db_path=db_file)
    assert db_file.exists()

    history = repo.get_available_history(AvailableHistoryRequest())
    assert history.total_scans == 0
    assert history.distinct_brand_ids == []
    assert history.recent_scans == []


def test_sqlite_repository_save_and_retrieve_bundle(tmp_path: Path) -> None:
    """2. Saves and retrieves scan bundles with full round-trip fidelity."""
    db_file = tmp_path / "test.db"
    repo = SQLiteVisibilityRepository(db_path=db_file)

    bundle = _make_bundle("scan_001")
    repo.save_bundle(bundle)

    loaded = repo.get_bundle("scan_001")
    assert loaded is not None
    assert loaded.scan.scan_id == "scan_001"
    assert loaded.scan.brand_id == "austin_artisan"
    assert len(loaded.brand_observations) == 2
    assert len(loaded.citations) == 1
    assert loaded.citations[0].domain == "austinartisan.com"


def test_sqlite_persistence_across_separate_instances(tmp_path: Path) -> None:
    """3 & 4. Proves persistence across separate repository instances / process reopen."""
    db_file = tmp_path / "persist.db"

    # Instance 1: write
    repo1 = SQLiteVisibilityRepository(db_path=db_file)
    bundle = _make_bundle("scan_persist")
    repo1.save_bundle(bundle)

    # Instance 2: reopen same file
    repo2 = SQLiteVisibilityRepository(db_path=db_file)
    loaded = repo2.get_bundle("scan_persist")
    assert loaded is not None
    assert loaded.scan.scan_id == "scan_persist"

    avail = repo2.get_available_history(AvailableHistoryRequest())
    assert avail.total_scans == 1
    assert "austin_artisan" in avail.distinct_brand_ids


def test_sqlite_empty_history_clean_response(tmp_path: Path) -> None:
    """5. Empty local history returns clean zeroed models without exceptions."""
    db_file = tmp_path / "empty.db"
    repo = SQLiteVisibilityRepository(db_path=db_file)

    avail = repo.get_available_history(AvailableHistoryRequest())
    assert avail.total_scans == 0
    assert avail.earliest_started_at is None
    assert avail.latest_started_at is None
    assert avail.distinct_brand_ids == []
    assert avail.recent_scans == []

    now = datetime.now(timezone.utc)
    summary = repo.get_visibility_summary(
        VisibilitySummaryRequest(start_date=now, end_date=now, brand_id="nonexistent")
    )
    assert summary.total_scans == 0
    assert summary.mention_rate == 0.0

    trend = repo.get_brand_trend(
        BrandTrendRequest(start_date=now, end_date=now, brand_id="nonexistent")
    )
    assert trend.trends == []

    comp = repo.compare_brands(
        CompetitorComparisonRequest(
            start_date=now, end_date=now, brand_ids=["brand_a", "brand_b"]
        )
    )
    assert len(comp.metrics) == 2
    assert comp.metrics[0].total_scans == 0

    citations = repo.analyze_citations(
        CitationAnalysisRequest(start_date=now, end_date=now, brand_id="nonexistent")
    )
    assert citations.top_citations == []

    gaps = repo.find_fanout_gaps(
        FanoutGapRequest(start_date=now, end_date=now, brand_id="nonexistent")
    )
    assert gaps.gaps == []


def test_sqlite_analytics_operations(tmp_path: Path) -> None:
    """6, 7, 8. Verifies get_available_history, visibility summary, trends, comparisons."""
    db_file = tmp_path / "analytics.db"
    repo = SQLiteVisibilityRepository(db_path=db_file)

    t0 = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    b1 = _make_bundle(
        "scan_1", brand_id="brand_a", started_at=t0, mentioned=True, recommended=True
    )
    b2 = _make_bundle(
        "scan_2", brand_id="brand_a", started_at=t0, mentioned=True, recommended=False
    )
    repo.save_bundle(b1)
    repo.save_bundle(b2)

    req_summary = VisibilitySummaryRequest(
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
        brand_id="brand_a",
    )
    summary = repo.get_visibility_summary(req_summary)
    assert summary.total_scans == 2
    assert summary.mention_rate == 1.0
    assert summary.recommendation_rate == 0.5

    req_trend = BrandTrendRequest(
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
        brand_id="brand_a",
    )
    trend = repo.get_brand_trend(req_trend)
    assert len(trend.trends) == 1
    assert trend.trends[0].date == "2026-01-15"
    assert trend.trends[0].mention_rate == 1.0
    assert trend.trends[0].recommendation_rate == 0.5

    req_comp = CompetitorComparisonRequest(
        start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
        brand_ids=["brand_a", "competitor_brew"],
    )
    comp = repo.compare_brands(req_comp)
    assert len(comp.metrics) == 2
    assert comp.metrics[0].brand_id == "brand_a"
    assert comp.metrics[0].total_scans == 2
    assert comp.metrics[1].brand_id == "competitor_brew"
    assert comp.metrics[1].total_scans == 2


def test_mcp_reading_local_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """9. MCP server tools read directly from SQLite repository when local backend is selected."""
    db_file = tmp_path / "mcp_test.db"
    repo = SQLiteVisibilityRepository(db_path=db_file)
    bundle = _make_bundle("scan_mcp_1", brand_id="mcp_brand")
    repo.save_bundle(bundle)

    monkeypatch.setenv("AI_SEARCH_HISTORY_BACKEND", "local")
    monkeypatch.setenv("LOCAL_HISTORY_DB_PATH", str(db_file))

    import ai_search_journey.visibility.mcp_server as mcp_mod

    mcp_mod.repo = None  # Reset cached repository

    result = mcp_mod.get_available_history(lookback_days=30)
    assert result["total_scans"] == 1
    assert "mcp_brand" in result["distinct_brand_ids"]
    assert len(result["recent_scans"]) == 1
    assert result["recent_scans"][0]["scan_id"] == "scan_mcp_1"


def test_mcp_empty_history_returns_friendly_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MCP get_available_history includes a friendly message when 0 scans exist."""
    db_file = tmp_path / "empty_mcp.db"
    monkeypatch.setenv("AI_SEARCH_HISTORY_BACKEND", "local")
    monkeypatch.setenv("LOCAL_HISTORY_DB_PATH", str(db_file))

    import ai_search_journey.visibility.mcp_server as mcp_mod

    mcp_mod.repo = None

    result = mcp_mod.get_available_history(lookback_days=30)
    assert result["total_scans"] == 0
    assert "No visibility scans are available yet" in result.get("message", "")


def test_backend_configuration_selection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """10, 11, 12. Validates backend config resolution: local, bigquery, and invalid values."""
    monkeypatch.setenv("AI_SEARCH_HISTORY_BACKEND", "local")
    assert get_configured_backend() == "local"

    monkeypatch.setenv("AI_SEARCH_HISTORY_BACKEND", "bigquery")
    assert get_configured_backend() == "bigquery"

    monkeypatch.setenv("AI_SEARCH_HISTORY_BACKEND", "LOCAL")
    assert get_configured_backend() == "local"

    monkeypatch.setenv("AI_SEARCH_HISTORY_BACKEND", "invalid_backend")
    with pytest.raises(ValueError, match="Invalid AI_SEARCH_HISTORY_BACKEND"):
        get_configured_backend()


def test_bigquery_remains_selectable_and_fails_actionably(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """13, 14, 15. BigQuery remains selectable without silent fallback, fails actionably."""
    monkeypatch.setenv("AI_SEARCH_HISTORY_BACKEND", "bigquery")
    monkeypatch.setattr(settings, "bigquery_project", "test-project")
    monkeypatch.setattr(settings, "bigquery_dataset", "test_dataset")
    monkeypatch.setattr(settings, "bigquery_location", "US")

    # With mock client
    mock_client = mock.MagicMock()
    repo = get_visibility_analytics_repository(client=mock_client)
    assert isinstance(repo, BigQueryVisibilityAnalyticsRepository)

    # For v3 repository
    v3_repo = get_visibility_repository()
    assert isinstance(v3_repo, BigQueryVisibilityRepository)

    # Missing project ID raises actionable RuntimeError
    monkeypatch.setattr(settings, "bigquery_project", None)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("BIGQUERY_PROJECT", raising=False)

    with pytest.raises(RuntimeError, match="BigQuery repository unavailable"):
        get_visibility_analytics_repository()


def test_local_mode_does_not_instantiate_bigquery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Local mode does not require BigQuery or instantiate bigquery.Client."""
    monkeypatch.setenv("AI_SEARCH_HISTORY_BACKEND", "local")
    monkeypatch.setenv("LOCAL_HISTORY_DB_PATH", str(tmp_path / "local.db"))
    monkeypatch.setattr(settings, "bigquery_project", None)

    repo = get_visibility_repository()
    assert isinstance(repo, SQLiteVisibilityRepository)

    analytics_repo = get_visibility_analytics_repository()
    assert isinstance(analytics_repo, SQLiteVisibilityRepository)


def test_end_to_end_v3_write_local_persistence_mcp_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Integration test: V3 write -> SQLite persistence -> MCP get_available_history."""
    db_file = tmp_path / "e2e.db"
    monkeypatch.setenv("AI_SEARCH_HISTORY_BACKEND", "local")
    monkeypatch.setenv("LOCAL_HISTORY_DB_PATH", str(db_file))

    # 1. V3 write via factory
    v3_repo = get_visibility_repository()
    bundle = _make_bundle("e2e_scan_100", brand_id="artisan_e2e", brand_name="Artisan E2E")
    v3_repo.save_bundle(bundle)

    # 2. Reset MCP repo to simulate independent call
    import ai_search_journey.visibility.mcp_server as mcp_mod

    mcp_mod.repo = None

    # 3. MCP tool read
    res = mcp_mod.get_available_history(lookback_days=365)
    assert res["total_scans"] == 1
    assert "artisan_e2e" in res["distinct_brand_ids"]
    assert res["recent_scans"][0]["scan_id"] == "e2e_scan_100"
    assert res["recent_scans"][0]["brand_name_snapshot"] == "Artisan E2E"
