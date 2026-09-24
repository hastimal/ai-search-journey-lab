from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest

from ai_search_journey.adk.agent import (
    SearchJourneyAgent,
)
from ai_search_journey.adk.tools import (
    places_retrieval_tool,
    reference_location_tool,
    search_grounding_tool,
)
from ai_search_journey.models import (
    Candidate,
    ConstraintStatus,
    FanoutQuery,
    GroundedAnswer,
    JourneyExecutionTrace,
    JourneyResult,
    JourneyStepTiming,
    ReferenceLocation,
    SearchGroundingResult,
    SearchIntent,
    ToolName,
)


def test_adk_root_agent_initialization() -> None:
    """ADK root agent is initialized with instructions and tools."""
    agent = SearchJourneyAgent()
    assert agent.name == "SearchJourneyAgent"
    assert "You are the Search Journey Agent" in agent.instructions
    assert len(agent.tools) == 3
    assert places_retrieval_tool in agent.tools
    assert search_grounding_tool in agent.tools
    assert reference_location_tool in agent.tools


@pytest.mark.asyncio
async def test_existing_retrieval_functions_wrapped_correctly() -> None:
    """ADK tools correctly wrap existing places, search, and reference location functions."""
    with (
        patch("ai_search_journey.adk.tools.search_places", new_callable=AsyncMock) as mock_places,
        patch("ai_search_journey.adk.tools.search_web", new_callable=AsyncMock) as mock_search,
        patch(
            "ai_search_journey.adk.tools.resolve_reference_location",
            new_callable=AsyncMock,
        ) as mock_ref,
    ):
        mock_places.return_value = [Candidate(place_id="p1", name="Place 1")]
        mock_search.return_value = SearchGroundingResult(
            planner_query="test", grounded_text="info"
        )
        mock_ref.return_value = ReferenceLocation(
            query="Geekdom",
            place_id="ref1",
            name="Geekdom",
            latitude=29.426,
            longitude=-98.493,
        )

        res_places = await places_retrieval_tool("coffee shops", task_id="F1")
        assert len(res_places) == 1
        assert res_places[0].name == "Place 1"
        assert mock_places.call_count == 1

        res_search = await search_grounding_tool("coffee reviews", task_id="F2")
        assert res_search.grounded_text == "info"
        assert mock_search.call_count == 1

        res_ref = await reference_location_tool("Geekdom")
        assert res_ref is not None
        assert res_ref.name == "Geekdom"
        assert mock_ref.call_count == 1


@pytest.mark.asyncio
async def test_adk_orchestration_preserves_ranking_order_and_scores() -> None:
    """ADK orchestration maintains exact deterministic ranking order, scores, and provenance."""
    sample_intent = SearchIntent(
        category="coffee shop",
        reference_location="Geekdom San Antonio",
        open_after="20:00",
        group_size=6,
        preferences=["quiet"],
    )

    c1 = Candidate(
        place_id="c1",
        name="Candidate One",
        primary_type="coffee_shop",
        place_types=["coffee_shop", "cafe"],
        latitude=29.426,
        longitude=-98.493,
        rating=4.8,
        user_rating_count=500,
        opening_hours=["Monday: 7:00 AM – 10:00 PM"],
    )
    c2 = Candidate(
        place_id="c2",
        name="Candidate Two",
        primary_type="coffee_shop",
        place_types=["coffee_shop"],
        latitude=29.428,
        longitude=-98.490,
        rating=4.2,
        user_rating_count=100,
        opening_hours=["Monday: 7:00 AM – 9:00 PM"],
    )

    ref = ReferenceLocation(
        query="Geekdom San Antonio",
        place_id="ref_g",
        name="Geekdom",
        latitude=29.4262,
        longitude=-98.4935,
    )

    fanout = [
        FanoutQuery(task_id="F1", goal="Discovery", query="coffee", tool=ToolName.GOOGLE_PLACES),
        FanoutQuery(task_id="F2", goal="Atmosphere", query="quiet", tool=ToolName.GOOGLE_SEARCH),
    ]

    with (
        patch(
            "ai_search_journey.adk.agent.extract_intent", new_callable=AsyncMock
        ) as mock_intent,
        patch(
            "ai_search_journey.adk.agent.reference_location_tool", new_callable=AsyncMock
        ) as mock_ref,
        patch(
            "ai_search_journey.adk.agent.generate_fanout", new_callable=AsyncMock
        ) as mock_fanout,
        patch(
            "ai_search_journey.adk.agent.places_retrieval_tool", new_callable=AsyncMock
        ) as mock_places,
        patch(
            "ai_search_journey.adk.agent.search_grounding_tool", new_callable=AsyncMock
        ) as mock_search,
        patch(
            "ai_search_journey.adk.agent.generate_grounded_answer", new_callable=AsyncMock
        ) as mock_ans,
    ):
        mock_intent.return_value = sample_intent
        mock_ref.return_value = ref
        mock_fanout.return_value = fanout
        mock_places.return_value = [c1, c2]
        mock_search.return_value = SearchGroundingResult(
            task_id="F2", planner_query="quiet", grounded_text="Candidate One is quiet."
        )
        mock_ans.return_value = GroundedAnswer(
            summary="Top recommendations",
            recommendations=[],
        )

        trace_log: list[str] = []
        agent = SearchJourneyAgent()
        journey = await agent.run(
            "Find a coffee shop near Geekdom for 6 people open after 8 PM",
            on_trace=lambda step: trace_log.append(step),
        )

        assert isinstance(journey, JourneyResult)
        assert len(journey.ranking) == 2
        # Deterministic ranking order: Candidate One has higher rating and closer proximity
        assert journey.ranking[0].candidate.name == "Candidate One"
        assert journey.ranking[1].candidate.name == "Candidate Two"
        assert journey.ranking[0].score > journey.ranking[1].score

        # Verification of JourneyResult major stages
        assert journey.intent == sample_intent
        assert journey.reference_location == ref
        assert len(journey.fanout) == 2
        assert len(journey.candidates) == 2
        assert len(journey.search_results) == 1
        assert journey.evidence_result is not None
        assert journey.constraint_result is not None
        assert journey.static_map is not None
        assert journey.answer is not None
        assert len(journey.trace_steps) >= 8
        assert len(trace_log) >= 8

        # Verify static map markers match ranked order
        assert journey.static_map.markers[0].candidate_name == "Candidate One"
        assert journey.static_map.markers[0].label == "A"
        assert journey.static_map.markers[1].candidate_name == "Candidate Two"
        assert journey.static_map.markers[1].label == "B"

        # Verify category eligibility constraint survived in evaluation
        assert journey.ranking[0].category_eligibility is not None
        assert journey.ranking[0].category_eligibility.status == ConstraintStatus.SUPPORTED


