import os
from datetime import datetime
from typing import Any

from mcp.server.mcpserver import MCPServer

from ai_search_journey.visibility.v4_analytics import (
    BigQueryVisibilityAnalyticsRepository,
    BrandTrendRequest,
    BrandTrendResult,
    CitationAnalysisRequest,
    CitationAnalysisResult,
    CompetitorComparisonRequest,
    CompetitorComparisonResult,
    FanoutGapRequest,
    FanoutGapResult,
    VisibilityAnalyticsRepository,
    VisibilitySummaryRequest,
    VisibilitySummaryResult,
)

server = MCPServer("AI Visibility Analytics V4")

# Initialize repository (Mock fallback for tests/offline demo)
class LocalMockRepo:
    def get_visibility_summary(self, request: Any) -> Any:
        return VisibilitySummaryResult(
            brand_id=request.brand_id,
            total_scans=0,
            mention_rate=0.0,
            recommendation_rate=0.0,
            citation_rate=0.0
        )
    def get_brand_trend(self, request: Any) -> Any:
        return BrandTrendResult(brand_id=request.brand_id, trends=[])
    def compare_brands(self, request: Any) -> Any:
        return CompetitorComparisonResult(metrics=[])
    def analyze_citations(self, request: Any) -> Any:
        return CitationAnalysisResult(brand_id=request.brand_id, top_citations=[])
    def find_fanout_gaps(self, request: Any) -> Any:
        return FanoutGapResult(brand_id=request.brand_id, gaps=[])

def _get_repository() -> VisibilityAnalyticsRepository:
    if os.environ.get("USE_MOCK_VISIBILITY_REPO") == "1":
        return LocalMockRepo() 
    try:
        return BigQueryVisibilityAnalyticsRepository(
            project_id=os.environ.get("GOOGLE_CLOUD_PROJECT", "test-project")
        )
    except Exception:
        return LocalMockRepo()

repo = _get_repository()

@server.tool()
def get_visibility_summary(start_date: str, end_date: str, brand_id: str) -> dict[str, Any]:
    """Aggregates overall brand visibility for a date range
    (mention, recommendation, citation rates)."""
    sd = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
    ed = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    req = VisibilitySummaryRequest.model_validate({
        "start_date": sd, "end_date": ed, "brand_id": brand_id
    })
    return repo.get_visibility_summary(req).model_dump()

@server.tool()
def get_brand_trend(start_date: str, end_date: str, brand_id: str) -> dict[str, Any]:
    """Returns chronological data points showing how a brand's
    visibility metrics have changed over time."""
    sd = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
    ed = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    req = BrandTrendRequest.model_validate({
        "start_date": sd, "end_date": ed, "brand_id": brand_id
    })
    return repo.get_brand_trend(req).model_dump()

@server.tool()
def compare_brands(start_date: str, end_date: str, brand_ids: list[str]) -> dict[str, Any]:
    """Directly compares the visibility metrics of multiple brands side-by-side."""
    sd = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
    ed = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    req = CompetitorComparisonRequest.model_validate({
        "start_date": sd, "end_date": ed, "brand_ids": brand_ids
    })
    return repo.compare_brands(req).model_dump()

@server.tool()
def analyze_citations(
    start_date: str, end_date: str, brand_id: str, limit: int = 10
) -> dict[str, Any]:
    """Analyzes which domains and source types are most frequently
    cited when a brand is mentioned."""
    sd = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
    ed = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    req = CitationAnalysisRequest.model_validate({
        "start_date": sd, "end_date": ed, "brand_id": brand_id, "limit": limit
    })
    return repo.analyze_citations(req).model_dump()

@server.tool()
def find_fanout_gaps(
    start_date: str, end_date: str, brand_id: str, limit: int = 20
) -> dict[str, Any]:
    """Examines query fan-outs to identify specific long-tail queries
    where the brand was NOT found."""
    sd = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
    ed = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
    req = FanoutGapRequest.model_validate({
        "start_date": sd, "end_date": ed, "brand_id": brand_id, "limit": limit
    })
    return repo.find_fanout_gaps(req).model_dump()

if __name__ == "__main__":
    server.run()
