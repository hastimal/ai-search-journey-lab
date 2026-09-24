"""Tests for V4 AI Visibility Analytics."""

from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest
from pydantic import ValidationError

from ai_search_journey.visibility.v4_analytics import (
    BigQueryVisibilityAnalyticsRepository,
    CitationAnalysisRequest,
    CompetitorComparisonRequest,
    FanoutGapRequest,
    VisibilitySummaryRequest,
)


@pytest.fixture
def valid_start() -> datetime:
    return datetime(2023, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def valid_end(valid_start: datetime) -> datetime:
    return valid_start + timedelta(days=30)


def test_visibility_summary_request_validation(valid_start: datetime, valid_end: datetime) -> None:
    # Valid
    req = VisibilitySummaryRequest(
        start_date=valid_start, end_date=valid_end, brand_id="  brandA  "
    )
    assert req.brand_id == "branda"

    # Invalid date range
    with pytest.raises(ValidationError, match="start_date cannot be after end_date"):
        VisibilitySummaryRequest(start_date=valid_end, end_date=valid_start, brand_id="a")

    # Invalid max window
    with pytest.raises(ValidationError, match="Maximum date window is 365 days"):
        VisibilitySummaryRequest(
            start_date=valid_start, end_date=valid_start + timedelta(days=400), brand_id="a"
        )

    # Empty brand
    with pytest.raises(ValidationError, match="cannot be empty"):
        VisibilitySummaryRequest(start_date=valid_start, end_date=valid_end, brand_id="   ")

    # Timezone naive
    with pytest.raises(
        ValidationError
    ):  # Pydantic will catch the validation error from our custom validator
        VisibilitySummaryRequest(start_date=datetime(2023, 1, 1), end_date=valid_end, brand_id="a")


@mock.patch("ai_search_journey.visibility.v4_analytics.bigquery")
def test_get_visibility_summary_empty(
    mock_bq: mock.MagicMock, valid_start: datetime, valid_end: datetime
) -> None:
    # Mock BigQuery client
    mock_client = mock.MagicMock()
    mock_job = mock.MagicMock()
    mock_job.result.return_value = []
    mock_client.query.return_value = mock_job

    repo = BigQueryVisibilityAnalyticsRepository(project_id="test", client=mock_client)
    req = VisibilitySummaryRequest(start_date=valid_start, end_date=valid_end, brand_id="branda")

    result = repo.get_visibility_summary(req)

    assert result.brand_id == "branda"
    assert result.total_scans == 0
    assert result.mention_rate == 0.0

    # Verify parameterized query
    mock_client.query.assert_called_once()
    args, kwargs = mock_client.query.call_args
    sql = args[0]
    assert "WHERE started_at >= @start_date AND started_at <= @end_date" in sql
    assert "brand_id = @brand_id" in sql

    # Verify we pass config (which has query params)
    assert "job_config" in kwargs


@mock.patch("ai_search_journey.visibility.v4_analytics.bigquery")
def test_get_visibility_summary_success(
    mock_bq: mock.MagicMock, valid_start: datetime, valid_end: datetime
) -> None:
    # Mock BigQuery client returning rows
    mock_client = mock.MagicMock()
    mock_job = mock.MagicMock()
    mock_job.result.return_value = [
        {"total_scans": 10, "mentioned_scans": 5, "recommended_scans": 2, "cited_scans": 1}
    ]
    mock_client.query.return_value = mock_job

    repo = BigQueryVisibilityAnalyticsRepository(project_id="test", client=mock_client)
    req = VisibilitySummaryRequest(start_date=valid_start, end_date=valid_end, brand_id="branda")

    result = repo.get_visibility_summary(req)

    assert result.brand_id == "branda"
    assert result.total_scans == 10
    assert result.mention_rate == 0.5
    assert result.recommendation_rate == 0.2
    assert result.citation_rate == 0.1


@mock.patch("ai_search_journey.visibility.v4_analytics.bigquery")
def test_compare_brands_success(
    mock_bq: mock.MagicMock, valid_start: datetime, valid_end: datetime
) -> None:
    mock_client = mock.MagicMock()
    mock_job = mock.MagicMock()
    mock_job.result.return_value = [
        {
            "brand_id": "branda",
            "total_scans": 10,
            "mentioned_scans": 5,
            "recommended_scans": 2,
            "cited_scans": 1,
        },
        {
            "brand_id": "brandb",
            "total_scans": 10,
            "mentioned_scans": 8,
            "recommended_scans": 4,
            "cited_scans": 2,
        },
    ]
    mock_client.query.return_value = mock_job

    repo = BigQueryVisibilityAnalyticsRepository(project_id="test", client=mock_client)
    req = CompetitorComparisonRequest(
        start_date=valid_start, end_date=valid_end, brand_ids=["branda", "brandb", "brandc"]
    )

    result = repo.compare_brands(req)

    assert len(result.metrics) == 3

    # Brand A
    a = next(m for m in result.metrics if m.brand_id == "branda")
    assert a.total_scans == 10
    assert a.mention_rate == 0.5

    # Brand C (no rows returned for it)
    c = next(m for m in result.metrics if m.brand_id == "brandc")
    assert c.total_scans == 0
    assert c.mention_rate == 0.0


@mock.patch("ai_search_journey.visibility.v4_analytics.bigquery")
def test_analyze_citations(
    mock_bq: mock.MagicMock, valid_start: datetime, valid_end: datetime
) -> None:
    mock_client = mock.MagicMock()
    mock_job = mock.MagicMock()
    mock_job.result.return_value = [
        {"domain": "example.com", "source_type": "blog", "citation_count": 5},
        {"domain": "news.com", "source_type": "article", "citation_count": 2},
    ]
    mock_client.query.return_value = mock_job

    repo = BigQueryVisibilityAnalyticsRepository(project_id="test", client=mock_client)
    req = CitationAnalysisRequest(
        start_date=valid_start, end_date=valid_end, brand_id="branda", limit=5, sort_by="citations"
    )

    result = repo.analyze_citations(req)

    assert len(result.top_citations) == 2
    assert result.top_citations[0].domain == "example.com"
    assert result.top_citations[0].count == 5


@mock.patch("ai_search_journey.visibility.v4_analytics.bigquery")
def test_find_fanout_gaps(
    mock_bq: mock.MagicMock, valid_start: datetime, valid_end: datetime
) -> None:
    mock_client = mock.MagicMock()
    mock_job = mock.MagicMock()
    mock_job.result.return_value = [
        {"query_text": "how to X", "tool": "google_search", "miss_count": 3},
    ]
    mock_client.query.return_value = mock_job

    repo = BigQueryVisibilityAnalyticsRepository(project_id="test", client=mock_client)
    req = FanoutGapRequest(start_date=valid_start, end_date=valid_end, brand_id="branda")

    result = repo.find_fanout_gaps(req)

    assert len(result.gaps) == 1
    assert result.gaps[0].query_text == "how to X"
    assert result.gaps[0].miss_count == 3


@mock.patch("ai_search_journey.visibility.v4_analytics.bigquery")
def test_get_available_history_partition_safe(mock_bq: mock.MagicMock) -> None:
    """Test get_available_history queries partition safely and returns metadata."""
    from ai_search_journey.visibility.v4_analytics import AvailableHistoryRequest

    mock_client = mock.MagicMock()
    mock_summary_job = mock.MagicMock()
    mock_summary_job.result.return_value = [
        {
            "earliest_started_at": "2026-09-24T03:03:19.002028+00:00",
            "latest_started_at": "2026-09-24T04:00:45.255716+00:00",
            "total_scans": 4,
            "distinct_brand_ids": ["halcyon_southtown", "kafe_krave"],
        }
    ]
    mock_recent_job = mock.MagicMock()
    mock_recent_job.result.return_value = [
        {
            "scan_id": "scan_5191faf2fb77",
            "started_at": "2026-09-24T04:00:45.255716+00:00",
            "brand_id": "halcyon_southtown",
            "brand_name_snapshot": "Halcyon Southtown",
            "prompt_text_snapshot": "Find a coffee shop near Geekdom",
        }
    ]

    mock_client.query.side_effect = [mock_summary_job, mock_recent_job]

    repo = BigQueryVisibilityAnalyticsRepository(project_id="test", client=mock_client)
    req = AvailableHistoryRequest(lookback_days=30)
    result = repo.get_available_history(req)

    assert result.total_scans == 4
    assert result.earliest_started_at == "2026-09-24T03:03:19.002028+00:00"
    assert result.latest_started_at == "2026-09-24T04:00:45.255716+00:00"
    assert "halcyon_southtown" in result.distinct_brand_ids
    assert len(result.recent_scans) == 1
    assert result.recent_scans[0].scan_id == "scan_5191faf2fb77"

    assert mock_client.query.call_count == 2
    for call in mock_client.query.call_args_list:
        sql = call[0][0]
        # Must filter on started_at for partition safety
        assert "started_at >=" in sql