@pytest.mark.asyncio
async def test_adk_does_not_fabricate_candidates_or_convert_unknown() -> None:
    """ADK does not introduce hallucinated candidates and preserves UNKNOWN constraint status."""
    sample_intent = SearchIntent(
        category="coffee shop",
        group_size=6,
        preferences=["quiet"],
    )
    c1 = Candidate(
        place_id="c1",
        name="Quiet Unknown Corner",
        primary_type="coffee_shop",
        place_types=["coffee_shop"],
    )

    with (
        patch(
            "ai_search_journey.adk.agent.extract_intent", new_callable=AsyncMock
        ) as mock_intent,
        patch(
            "ai_search_journey.adk.agent.reference_location_tool", new_callable=AsyncMock
        ) as mock_ref,
        patch(
            "ai_search_journey.adk.agent.generate_fanout", new_callable=AsyncMock
        ) as mock_fanout,
        patch(
            "ai_search_journey.adk.agent.places_retrieval_tool", new_callable=AsyncMock
        ) as mock_places,
        patch(
            "ai_search_journey.adk.agent.search_grounding_tool", new_callable=AsyncMock
        ) as mock_search,
        patch(
            "ai_search_journey.adk.agent.generate_grounded_answer", new_callable=AsyncMock
        ) as mock_ans,
    ):
        mock_intent.return_value = sample_intent
        mock_ref.return_value = None
        mock_fanout.return_value = [
            FanoutQuery(
                task_id="F1", goal="Discovery", query="coffee", tool=ToolName.GOOGLE_PLACES
            )
        ]
        mock_places.return_value = [c1]
        mock_search.return_value = SearchGroundingResult(
            task_id="F2", planner_query="quiet", grounded_text=""
        )
        mock_ans.return_value = GroundedAnswer(summary="Result", recommendations=[])

        agent = SearchJourneyAgent()
        journey = await agent.run("Find a coffee shop")

        assert len(journey.candidates) == 1
        assert journey.candidates[0].name == "Quiet Unknown Corner"

        # Check that missing group size / quiet evidence remains UNKNOWN
        assert journey.constraint_result is not None
        results = journey.constraint_result.evaluations[0].results
        group_res = [r for r in results if "Group size" in r.constraint]
        assert len(group_res) == 1
        assert group_res[0].status == ConstraintStatus.UNKNOWN


