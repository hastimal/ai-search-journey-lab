"""V4 AI Visibility Analytics interfaces and BigQuery implementations."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator, model_validator

from ai_search_journey.visibility.bigquery_schema import (
    TABLE_BRAND_OBSERVATIONS,
    TABLE_CITATIONS,
    TABLE_FANOUT_OBSERVATIONS,
    validate_dataset_id,
    validate_location,
    validate_project_id,
)

# Optional BigQuery imports
try:
    from google.cloud import bigquery
except ImportError:
    bigquery = None  # type: ignore

# ======================================================================
# Exceptions
# ======================================================================


class AnalyticsValidationError(ValueError):
    """Raised when an analytics request fails validation."""


class BigQueryDependencyError(ImportError):
    """Raised when BigQuery optional dependencies are not installed."""


class AnalyticsDatabaseError(Exception):
    """Raised when a query to the analytics database fails."""


# ======================================================================
# V4 Request & Result Models
# ======================================================================


def validate_iso_date(v: datetime | None) -> datetime | None:
    if v is not None:
        if v.tzinfo is None or v.tzinfo.utcoffset(v) is None:
            raise AnalyticsValidationError("Dates must be timezone-aware (ISO format).")
    return v


def normalize_brand_id(v: str) -> str:
    cleaned = v.strip().lower()
    if not cleaned:
        raise AnalyticsValidationError("brand_id cannot be empty or whitespace.")
    return cleaned


class BaseAnalyticsRequest(BaseModel):
    """Base class for all analytics requests with common date validation."""

    start_date: datetime
    end_date: datetime

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def require_tz(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                v = datetime.fromisoformat(v)
            except ValueError as e:
                raise AnalyticsValidationError(f"Invalid ISO date: {e}") from e
        return v

    @field_validator("start_date", "end_date")
    @classmethod
    def check_tz(cls, v: datetime) -> datetime:
        return validate_iso_date(v)  # type: ignore

    @model_validator(mode="after")
    def validate_date_range(self) -> BaseAnalyticsRequest:
        if self.start_date > self.end_date:
            raise AnalyticsValidationError("start_date cannot be after end_date.")
        if (self.end_date - self.start_date).days > 365:
            raise AnalyticsValidationError("Maximum date window is 365 days.")
        return self


class VisibilitySummaryRequest(BaseAnalyticsRequest):
    brand_id: str

    @field_validator("brand_id")
    @classmethod
    def validate_brand(cls, v: str) -> str:
        return normalize_brand_id(v)


class VisibilitySummaryResult(BaseModel):
    brand_id: str
    total_scans: int
    mention_rate: float
    recommendation_rate: float
    citation_rate: float


class BrandTrendRequest(BaseAnalyticsRequest):
    brand_id: str

    @field_validator("brand_id")
    @classmethod
    def validate_brand(cls, v: str) -> str:
        return normalize_brand_id(v)


class TrendDataPoint(BaseModel):
    date: str  # YYYY-MM-DD
    mention_rate: float
    recommendation_rate: float


class BrandTrendResult(BaseModel):
    brand_id: str
    trends: list[TrendDataPoint]


class CompetitorComparisonRequest(BaseAnalyticsRequest):
    brand_ids: list[str] = Field(min_length=2, max_length=10)

    @field_validator("brand_ids")
    @classmethod
    def validate_brands(cls, v: list[str]) -> list[str]:
        return [normalize_brand_id(bid) for bid in v]


class CompetitorComparisonResult(BaseModel):
    metrics: list[VisibilitySummaryResult]


class CitationAnalysisRequest(BaseAnalyticsRequest):
    brand_id: str
    limit: int = Field(default=10, ge=1, le=100)
    sort_by: Literal["mentions", "citations"] = "citations"

    @field_validator("brand_id")
    @classmethod
    def validate_brand(cls, v: str) -> str:
        return normalize_brand_id(v)


class CitationDataPoint(BaseModel):
    domain: str
    source_type: str
    count: int


class CitationAnalysisResult(BaseModel):
    brand_id: str
    top_citations: list[CitationDataPoint]


class FanoutGapRequest(BaseAnalyticsRequest):
    brand_id: str
    limit: int = Field(default=20, ge=1, le=100)

    @field_validator("brand_id")
    @classmethod
    def validate_brand(cls, v: str) -> str:
        return normalize_brand_id(v)


class FanoutGapDataPoint(BaseModel):
    query_text: str
    tool: str
    miss_count: int


class FanoutGapResult(BaseModel):
    brand_id: str
    gaps: list[FanoutGapDataPoint]


# ======================================================================
# Interfaces
# ======================================================================


@runtime_checkable
class VisibilityAnalyticsRepository(Protocol):
    """Read-only interface for analyzing historical V3 AI Visibility scans."""

    def get_visibility_summary(
        self, request: VisibilitySummaryRequest
    ) -> VisibilitySummaryResult: ...

    def get_brand_trend(self, request: BrandTrendRequest) -> BrandTrendResult: ...

    def compare_brands(
        self, request: CompetitorComparisonRequest
    ) -> CompetitorComparisonResult: ...

    def analyze_citations(self, request: CitationAnalysisRequest) -> CitationAnalysisResult: ...

    def find_fanout_gaps(self, request: FanoutGapRequest) -> FanoutGapResult: ...


# ======================================================================
# BigQuery Implementation
# ======================================================================


class BigQueryVisibilityAnalyticsRepository:
    """Safe, parameterized read-only BigQuery implementation."""

    def __init__(
        self,
        project_id: str,
        dataset_id: str = "ai_search_journey_v3",
        location: str = "US",
        *,
        client: Any = None,
    ) -> None:
        self.project_id = validate_project_id(project_id)
        self.dataset_id = validate_dataset_id(dataset_id)
        self.location = validate_location(location)

        if client is not None:
            self._client = client
        else:
            if bigquery is None:
                raise BigQueryDependencyError(
                    'google-cloud-bigquery is required. Install with: pip install -e ".[bigquery]"'
                )
            self._client = bigquery.Client(project=self.project_id, location=self.location)

    def _execute_query(self, sql: str, params: list[Any]) -> list[Any]:
        if bigquery is None:
            raise BigQueryDependencyError("google-cloud-bigquery is required.")
        config = bigquery.QueryJobConfig(query_parameters=params)
        try:
            job = self._client.query(sql, job_config=config)
            return list(job.result())
        except Exception as e:
            raise AnalyticsDatabaseError(f"Failed to execute query: {e}") from e

    def get_visibility_summary(self, request: VisibilitySummaryRequest) -> VisibilitySummaryResult:
        sql = f"""
        SELECT
            COUNT(DISTINCT scan_id) AS total_scans,
            COUNTIF(mentioned = TRUE) AS mentioned_scans,
            COUNTIF(recommended = TRUE) AS recommended_scans,
            COUNTIF(cited = TRUE) AS cited_scans
        FROM `{self.project_id}.{self.dataset_id}.{TABLE_BRAND_OBSERVATIONS}`
        WHERE started_at >= @start_date AND started_at <= @end_date
            AND brand_id = @brand_id
        """
        params = [
            bigquery.ScalarQueryParameter("start_date", "TIMESTAMP", request.start_date),
            bigquery.ScalarQueryParameter("end_date", "TIMESTAMP", request.end_date),
            bigquery.ScalarQueryParameter("brand_id", "STRING", request.brand_id),
        ]
        rows = self._execute_query(sql, params)
        if not rows:
            return VisibilitySummaryResult(
                brand_id=request.brand_id,
                total_scans=0,
                mention_rate=0.0,
                recommendation_rate=0.0,
                citation_rate=0.0,
            )

        row = rows[0]
        t = int(row.get("total_scans") or 0)
        if t == 0:
            return VisibilitySummaryResult(
                brand_id=request.brand_id,
                total_scans=0,
                mention_rate=0.0,
                recommendation_rate=0.0,
                citation_rate=0.0,
            )

        m = int(row.get("mentioned_scans") or 0)
        r = int(row.get("recommended_scans") or 0)
        c = int(row.get("cited_scans") or 0)

        return VisibilitySummaryResult(
            brand_id=request.brand_id,
            total_scans=t,
            mention_rate=m / t,
            recommendation_rate=r / t,
            citation_rate=c / t,
        )

    def get_brand_trend(self, request: BrandTrendRequest) -> BrandTrendResult:
        sql = f"""
        SELECT
            CAST(DATE(started_at) AS STRING) as date_str,
            COUNT(DISTINCT scan_id) AS total_scans,
            COUNTIF(mentioned = TRUE) AS mentioned_scans,
            COUNTIF(recommended = TRUE) AS recommended_scans
        FROM `{self.project_id}.{self.dataset_id}.{TABLE_BRAND_OBSERVATIONS}`
        WHERE started_at >= @start_date AND started_at <= @end_date
            AND brand_id = @brand_id
        GROUP BY date_str
        ORDER BY date_str ASC
        """
        params = [
            bigquery.ScalarQueryParameter("start_date", "TIMESTAMP", request.start_date),
            bigquery.ScalarQueryParameter("end_date", "TIMESTAMP", request.end_date),
            bigquery.ScalarQueryParameter("brand_id", "STRING", request.brand_id),
        ]
        rows = self._execute_query(sql, params)
        trends = []
        for row in rows:
            d = row.get("date_str")
            t = int(row.get("total_scans") or 0)
            m = int(row.get("mentioned_scans") or 0)
            r = int(row.get("recommended_scans") or 0)
            if t > 0:
                trends.append(TrendDataPoint(date=d, mention_rate=m / t, recommendation_rate=r / t))
        return BrandTrendResult(brand_id=request.brand_id, trends=trends)

    def compare_brands(self, request: CompetitorComparisonRequest) -> CompetitorComparisonResult:
        sql = f"""
        SELECT
            brand_id,
            COUNT(DISTINCT scan_id) AS total_scans,
            COUNTIF(mentioned = TRUE) AS mentioned_scans,
            COUNTIF(recommended = TRUE) AS recommended_scans,
            COUNTIF(cited = TRUE) AS cited_scans
        FROM `{self.project_id}.{self.dataset_id}.{TABLE_BRAND_OBSERVATIONS}`
        WHERE started_at >= @start_date AND started_at <= @end_date
            AND brand_id IN UNNEST(@brand_ids)
        GROUP BY brand_id
        """
        params = [
            bigquery.ScalarQueryParameter("start_date", "TIMESTAMP", request.start_date),
            bigquery.ScalarQueryParameter("end_date", "TIMESTAMP", request.end_date),
            bigquery.ArrayQueryParameter("brand_ids", "STRING", request.brand_ids),
        ]
        rows = self._execute_query(sql, params)

        metrics = []
        brand_map = {b: (0, 0, 0, 0) for b in request.brand_ids}

        for row in rows:
            b = row.get("brand_id")
            t = int(row.get("total_scans") or 0)
            m = int(row.get("mentioned_scans") or 0)
            r = int(row.get("recommended_scans") or 0)
            c = int(row.get("cited_scans") or 0)
            brand_map[b] = (t, m, r, c)

        for b in request.brand_ids:
            t, m, r, c = brand_map[b]
            if t == 0:
                metrics.append(
                    VisibilitySummaryResult(
                        brand_id=b,
                        total_scans=0,
                        mention_rate=0.0,
                        recommendation_rate=0.0,
                        citation_rate=0.0,
                    )
                )
            else:
                metrics.append(
                    VisibilitySummaryResult(
                        brand_id=b,
                        total_scans=t,
                        mention_rate=m / t,
                        recommendation_rate=r / t,
                        citation_rate=c / t,
                    )
                )

        return CompetitorComparisonResult(metrics=metrics)

    def analyze_citations(self, request: CitationAnalysisRequest) -> CitationAnalysisResult:
        # Sort allowed values: "mentions", "citations". 
        # Since citations map directly to counts, we just sort by count.
        sql = f"""
        SELECT
            domain,
            source_type,
            COUNT(*) as citation_count
        FROM `{self.project_id}.{self.dataset_id}.{TABLE_CITATIONS}`, 
             UNNEST(matched_brand_ids) AS matched_brand_id
        WHERE started_at >= @start_date AND started_at <= @end_date
            AND matched_brand_id = @brand_id
        GROUP BY domain, source_type
        ORDER BY citation_count DESC
        LIMIT @limit
        """
        params = [
            bigquery.ScalarQueryParameter("start_date", "TIMESTAMP", request.start_date),
            bigquery.ScalarQueryParameter("end_date", "TIMESTAMP", request.end_date),
            bigquery.ScalarQueryParameter("brand_id", "STRING", request.brand_id),
            bigquery.ScalarQueryParameter("limit", "INT64", request.limit),
        ]
        rows = self._execute_query(sql, params)

        citations = []
        for row in rows:
            citations.append(
                CitationDataPoint(
                    domain=row.get("domain") or "",
                    source_type=row.get("source_type") or "",
                    count=int(row.get("citation_count") or 0),
                )
            )

        return CitationAnalysisResult(brand_id=request.brand_id, top_citations=citations)

    def find_fanout_gaps(self, request: FanoutGapRequest) -> FanoutGapResult:
        sql = f"""
        SELECT
            query_text,
            tool,
            COUNT(*) as miss_count
        FROM `{self.project_id}.{self.dataset_id}.{TABLE_FANOUT_OBSERVATIONS}`
        WHERE started_at >= @start_date AND started_at <= @end_date
            AND brand_id = @brand_id
            AND brand_found = FALSE
        GROUP BY query_text, tool
        ORDER BY miss_count DESC
        LIMIT @limit
        """
        params = [
            bigquery.ScalarQueryParameter("start_date", "TIMESTAMP", request.start_date),
            bigquery.ScalarQueryParameter("end_date", "TIMESTAMP", request.end_date),
            bigquery.ScalarQueryParameter("brand_id", "STRING", request.brand_id),
            bigquery.ScalarQueryParameter("limit", "INT64", request.limit),
        ]
        rows = self._execute_query(sql, params)

        gaps = []
        for row in rows:
            gaps.append(
                FanoutGapDataPoint(
                    query_text=row.get("query_text") or "",
                    tool=row.get("tool") or "",
                    miss_count=int(row.get("miss_count") or 0),
                )
            )

        return FanoutGapResult(brand_id=request.brand_id, gaps=gaps)
