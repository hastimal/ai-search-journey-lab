"""Google ADK Search Journey Root Agent.

Orchestrates the complete search journey using Google ADK design principles:
- Agents reason and plan (Intent Extraction, Fan-Out, Final Grounded Synthesis).
- Tools retrieve data (Google Places, Google Search Grounding, Reference Location).
- Deterministic code evaluates (Candidate Normalization, Evidence Aggregation,
  Constraint Evaluation, Explainable Scoring, Proximity, Ranking, Static Map URL).

Strict Rules:
- ADK must NOT decide final rank itself.
- ADK must NOT override Python scoring.
- ADK must NOT fabricate search or places results.
- ADK preserves UNKNOWN != FALSE and multi-source provenance.
"""

from typing import Any, Callable, Optional

from ai_search_journey.adk.tools import (
    places_retrieval_tool,
    reference_location_tool,
    search_grounding_tool,
)
from ai_search_journey.answer import generate_grounded_answer
from ai_search_journey.constraints import evaluate_constraints
from ai_search_journey.evidence import aggregate_evidence
from ai_search_journey.fanout import generate_fanout
from ai_search_journey.models import (
    Candidate,
    JourneyResult,
    ReferenceLocation,
    SearchGroundingResult,
    ToolName,
)
from ai_search_journey.normalize import normalize_candidates
from ai_search_journey.planner import extract_intent
from ai_search_journey.ranking import rank_candidates
from ai_search_journey.static_map import generate_static_map

SEARCH_JOURNEY_AGENT_INSTRUCTIONS = """You are the Search Journey Agent for AI Search Journey Lab.
Your role is to orchestrate structured, grounded local discovery searches.

Strict Guidelines:
1. Use the provided tools and pipelines. Do not hallucinate or fabricate candidate venues.
2. Never override or bypass deterministic ranking and scoring.
3. Candidate order in the final answer must strictly match the deterministic ranking.
4. Preserve UNKNOWN constraint status and multi-source evidence provenance.
5. Provide helpful, grounded explanations without inventing features.
"""


class SearchJourneyAgent:
    """Primary ADK root agent responsible for orchestrating the search journey."""

    def __init__(
        self,
        name: str = "SearchJourneyAgent",
        instructions: str = SEARCH_JOURNEY_AGENT_INSTRUCTIONS,
        tools: Optional[list[Callable[..., Any]]] = None,
    ) -> None:
        self.name = name
        self.instructions = instructions
        self.tools = tools or [
            places_retrieval_tool,
            search_grounding_tool,
            reference_location_tool,
        ]

    async def run(
        self,
        question: str,
        *,
        on_trace: Optional[Callable[[str], None]] = None,
    ) -> JourneyResult:
        """Execute the full search journey orchestration for a user question.

        Args:
            question: The natural language search request.
            on_trace: Optional callback for live step tracing events.

        Returns:
            JourneyResult containing complete trace, state, evaluation matrix, and recommendations.
        """
        trace_steps: list[str] = []

        def trace(msg: str) -> None:
            formatted = f"[ADK] {msg}"
            trace_steps.append(formatted)
            if on_trace:
                on_trace(formatted)

        trace(f"Initiating Search Journey orchestration for: '{question}'")

        # 1. Structured Intent Extraction
        intent = await extract_intent(question)
        trace(
            f"Intent extraction complete: category='{intent.category}', "
            f"reference_location='{intent.reference_location}', "
            f"open_after='{intent.open_after}', group_size={intent.group_size}"
        )

        # 2. Reference Location Resolution (if present)
        ref_loc: Optional[ReferenceLocation] = None
        if intent.reference_location:
            ref_loc = await reference_location_tool(intent.reference_location)
            if ref_loc:
                trace(
                    f"Resolved reference location: '{ref_loc.name}' at "
                    f"({ref_loc.latitude:.4f}, {ref_loc.longitude:.4f})"
                )
            else:
                trace(f"Could not resolve reference location for: '{intent.reference_location}'")

        # 3. Dynamic Query Fan-Out
        fanout = await generate_fanout(intent)
        trace(f"Fan-out generated: {len(fanout)} tasks")

        # 4. Retrieval Tool Execution
        places_tasks = [q for q in fanout if q.tool == ToolName.GOOGLE_PLACES]
        raw_candidate_groups: list[list[Candidate]] = []
        for task in places_tasks:
            candidates = await places_retrieval_tool(
                query=task.query,
                task_id=task.task_id,
                goal=task.goal,
                max_results=10,
            )
            raw_candidate_groups.append(candidates)
        trace(f"Places tasks executed: {len(places_tasks)}")

        # 5. Candidate Normalization
        canonical_candidates = normalize_candidates(
            raw_candidate_groups,
            reference_location=intent.reference_location,
        )
        trace(f"Candidates normalized: {len(canonical_candidates)} unique places")

        # 6. Web Grounding Tool Execution
        search_tasks = [q for q in fanout if q.tool == ToolName.GOOGLE_SEARCH]
        search_results: list[SearchGroundingResult] = []
        for task in search_tasks:
            res = await search_grounding_tool(
                query=task.query,
                task_id=task.task_id,
                goal=task.goal,
            )
            search_results.append(res)
        trace(f"Search tasks executed: {len(search_tasks)}")

        # 7. Evidence Aggregation
        primary_places_task_id = places_tasks[0].task_id if places_tasks else "F1"
        evidence_result = aggregate_evidence(
            canonical_candidates,
            search_results,
            places_task_id=primary_places_task_id,
        )
        trace("Evidence aggregated across Places and Search sources")

        # 8. Deterministic Constraint Evaluation
        constraint_matrix = evaluate_constraints(intent, evidence_result.candidates)
        trace("Constraint evaluation complete")

        # 9. Deterministic Explainable Ranking
        ranked_all = rank_candidates(constraint_matrix, reference_location=ref_loc)
        top_candidates = ranked_all[:3]
        trace(f"Ranking complete: Top {len(top_candidates)} selected deterministically")

        # 10. Google Maps Static API Preview (if coordinates are available)
        static_map_result = None
        try:
            static_map_result = generate_static_map(top_candidates, max_candidates=3)
            trace(f"Static map generated: {static_map_result.marker_count} markers")
        except ValueError as val_err:
            trace(f"Static map preview skipped: {val_err}")

        # 11. Grounded Final Answer Synthesis
        grounded_answer = await generate_grounded_answer(
            question=question,
            intent=intent,
            ranked_candidates=top_candidates,
            max_candidates=3,
        )
        trace("Final grounded answer generated")

        # Collect all flat evidence items for legacy JourneyResult compatibility
        all_evidence = []
        for ce in evidence_result.candidates:
            all_evidence.extend(ce.structured_evidence)
            all_evidence.extend(ce.search_evidence)

        return JourneyResult(
            question=question,
            intent=intent,
            fanout=fanout,
            reference_location=ref_loc,
            candidates=canonical_candidates,
            search_results=search_results,
            evidence_result=evidence_result,
            constraint_result=constraint_matrix,
            evidence=all_evidence,
            ranking=ranked_all,
            static_map=static_map_result,
            answer=grounded_answer,
            trace_steps=trace_steps,
        )
