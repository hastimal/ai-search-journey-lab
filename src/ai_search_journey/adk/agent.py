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

import time
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
    GroundedAnswer,
    JourneyExecutionTrace,
    JourneyResult,
    JourneyStepTiming,
    ReferenceLocation,
    SearchGroundingResult,
    StepExecutionStatus,
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

INITIAL_JOURNEY_STEPS: list[tuple[str, str]] = [
    ("intent", "Understanding intent"),
    ("reference_location", "Resolving reference location"),
    ("fanout", "Planning query fan-out"),
    ("places", "Retrieving Google Places candidates"),
    ("normalize", "Normalizing candidates"),
    ("search", "Grounding qualitative evidence with Search"),
    ("evidence", "Aggregating multi-source evidence"),
    ("constraints", "Evaluating constraints"),
    ("ranking", "Ranking candidates deterministically"),
    ("static_map", "Building Map preview"),
    ("answer", "Generating grounded answer"),
]


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
        on_step_update: Optional[
            Callable[[Optional[JourneyStepTiming], JourneyExecutionTrace], None]
        ] = None,
    ) -> JourneyResult:
        """Execute the full search journey orchestration for a user question.

        Args:
            question: The natural language search request.
            on_trace: Optional callback for raw trace string events.
            on_step_update: Optional callback for live step status and timing updates.

        Returns:
            JourneyResult containing complete trace, state, evaluation matrix, and recommendations.
        """
        trace_steps: list[str] = []
        overall_start_time = time.perf_counter()

        # Initialize structured execution trace
        step_timings = [
            JourneyStepTiming(key=key, label=label, status=StepExecutionStatus.PENDING)
            for key, label in INITIAL_JOURNEY_STEPS
        ]
        step_map = {st.key: st for st in step_timings}
        execution_trace = JourneyExecutionTrace(steps=step_timings)

        def trace(msg: str) -> None:
            formatted = f"[ADK] {msg}"
            trace_steps.append(formatted)
            if on_trace:
                on_trace(formatted)

        def notify_step(step: Optional[JourneyStepTiming]) -> None:
            if on_step_update:
                on_step_update(step, execution_trace)

        notify_step(None)
        trace(f"Initiating Search Journey orchestration for: '{question}'")

        # ---------------- 1. Structured Intent Extraction ----------------
        step_intent = step_map["intent"]
        step_intent.status = StepExecutionStatus.RUNNING
        notify_step(step_intent)
        t0 = time.perf_counter()
        try:
            intent = await extract_intent(question)
            step_intent.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_intent.status = StepExecutionStatus.COMPLETED
            step_intent.detail = f"Category: '{intent.category}'"
            notify_step(step_intent)
            trace(
                f"Intent extraction complete: category='{intent.category}', "
                f"reference_location='{intent.reference_location}', "
                f"open_after='{intent.open_after}', group_size={intent.group_size}"
            )
        except Exception as e:
            step_intent.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_intent.status = StepExecutionStatus.FAILED
            step_intent.error = str(e)
            execution_trace.failed_step_key = "intent"
            notify_step(step_intent)
            raise

        # ---------------- 2. Reference Location Resolution ----------------
        step_ref = step_map["reference_location"]
        step_ref.status = StepExecutionStatus.RUNNING
        notify_step(step_ref)
        t0 = time.perf_counter()
        ref_loc: Optional[ReferenceLocation] = None
        try:
            if intent.reference_location:
                ref_loc = await reference_location_tool(intent.reference_location)
                if ref_loc:
                    step_ref.detail = f"Resolved: '{ref_loc.name}'"
                    trace(
                        f"Resolved reference location: '{ref_loc.name}' at "
                        f"({ref_loc.latitude:.4f}, {ref_loc.longitude:.4f})"
                    )
                else:
                    step_ref.detail = f"Not resolved: '{intent.reference_location}'"
                    trace(
                        f"Could not resolve reference location for: '{intent.reference_location}'"
                    )
            else:
                step_ref.detail = "No reference location requested"
                trace("No reference location specified in intent")
            step_ref.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_ref.status = StepExecutionStatus.COMPLETED
            notify_step(step_ref)
        except Exception as e:
            step_ref.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_ref.status = StepExecutionStatus.FAILED
            step_ref.error = str(e)
            execution_trace.failed_step_key = "reference_location"
            notify_step(step_ref)
            raise

        # ---------------- 3. Dynamic Query Fan-Out ----------------
        step_fanout = step_map["fanout"]
        step_fanout.status = StepExecutionStatus.RUNNING
        notify_step(step_fanout)
        t0 = time.perf_counter()
        try:
            fanout = await generate_fanout(intent)
            step_fanout.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_fanout.status = StepExecutionStatus.COMPLETED
            p_cnt = len([q for q in fanout if q.tool == ToolName.GOOGLE_PLACES])
            s_cnt = len([q for q in fanout if q.tool == ToolName.GOOGLE_SEARCH])
            step_fanout.detail = f"{p_cnt} Places · {s_cnt} Search tasks ({len(fanout)} total)"
            notify_step(step_fanout)
            trace(f"Fan-out generated: {len(fanout)} tasks")
        except Exception as e:
            step_fanout.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_fanout.status = StepExecutionStatus.FAILED
            step_fanout.error = str(e)
            execution_trace.failed_step_key = "fanout"
            notify_step(step_fanout)
            raise

        # ---------------- 4. Retrieval Tool Execution (Places) ----------------
        step_places = step_map["places"]
        step_places.status = StepExecutionStatus.RUNNING
        notify_step(step_places)
        t0 = time.perf_counter()
        places_tasks = [q for q in fanout if q.tool == ToolName.GOOGLE_PLACES]
        raw_candidate_groups: list[list[Candidate]] = []
        try:
            for task in places_tasks:
                candidates = await places_retrieval_tool(
                    query=task.query,
                    task_id=task.task_id,
                    goal=task.goal,
                    max_results=10,
                )
                raw_candidate_groups.append(candidates)
            total_raw = sum(len(grp) for grp in raw_candidate_groups)
            step_places.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_places.status = StepExecutionStatus.COMPLETED
            step_places.detail = f"{len(places_tasks)} tasks · {total_raw} raw results"
            notify_step(step_places)
            trace(f"Places tasks executed: {len(places_tasks)}")
        except Exception as e:
            step_places.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_places.status = StepExecutionStatus.FAILED
            step_places.error = str(e)
            execution_trace.failed_step_key = "places"
            notify_step(step_places)
            raise

        # ---------------- 5. Candidate Normalization ----------------
        step_norm = step_map["normalize"]
        step_norm.status = StepExecutionStatus.RUNNING
        notify_step(step_norm)
        t0 = time.perf_counter()
        try:
            canonical_candidates = normalize_candidates(
                raw_candidate_groups,
                reference_location=intent.reference_location,
            )
            step_norm.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_norm.status = StepExecutionStatus.COMPLETED
            dupes_removed = max(0, total_raw - len(canonical_candidates))
            step_norm.detail = (
                f"{total_raw} raw records → {len(canonical_candidates)} unique candidates "
                f"({dupes_removed} duplicates removed)"
            )
            notify_step(step_norm)
            trace(f"Candidates normalized: {len(canonical_candidates)} unique places")
        except Exception as e:
            step_norm.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_norm.status = StepExecutionStatus.FAILED
            step_norm.error = str(e)
            execution_trace.failed_step_key = "normalize"
            notify_step(step_norm)
            raise

        # ---------------- 6. Web Grounding Tool Execution (Search) ----------------
        step_search = step_map["search"]
        step_search.status = StepExecutionStatus.RUNNING
        notify_step(step_search)
        t0 = time.perf_counter()
        search_tasks = [q for q in fanout if q.tool == ToolName.GOOGLE_SEARCH]
        search_results: list[SearchGroundingResult] = []
        try:
            for task in search_tasks:
                res = await search_grounding_tool(
                    query=task.query,
                    task_id=task.task_id,
                    goal=task.goal,
                )
                search_results.append(res)
            total_queries = sum(len(r.executed_search_queries) for r in search_results)
            total_sources = sum(len(r.sources) for r in search_results)
            step_search.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_search.status = StepExecutionStatus.COMPLETED
            step_search.detail = (
                f"{len(search_tasks)} tasks · {total_queries} queries · {total_sources} sources"
            )
            notify_step(step_search)
            trace(f"Search tasks executed: {len(search_tasks)}")
        except Exception as e:
            step_search.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_search.status = StepExecutionStatus.FAILED
            step_search.error = str(e)
            execution_trace.failed_step_key = "search"
            notify_step(step_search)
            raise

        # ---------------- 7. Evidence Aggregation ----------------
        step_evidence = step_map["evidence"]
        step_evidence.status = StepExecutionStatus.RUNNING
        notify_step(step_evidence)
        t0 = time.perf_counter()
        try:
            primary_places_task_id = places_tasks[0].task_id if places_tasks else "F1"
            evidence_result = aggregate_evidence(
                canonical_candidates,
                search_results,
                places_task_id=primary_places_task_id,
            )
            all_evidence = []
            for ce in evidence_result.candidates:
                all_evidence.extend(ce.structured_evidence)
                all_evidence.extend(ce.search_evidence)
            step_evidence.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_evidence.status = StepExecutionStatus.COMPLETED
            step_evidence.detail = (
                f"{len(all_evidence)} claims across "
                f"{len(evidence_result.candidates)} candidates"
            )
            notify_step(step_evidence)
            trace("Evidence aggregated across Places and Search sources")
        except Exception as e:
            step_evidence.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_evidence.status = StepExecutionStatus.FAILED
            step_evidence.error = str(e)
            execution_trace.failed_step_key = "evidence"
            notify_step(step_evidence)
            raise

        # ---------------- 8. Deterministic Constraint Evaluation ----------------
        step_constraints = step_map["constraints"]
        step_constraints.status = StepExecutionStatus.RUNNING
        notify_step(step_constraints)
        t0 = time.perf_counter()
        try:
            constraint_matrix = evaluate_constraints(intent, evidence_result.candidates)
            step_constraints.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_constraints.status = StepExecutionStatus.COMPLETED
            step_constraints.detail = (
                f"{len(constraint_matrix.evaluations)} candidate matrices evaluated"
            )
            notify_step(step_constraints)
            trace("Constraint evaluation complete")
        except Exception as e:
            step_constraints.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_constraints.status = StepExecutionStatus.FAILED
            step_constraints.error = str(e)
            execution_trace.failed_step_key = "constraints"
            notify_step(step_constraints)
            raise

        # ---------------- 9. Deterministic Explainable Ranking ----------------
        step_ranking = step_map["ranking"]
        step_ranking.status = StepExecutionStatus.RUNNING
        notify_step(step_ranking)
        t0 = time.perf_counter()
        try:
            ranked_all = rank_candidates(constraint_matrix, reference_location=ref_loc)
            top_candidates = ranked_all[:3]
            step_ranking.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_ranking.status = StepExecutionStatus.COMPLETED
            step_ranking.detail = (
                f"{len(ranked_all)} candidates → Top {len(top_candidates)} selected"
            )
            notify_step(step_ranking)
            trace(f"Ranking complete: Top {len(top_candidates)} selected deterministically")
        except Exception as e:
            step_ranking.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_ranking.status = StepExecutionStatus.FAILED
            step_ranking.error = str(e)
            execution_trace.failed_step_key = "ranking"
            notify_step(step_ranking)
            raise

        # ---------------- 10. Google Maps Static API Preview ----------------
        step_map_preview = step_map["static_map"]
        step_map_preview.status = StepExecutionStatus.RUNNING
        notify_step(step_map_preview)
        t0 = time.perf_counter()
        static_map_result = None
        try:
            static_map_result = generate_static_map(top_candidates, max_candidates=3)
            step_map_preview.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_map_preview.status = StepExecutionStatus.COMPLETED
            step_map_preview.detail = f"{static_map_result.marker_count} map markers generated"
            notify_step(step_map_preview)
            trace(f"Static map generated: {static_map_result.marker_count} markers")
        except ValueError as val_err:
            step_map_preview.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_map_preview.status = StepExecutionStatus.COMPLETED
            step_map_preview.detail = "Map preview skipped (no coordinates)"
            notify_step(step_map_preview)
            trace(f"Static map preview skipped: {val_err}")
        except Exception as e:
            step_map_preview.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_map_preview.status = StepExecutionStatus.FAILED
            step_map_preview.error = str(e)
            execution_trace.failed_step_key = "static_map"
            notify_step(step_map_preview)
            raise

        # ---------------- 11. Grounded Final Answer Synthesis ----------------
        step_ans = step_map["answer"]
        step_ans.status = StepExecutionStatus.RUNNING
        notify_step(step_ans)
        t0 = time.perf_counter()
        grounded_answer: Optional[GroundedAnswer] = None
        try:
            grounded_answer = await generate_grounded_answer(
                question=question,
                intent=intent,
                ranked_candidates=top_candidates,
                max_candidates=3,
                on_trace=trace,
            )
            step_ans.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_ans.status = StepExecutionStatus.COMPLETED
            step_ans.detail = f"{len(grounded_answer.recommendations)} candidate recommendations"
            notify_step(step_ans)
            trace("Final grounded answer generated")
        except Exception as e:
            step_ans.duration_seconds = round(max(0.0, time.perf_counter() - t0), 3)
            step_ans.status = StepExecutionStatus.FAILED
            step_ans.error = str(e)
            step_ans.detail = "Grounded answer unavailable"
            execution_trace.failed_step_key = "answer"
            notify_step(step_ans)
            trace(f"Grounded answer generation unavailable: {e}")

        # Finalize execution trace
        total_duration = round(max(0.0, time.perf_counter() - overall_start_time), 3)
        execution_trace.total_duration_seconds = total_duration
        execution_trace.is_complete = True
        notify_step(None)

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
            execution_trace=execution_trace,
        )

