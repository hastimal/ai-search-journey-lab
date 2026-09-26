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
            "mcp.brand_count": len(brand_ids) if brand_ids else 0,
            "bigquery.read_only": True,
        },
    ) as s_span:
        if not brand_ids or not isinstance(brand_ids, list):
            return {
                "error": "brand_ids must be a non-empty list of brand IDs",
                "metrics": [],
            }

        # Deduplicate while preserving first-seen input order
        seen: set[str] = set()
        deduped_brand_ids: list[str] = []
        for bid in brand_ids:
            if isinstance(bid, str) and bid.strip():
                clean_bid = bid.strip()
                if clean_bid not in seen:
                    seen.add(clean_bid)
                    deduped_brand_ids.append(clean_bid)

        if not deduped_brand_ids:
            return {
                "error": "No valid non-blank brand IDs provided",
                "metrics": [],
            }

        if len(deduped_brand_ids) > 50:
            return {
                "error": (
                    f"Too many brand IDs requested ({len(deduped_brand_ids)}). "
                    "Maximum supported is 50."
                ),
                "metrics": [],
            }

        try:
            sd = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            ed = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        except Exception as date_err:
            return {
                "error": f"Invalid ISO 8601 date format: {date_err}",
                "metrics": [],
            }

        # If only 1 brand is provided, compare_brands requires at least 2 in repo schema.
        # But for robustness, if 1 brand is passed, query it as a 1-item batch or summary.
        # However, CompetitorComparisonRequest has min_length=2. To safely support 1 brand,
        # duplicate it in the request or query get_visibility_summary and wrap in metrics.
        # If >= 2 brands, batch in chunks of at most 10.
        combined_metrics: list[dict[str, Any]] = []
        repo_inst = get_repo()

        if len(deduped_brand_ids) == 1:
            try:
                single_req = VisibilitySummaryRequest(
                    start_date=sd, end_date=ed, brand_id=deduped_brand_ids[0]
                )
                single_res = repo_inst.get_visibility_summary(single_req)
                combined_metrics.append(single_res.model_dump())
            except Exception as e:
                return {"error": f"Failed comparing single brand: {e}", "metrics": []}
        else:
            # Split into deterministic chunks of at most 10
            chunk_size = 10
            for i in range(0, len(deduped_brand_ids), chunk_size):
                chunk = deduped_brand_ids[i:i + chunk_size]
                # If a final remainder chunk has only 1 brand, we can pad with the first brand
                # and filter out duplicates from the result
                query_chunk = chunk
                if len(chunk) == 1:
                    query_chunk = [chunk[0], deduped_brand_ids[0]]

                try:
                    req = CompetitorComparisonRequest.model_validate({
                        "start_date": sd, "end_date": ed, "brand_ids": query_chunk
                    })
                    chunk_res = repo_inst.compare_brands(req).model_dump()
                    chunk_metrics = chunk_res.get("metrics", [])
                    # Keep only metrics for the chunk
                    chunk_brand_set = set(chunk)
                    for m in chunk_metrics:
                        bid = m.get("brand_id")
                        if bid in chunk_brand_set and not any(
                            existing.get("brand_id") == bid for existing in combined_metrics
                        ):
                            combined_metrics.append(m)
                except Exception as batch_err:
                    return {
                        "error": f"Failed evaluating brand batch {chunk}: {batch_err}",
                        "metrics": combined_metrics,
                    }

        if s_span.is_recording():
            s_span.set_attribute("compare.result_count", len(combined_metrics))

        return {"metrics": combined_metrics}

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
