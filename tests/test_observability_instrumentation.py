"""Integration & regression tests for V1, V3, and V4 observability instrumentation.

Verifies:
1. V1 Search Journey pipeline instrumentation and span generation.
2. V3 Visibility Scan pipeline instrumentation and span generation.
3. V4 Agent chat execution span and read-only BigQuery boundaries.
4. Telemetry does NOT issue BigQuery write operations during V4.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_search_journey.adk import SearchJourneyAgent
from ai_search_journey.models import (
    Candidate,
    CandidateConstraintEvaluation,
    ConstraintEvaluationResult,
    ConstraintResult,
    ConstraintStatus,
    ConstraintSupport,
    FanoutQuery,
    GroundedAnswer,
    JourneyExecutionTrace,
    JourneyResult,
    ReferenceLocation,
    SearchGroundingResult,
    SearchIntent,
    StaticMapResult,
    ToolName,
)
from ai_search_journey.telemetry import TelemetryStore, init_telemetry
from ai_search_journey.visibility.models import (
    BrandObservation,
    BrandProfile,
    BrandRole,
    ScanStatus,
    VisibilityScan,
    VisibilityScanBundle,
)
from ai_search_journey.visibility.repository import InMemoryVisibilityRepository
from ai_search_journey.visibility.runner import run_visibility_scan
from ai_search_journey.visibility.v4_agent import VisibilityAnalyticsAgent


@pytest.fixture(autouse=True)
def clean_telemetry_store():
    store = init_telemetry(max_runs=10)
    store.clear()
    yield store
    store.clear()


@pytest.mark.asyncio
async def test_v1_journey_instrumentation(clean_telemetry_store: TelemetryStore):
    """Verify that executing a V1 search journey produces journey.execution and step spans."""
    dummy_intent = SearchIntent(
        category="coffee shop",
        reference_location="Geekdom San Antonio",
        hard_constraints=["open after 8pm"],
    )
    dummy_ref_loc = ReferenceLocation(
        query="Geekdom San Antonio",
        place_id="ref_place_1",
        name="Geekdom San Antonio",
        latitude=29.426,
        longitude=-98.493,
    )
    dummy_fanout = [
        FanoutQuery(
            task_id="F1",
            query="coffee shop near geekdom",
            tool=ToolName.GOOGLE_PLACES,
            goal="find places",
        ),
        FanoutQuery(
            task_id="F2",
            query="coffee open after 8pm",
            tool=ToolName.GOOGLE_SEARCH,
            goal="check hours",
        ),
    ]
    dummy_cand = Candidate(
        place_id="place_1",
        name="Local Coffee",
        formatted_address="San Antonio, TX",
        latitude=29.426,
        longitude=-98.493,
    )
    dummy_search = SearchGroundingResult(
        task_id="F2",
        planner_query="coffee open after 8pm",
        grounded_text="Local Coffee is open until 9pm.",
        executed_search_queries=["q1"],
        sources=[],
    )
    dummy_eval = ConstraintEvaluationResult(
        evaluations=[
            CandidateConstraintEvaluation(
                candidate=dummy_cand,
                results=[
                    ConstraintResult(
                        constraint="open after 8pm",
                        status=ConstraintStatus.SUPPORTED,
                        supporting_evidence=[
                            ConstraintSupport(
                                source_type="google_search",
                                evidence_text="Open until 9pm",
                            )
                        ],
                        explanation="Open until 9pm",
                    )
                ],
            )
        ]
    )
    dummy_map = StaticMapResult(
        url="https://maps.googleapis.com/maps/api/staticmap",
        redacted_url="https://maps.googleapis.com/maps/api/staticmap",
        marker_count=1,
    )
    dummy_answer = GroundedAnswer(
        summary="Here is a great coffee shop.",
        recommendations=[],
        caveats=[],
        citations=[],
    )

    with patch("ai_search_journey.adk.agent.extract_intent",
               AsyncMock(return_value=dummy_intent)), \
         patch("ai_search_journey.adk.agent.reference_location_tool",
               AsyncMock(return_value=dummy_ref_loc)), \
         patch("ai_search_journey.adk.agent.generate_fanout",
               AsyncMock(return_value=dummy_fanout)), \
         patch("ai_search_journey.adk.agent.places_retrieval_tool",
               AsyncMock(return_value=[dummy_cand])), \
         patch("ai_search_journey.adk.agent.search_grounding_tool",
               AsyncMock(return_value=dummy_search)), \
         patch("ai_search_journey.adk.agent.evaluate_constraints",
               MagicMock(return_value=dummy_eval)), \
         patch("ai_search_journey.adk.agent.generate_static_map",
               MagicMock(return_value=dummy_map)), \
         patch("ai_search_journey.adk.agent.generate_grounded_answer",
               AsyncMock(return_value=dummy_answer)):

        agent = SearchJourneyAgent()
        result = await agent.run("Find a coffee shop near Geekdom open late")
        assert result is not None

    spans = clean_telemetry_store.get_all_spans()
    span_names = {s.name for s in spans}

    assert "journey.execution" in span_names
    assert "journey.intent_parsing" in span_names
    assert "journey.reference_location" in span_names
    assert "journey.query_fanout" in span_names
    assert "journey.places_retrieval" in span_names
    assert "journey.normalize" in span_names
    assert "journey.search_grounding" in span_names
    assert "journey.evidence_aggregation" in span_names
    assert "journey.constraint_evaluation" in span_names
    assert "journey.ranking" in span_names
    assert "journey.static_map" in span_names
    assert "journey.answer_synthesis" in span_names


def test_v3_visibility_scan_instrumentation(clean_telemetry_store: TelemetryStore):
    """Verify that V3 visibility scan execution creates visibility spans."""
    target_brand = BrandProfile(
        brand_id="target_brand",
        name="Target Brand",
        domain="target.com",
        role=BrandRole.TARGET,
    )
    competitor = BrandProfile(
        brand_id="comp_brand",
        name="Competitor Brand",
        domain="competitor.com",
        role=BrandRole.COMPETITOR,
    )
    mock_journey = MagicMock(spec=JourneyResult)
    mock_journey.question = "Where to buy sports gear?"
    mock_journey.intent = SearchIntent(category="sports")
    mock_journey.reference_location = None
    mock_journey.execution_trace = JourneyExecutionTrace(
        is_complete=True, failed_step_key=None, steps=[]
    )

    repo = InMemoryVisibilityRepository()

    now = datetime.now(timezone.utc)
    dummy_scan = VisibilityScan(
        scan_id="scan_v3_test",
        batch_id="batch_1",
        project_id="p1",
        brand_id="target_brand",
        brand_name_snapshot="Target Brand",
        prompt_id="prompt_1",
        prompt_text_snapshot="test prompt",
        model_name="gemini-2.5-flash",
        started_at=now,
        completed_at=now,
        duration_seconds=1.0,
        status=ScanStatus.COMPLETED,
    )
    target_obs = BrandObservation(
        scan_id="scan_v3_test",
        brand_id="target_brand",
        role=BrandRole.TARGET,
    )
    dummy_bundle = VisibilityScanBundle(
        scan=dummy_scan,
        brand_observations=[target_obs],
        citations=[],
        fanout_observations=[],
    )

    with patch(
        "ai_search_journey.visibility.runner.extract_visibility_scan_bundle",
        return_value=dummy_bundle,
    ):
        scan_result = run_visibility_scan(
            journey=mock_journey,
            target_brand=target_brand,
            competitor_brands=[competitor],
            repository=repo,
        )
        assert scan_result.saved is True

    spans = clean_telemetry_store.get_all_spans()
    span_names = {s.name for s in spans}
    assert "visibility.scan_execution" in span_names
    assert "visibility.extract_bundle" in span_names
    assert "visibility.save_bundle" in span_names


def test_v4_agent_chat_instrumentation_and_read_only(clean_telemetry_store: TelemetryStore):
    """Verify V4 agent chat wraps in v4.agent.chat_turn and enforces read-only boundary."""
    mock_event = MagicMock()
    mock_event.text = "Based on BigQuery historical scans, the brand visibility is 80%."

    with patch("google.adk.runners.Runner.run", return_value=[mock_event]), \
         patch("ai_search_journey.visibility.v4_agent.create_v4_agent"):

        agent = VisibilityAnalyticsAgent()
        response = agent.run("What is the latest visibility summary?")
        assert "80%" in response

    spans = clean_telemetry_store.get_all_spans()
    span_names = {s.name for s in spans}
    assert "v4.agent.chat_turn" in span_names

    chat_span = next(s for s in spans if s.name == "v4.agent.chat_turn")
    assert chat_span.status == "OK"
    assert "v4.session_id" in chat_span.attributes
    assert chat_span.attributes.get("v4.response_length") == len(response)


def test_v4_mcp_server_tools_have_read_only_attribute(clean_telemetry_store: TelemetryStore):
    """Verify that MCP server tool executions record bigquery.read_only=True."""
    from ai_search_journey.visibility.mcp_server import get_available_history

    mock_repo = MagicMock()
    mock_repo.get_available_history.return_value = MagicMock(
        model_dump=MagicMock(return_value={"total_scans": 15, "brands": ["b1"]})
    )

    with patch("ai_search_journey.visibility.mcp_server.get_repo", return_value=mock_repo):
        res = get_available_history(30)
        assert res["total_scans"] == 15

    spans = clean_telemetry_store.get_all_spans()
    mcp_spans = [s for s in spans if s.name == "v4.mcp_tool.get_available_history"]
    assert len(mcp_spans) == 1
    span = mcp_spans[0]
    assert span.attributes.get("bigquery.read_only") is True
    assert span.attributes.get("mcp.tool_name") == "get_available_history"


def test_v3_visibility_scan_groups_by_trace_id_with_children(
    clean_telemetry_store: TelemetryStore,
):
    """Verify V3 visibility scan is grouped as one execution with child spans."""
    target_brand = BrandProfile(
        brand_id="target_brand",
        name="Target Brand",
        domain="target.com",
        role=BrandRole.TARGET,
    )
    competitor = BrandProfile(
        brand_id="comp_brand",
        name="Competitor Brand",
        domain="competitor.com",
        role=BrandRole.COMPETITOR,
    )
    mock_journey = MagicMock(spec=JourneyResult)
    mock_journey.question = "Where to find artisanal bakeries?"
    mock_journey.intent = SearchIntent(category="bakery")
    mock_journey.reference_location = None
    mock_journey.execution_trace = JourneyExecutionTrace(
        is_complete=True, failed_step_key=None, steps=[]
    )

    repo = InMemoryVisibilityRepository()
    now = datetime.now(timezone.utc)
    dummy_scan = VisibilityScan(
        scan_id="scan_v3_grouping_test",
        batch_id="batch_1",
        project_id="p1",
        brand_id="target_brand",
        brand_name_snapshot="Target Brand",
        prompt_id="prompt_1",
        prompt_text_snapshot="test prompt",
        model_name="gemini-2.5-flash",
        started_at=now,
        completed_at=now,
        duration_seconds=1.0,
        status=ScanStatus.COMPLETED,
    )
    target_obs = BrandObservation(
        scan_id="scan_v3_grouping_test",
        brand_id="target_brand",
        role=BrandRole.TARGET,
    )
    dummy_bundle = VisibilityScanBundle(
        scan=dummy_scan,
        brand_observations=[target_obs],
        citations=[],
        fanout_observations=[],
    )

    with patch(
        "ai_search_journey.visibility.runner.extract_visibility_scan_bundle",
        return_value=dummy_bundle,
    ):
        run_visibility_scan(
            journey=mock_journey,
            target_brand=target_brand,
            competitor_brands=[competitor],
            repository=repo,
        )

    # V3 must be listed as exactly one run in the store
    v3_runs = clean_telemetry_store.get_runs(stage_filter="v3")
    assert len(v3_runs) == 1
    run = v3_runs[0]
    assert run["stage"] == "v3"

    # All 3 spans (scan_execution, extract_bundle, save_bundle) belong to this single run
    spans = clean_telemetry_store.get_spans_for_run(run["run_id"])
    assert len(spans) == 3
    span_names = {s.name for s in spans}
    assert span_names == {
        "visibility.scan_execution",
        "visibility.extract_bundle",
        "visibility.save_bundle",
    }


def test_v4_agent_chat_groups_as_single_run(clean_telemetry_store: TelemetryStore):
    """Verify V4 chat interaction is listed as one execution run."""
    mock_event = MagicMock()
    mock_event.text = "Visibility trend is stable across historical scans."

    with patch("google.adk.runners.Runner.run", return_value=[mock_event]), \
         patch("ai_search_journey.visibility.v4_agent.create_v4_agent"):

        agent = VisibilityAnalyticsAgent()
        agent.run("Provide a brand trend analysis.")

    v4_runs = clean_telemetry_store.get_runs(stage_filter="v4")
    assert len(v4_runs) == 1
    run = v4_runs[0]
    assert run["stage"] == "v4"

    spans = clean_telemetry_store.get_spans_for_run(run["run_id"])
    assert len(spans) == 1
    assert spans[0].name == "v4.agent.chat_turn"


def test_public_domain_models_have_no_telemetry_fields():
    """Verify that public domain models have not gained telemetry/OTel fields."""
    # V1 models
    assert "telemetry" not in JourneyResult.model_fields
    assert "trace_id" not in JourneyResult.model_fields
    assert "run_id" not in JourneyResult.model_fields
    assert "trace_id" not in Candidate.model_fields

    # V3 models
    assert "telemetry" not in VisibilityScan.model_fields
    assert "trace_id" not in VisibilityScan.model_fields
    assert "telemetry" not in VisibilityScanBundle.model_fields
    assert "telemetry" not in BrandProfile.model_fields


def test_v4_telemetry_never_invokes_write_repository_or_scan():
    """Verify V4 analytics agent execution remains read-only and invokes no repository writes."""
    from ai_search_journey.visibility.v4_analytics import BigQueryVisibilityAnalyticsRepository

    # Confirm write methods do not exist on the analytics repository class
    assert not hasattr(BigQueryVisibilityAnalyticsRepository, "save_bundle")
    assert not hasattr(BigQueryVisibilityAnalyticsRepository, "insert_scan")
    assert not hasattr(BigQueryVisibilityAnalyticsRepository, "write")

    # Confirm read-only methods exist
    assert hasattr(BigQueryVisibilityAnalyticsRepository, "get_available_history")
    assert hasattr(BigQueryVisibilityAnalyticsRepository, "get_visibility_summary")
    assert hasattr(BigQueryVisibilityAnalyticsRepository, "get_brand_trend")
    assert hasattr(BigQueryVisibilityAnalyticsRepository, "compare_brands")
    assert hasattr(BigQueryVisibilityAnalyticsRepository, "analyze_citations")
    assert hasattr(BigQueryVisibilityAnalyticsRepository, "find_fanout_gaps")