@pytest.mark.asyncio
async def test_adk_step_timing_transitions_and_trace() -> None:
    """Verify step transitions (pending -> running -> completed), non-negative duration, trace."""
    sample_intent = SearchIntent(category="coffee shop")
    c1 = Candidate(place_id="c1", name="Place 1", primary_type="coffee_shop")

    updates_received: list[tuple[str, str]] = []

    def on_step(step: object, trace: object) -> None:
        if step is not None:
            k = getattr(step, "key", "")
            st = getattr(step, "status", "")
            val = getattr(st, "value", str(st))
            updates_received.append((k, val))

    with (
        patch(
            "ai_search_journey.adk.agent.extract_intent", new_callable=AsyncMock
        ) as mock_intent,
        patch(
            "ai_search_journey.adk.agent.reference_location_tool", new_callable=AsyncMock
        ) as mock_ref,
        patch(
            "ai_search_journey.adk.agent.generate_fanout", new_callable=AsyncMock
        ) as mock_fanout,
        patch(
            "ai_search_journey.adk.agent.places_retrieval_tool", new_callable=AsyncMock
        ) as mock_places,
        patch(
            "ai_search_journey.adk.agent.search_grounding_tool", new_callable=AsyncMock
        ) as mock_search,
        patch(
            "ai_search_journey.adk.agent.generate_grounded_answer", new_callable=AsyncMock
        ) as mock_ans,
    ):
        mock_intent.return_value = sample_intent
        mock_ref.return_value = None
        mock_fanout.return_value = [
            FanoutQuery(
                task_id="F1", goal="Discovery", query="coffee", tool=ToolName.GOOGLE_PLACES
            )
        ]
        mock_places.return_value = [c1]
        mock_search.return_value = SearchGroundingResult(
            task_id="F2", planner_query="test", grounded_text=""
        )
        mock_ans.return_value = GroundedAnswer(summary="Answer", recommendations=[])

        agent = SearchJourneyAgent()
        journey = await agent.run("Find coffee", on_step_update=on_step)

        # Trace exists and completed
        assert journey.execution_trace is not None
        assert journey.execution_trace.is_complete is True
        assert journey.execution_trace.total_duration_seconds is not None
        assert journey.execution_trace.total_duration_seconds >= 0.0

        # Steps are all completed and have non-negative durations
        for st in journey.execution_trace.steps:
            assert st.status.value == "completed"
            assert st.duration_seconds is not None
            assert st.duration_seconds >= 0.0
            # Ensure no API keys appear in detail or label
            assert "AIza" not in (st.detail or "")
            assert "AIza" not in st.label

        # Verify step transitions recorded in callback
        statuses_by_key: dict[str, list[str]] = {}
        for k, s in updates_received:
            statuses_by_key.setdefault(k, []).append(s)

        for key in ["intent", "fanout", "places", "normalize", "ranking", "answer"]:
            assert "running" in statuses_by_key.get(key, [])
            assert "completed" in statuses_by_key.get(key, [])


@pytest.mark.asyncio
async def test_adk_step_failure_captured_in_trace() -> None:
    """Verify failing step is marked as failed and trace captures failed_step_key."""
    with patch(
        "ai_search_journey.adk.agent.extract_intent", new_callable=AsyncMock
    ) as mock_intent:
        mock_intent.side_effect = RuntimeError("Gemini API connection error")

        agent = SearchJourneyAgent()
        last_trace: Optional[JourneyExecutionTrace] = None

        def on_step(step: Optional[JourneyStepTiming], trace: JourneyExecutionTrace) -> None:
            nonlocal last_trace
            last_trace = trace

        with pytest.raises(RuntimeError, match="Gemini API connection error"):
            await agent.run("Find coffee", on_step_update=on_step)

        assert last_trace is not None
        assert last_trace.failed_step_key == "intent"
        intent_step = [s for s in last_trace.steps if s.key == "intent"][0]
        assert intent_step.status.value == "failed"
        assert "Gemini API connection error" in (intent_step.error or "")


@pytest.mark.asyncio
async def test_adk_answer_failure_retains_retrieval_and_ranking() -> None:
    """Verify journey completes and retains rankings/evidence when answer synthesis fails."""
    sample_intent = SearchIntent(category="coffee shop")
    c1 = Candidate(place_id="c1", name="Place Alpha", primary_type="coffee_shop")

    with (
        patch(
            "ai_search_journey.adk.agent.extract_intent", new_callable=AsyncMock
        ) as mock_intent,
        patch(
            "ai_search_journey.adk.agent.reference_location_tool", new_callable=AsyncMock
        ) as mock_ref,
        patch(
            "ai_search_journey.adk.agent.generate_fanout", new_callable=AsyncMock
        ) as mock_fanout,
        patch(
            "ai_search_journey.adk.agent.places_retrieval_tool", new_callable=AsyncMock
        ) as mock_places,
        patch(
            "ai_search_journey.adk.agent.search_grounding_tool", new_callable=AsyncMock
        ) as mock_search,
        patch(
            "ai_search_journey.adk.agent.generate_grounded_answer", new_callable=AsyncMock
        ) as mock_ans,
    ):
        mock_intent.return_value = sample_intent
        mock_ref.return_value = None
        mock_fanout.return_value = [
            FanoutQuery(
                task_id="F1", goal="Discovery", query="coffee", tool=ToolName.GOOGLE_PLACES
            )
        ]
        mock_places.return_value = [c1]
        mock_search.return_value = SearchGroundingResult(
            task_id="F2", planner_query="test", grounded_text=""
        )
        mock_ans.side_effect = RuntimeError("Gemini models unavailable on all retries")

        agent = SearchJourneyAgent()
        journey = await agent.run("Find coffee")

        # Journey is returned successfully with answer=None
        assert journey is not None
        assert journey.answer is None
        assert len(journey.ranking) == 1
        assert journey.ranking[0].candidate.name == "Place Alpha"
        assert journey.execution_trace is not None
        assert journey.execution_trace.is_complete is True
        assert journey.execution_trace.failed_step_key == "answer"

        ans_step = [s for s in journey.execution_trace.steps if s.key == "answer"][0]
        assert ans_step.status.value == "failed"
        assert ans_step.detail == "Grounded answer unavailable"
