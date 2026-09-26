import os
from datetime import datetime
from typing import Any

from mcp.server.mcpserver import MCPServer

from ai_search_journey.config import settings
from ai_search_journey.telemetry import trace_span
from ai_search_journey.visibility.v4_analytics import (
    AvailableHistoryRequest,
    BigQueryVisibilityAnalyticsRepository,
    BrandTrendRequest,
    CitationAnalysisRequest,
    CompetitorComparisonRequest,
    FanoutGapRequest,
    VisibilityAnalyticsRepository,
    VisibilitySummaryRequest,
)

server = MCPServer("AI Visibility Analytics V4")


def _get_repository() -> VisibilityAnalyticsRepository:
    project_id = (
        settings.bigquery_project
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("BIGQUERY_PROJECT")
    )
    if not project_id:
        raise RuntimeError("BigQuery repository unavailable: BIGQUERY_PROJECT not configured")
    try:
        return BigQueryVisibilityAnalyticsRepository(
            project_id=project_id,
            dataset_id=settings.bigquery_dataset,
            location=settings.bigquery_location,
        )
    except Exception as e:
        raise RuntimeError(f"BigQuery repository unavailable: {e}") from e


repo: VisibilityAnalyticsRepository | None = None


def get_repo() -> VisibilityAnalyticsRepository:
    global repo
    if repo is None:
        repo = _get_repository()
    return repo


@server.tool()
def get_available_history(lookback_days: int = 365) -> dict[str, Any]:
    """Discovers available historical scan metadata, date bounds, total scans,
    distinct brands, and recent scan windows in BigQuery."""
    with trace_span(
        "v4.mcp_tool.get_available_history",
        attributes={
            "mcp.tool_name": "get_available_history",
            "mcp.lookback_days": lookback_days,
            "bigquery.read_only": True,
        },
    ) as s_span:
        req = AvailableHistoryRequest(lookback_days=lookback_days)
        result = get_repo().get_available_history(req).model_dump()
        if s_span.is_recording():
            s_span.set_attribute("history.total_scans", result.get("total_scans", 0))
        return result


@server.tool()
def get_visibility_summary(start_date: str, end_date: str, brand_id: str) -> dict[str, Any]:
    """Aggregates overall brand visibility for a date range
    (mention, recommendation, citation rates)."""
    with trace_span(
        "v4.mcp_tool.get_visibility_summary",
        attributes={
            "mcp.tool_name": "get_visibility_summary",
            "mcp.brand_id": brand_id,
            "bigquery.read_only": True,
        },
    ):
        sd = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        ed = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        req = VisibilitySummaryRequest.model_validate({
            "start_date": sd, "end_date": ed, "brand_id": brand_id
        })
        return get_repo().get_visibility_summary(req).model_dump()

@server.tool()
def get_brand_trend(start_date: str, end_date: str, brand_id: str) -> dict[str, Any]:
    """Returns chronological data points showing how a brand's
    visibility metrics have changed over time."""
    with trace_span(
        "v4.mcp_tool.get_brand_trend",
        attributes={
            "mcp.tool_name": "get_brand_trend",
            "mcp.brand_id": brand_id,
            "bigquery.read_only": True,
        },
    ):
        sd = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        ed = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        req = BrandTrendRequest.model_validate({
            "start_date": sd, "end_date": ed, "brand_id": brand_id
        })
        return get_repo().get_brand_trend(req).model_dump()

@server.tool()
def compare_brands(start_date: str, end_date: str, brand_ids: list[str]) -> dict[str, Any]:
    """Directly compares the visibility metrics of multiple brands side-by-side."""
    with trace_span(
        "v4.mcp_tool.compare_brands",
        attributes={
            "mcp.tool_name": "compare_brands",
            "mcp.brand_count": len(brand_ids),
            "bigquery.read_only": True,
        },
    ):
        sd = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        ed = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        req = CompetitorComparisonRequest.model_validate({
            "start_date": sd, "end_date": ed, "brand_ids": brand_ids
        })
        return get_repo().compare_brands(req).model_dump()

@server.tool()
def analyze_citations(
    start_date: str, end_date: str, brand_id: str, limit: int = 10
) -> dict[str, Any]:
    """Analyzes which domains and source types are most frequently
    cited when a brand is mentioned."""
    with trace_span(
        "v4.mcp_tool.analyze_citations",
        attributes={
            "mcp.tool_name": "analyze_citations",
            "mcp.brand_id": brand_id,
            "mcp.limit": limit,
            "bigquery.read_only": True,
        },
    ):
        sd = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        ed = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        req = CitationAnalysisRequest.model_validate({
            "start_date": sd, "end_date": ed, "brand_id": brand_id, "limit": limit
        })
        return get_repo().analyze_citations(req).model_dump()

@server.tool()
def find_fanout_gaps(
    start_date: str, end_date: str, brand_id: str, limit: int = 20
) -> dict[str, Any]:
    """Examines query fan-outs to identify specific long-tail queries
    where the brand was NOT found."""
    with trace_span(
        "v4.mcp_tool.find_fanout_gaps",
        attributes={
            "mcp.tool_name": "find_fanout_gaps",
            "mcp.brand_id": brand_id,
            "mcp.limit": limit,
            "bigquery.read_only": True,
        },
    ):
        sd = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        ed = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        req = FanoutGapRequest.model_validate({
            "start_date": sd, "end_date": ed, "brand_id": brand_id, "limit": limit
        })
        return get_repo().find_fanout_gaps(req).model_dump()

if __name__ == "__main__":
    server.run()
