"""Gemini Grounded Final Answer module for AI Search Journey."""

import json
from typing import Any, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from ai_search_journey.config import settings
from ai_search_journey.models import (
    ConstraintStatus,
    FinalRecommendation,
    GroundedAnswer,
    RankedCandidate,
    SearchIntent,
)


class GeminiRecommendationItem(BaseModel):
    """Internal Pydantic schema for a single recommendation item in Gemini response."""

    rank: int
    candidate_name: str
    summary: str
    why_it_matches: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    evidence_sources: list[str] = Field(default_factory=list)


class GeminiGroundedAnswerResponse(BaseModel):
    """Internal Pydantic schema for structured Gemini response."""

    answer_summary: str
    recommendations: list[GeminiRecommendationItem] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


ANSWER_SYSTEM_INSTRUCTION = (
    "You are an expert AI search synthesist for local discovery. Your task is to generate "
    "a concise, grounded final recommendation explaining the deterministically ranked "
    "Top candidates.\n\n"
    "CRITICAL GROUNDING AND TRUTHFULNESS RULES:\n"
    "1. PRESERVE CANDIDATE IDENTITY AND RANKING: You MUST preserve the exact candidates, "
    "exact names, and exact ranking order supplied in the input. Do NOT reorder candidates. "
    "Do NOT introduce new businesses. Do NOT alter rank numbers.\n"
    "2. STRICT EVIDENCE BOUNDARY: Use ONLY the supplied structured constraint evaluation results, "
    "distances, and evidence snippets. Do NOT invent facts, amenities, or hours.\n"
    "3. HONEST THREE-WAY STATUS REPRESENTATION:\n"
    "   - SUPPORTED: Describe as verified positive reasons ('why_it_matches') with source "
    "provenance (e.g. 'Google Places [F1]').\n"
    "   - UNKNOWN: Describe explicitly as unverified or missing evidence in 'unknowns' "
    "(e.g. 'Group seating for 6 is unverified'). "
    "NEVER describe UNKNOWN constraints as supported, verified, or positive attributes.\n"
    "   - NOT_SATISFIED: Clearly state the conflict in 'conflicts' "
    "(e.g. 'Fails late-night requirement: closes at 8 PM').\n"
    "4. CALIBRATED RECOMMENDATION LANGUAGE: Avoid hyperbolic guarantees like 'perfect'. "
    "Use calibrated phrases like 'best-supported match based on available evidence', "
    "'appears to meet', 'evidence is missing for'.\n"
    "5. PRESERVE PROVENANCE: In 'why_it_matches' and 'evidence_sources', clearly mention the "
    "supporting tool source (Google Places, Google Search) and task IDs (e.g. [F1], [F3]) "
    "or web source titles where provided.\n"
    "6. CAVEATS: Highlight general limitations, unverified assumptions, or tips to verify "
    "details before visiting."
)


def _format_candidate_evidence_payload(
    ranked_candidates: list[RankedCandidate],
    max_candidates: int = 3,
) -> list[dict[str, Any]]:
    """Prepare clean, compact structured payload of Top candidates for Gemini explanation."""
    payload: list[dict[str, Any]] = []
    candidates_to_explain = ranked_candidates[:max_candidates]

    for cand_ranked in candidates_to_explain:
        cand = cand_ranked.candidate

        supported_constraints: list[dict[str, Any]] = []
        unknown_constraints: list[str] = []
        failed_constraints: list[dict[str, Any]] = []

        for r in cand_ranked.constraint_results:
            if r.status == ConstraintStatus.SUPPORTED:
                sources_info: list[str] = []
                for s in r.supporting_evidence:
                    src_label = (
                        "Google Places"
                        if s.source_type == "google_places"
                        else "Google Search"
                    )
                    tids = f" [{','.join(s.fanout_task_ids)}]" if s.fanout_task_ids else ""
                    title = f" - '{s.source_title}'" if s.source_title else ""
                    sources_info.append(f"{src_label}{tids}{title}")

                supported_constraints.append({
                    "constraint": r.constraint,
                    "explanation": r.explanation,
                    "sources": sources_info or ["Google Places"],
                    "evidence_snippet": r.evidence_text[:150] if r.evidence_text else None,
                })
            elif r.status == ConstraintStatus.NOT_SATISFIED:
                failed_constraints.append({
                    "constraint": r.constraint,
                    "explanation": r.explanation or "Not satisfied based on evidence",
                })
            else:
                unknown_constraints.append(r.constraint)

        payload.append({
            "rank": cand_ranked.rank,
            "candidate_name": cand.name,
            "score": cand_ranked.score,
            "address": cand.formatted_address,
            "distance_miles": cand_ranked.distance_miles,
            "proximity_bonus": cand_ranked.proximity_score,
            "rating": cand.rating,
            "user_rating_count": cand.user_rating_count,
            "google_maps_url": cand.google_maps_url,
            "supported_constraints": supported_constraints,
            "unknown_constraints": unknown_constraints,
            "failed_constraints": failed_constraints,
            "ranking_reasons": cand_ranked.ranking_reasons,
        })

    return payload


def _collect_citations_from_ranked(
    ranked_candidates: list[RankedCandidate],
    max_candidates: int = 3,
) -> list[str]:
    """Collect unique web citations and URLs from candidate evidence."""
    citations: list[str] = []
    for cand_ranked in ranked_candidates[:max_candidates]:
        for r in cand_ranked.constraint_results:
            for s in r.supporting_evidence:
                if s.source_url and s.source_url not in citations:
                    citations.append(s.source_url)
    return citations


def _validate_and_assemble_grounded_answer(
    raw_response: GeminiGroundedAnswerResponse,
    ranked_candidates: list[RankedCandidate],
    max_candidates: int = 3,
) -> GroundedAnswer:
    """Validate Gemini response strictly against ground truth ranking and assemble GroundedAnswer.

    Validation Rules:
    - Must return exactly the expected number of recommendations.
    - Candidate names must match the input candidate names exactly in identical order.
    - Rank numbers must match 1-indexed integers in order.
    - Preserves canonical Google Maps URLs without modification.
    """
    expected_candidates = ranked_candidates[:max_candidates]
    if len(raw_response.recommendations) != len(expected_candidates):
        raise ValueError(
            f"Gemini returned {len(raw_response.recommendations)} recommendations; "
            f"expected exactly {len(expected_candidates)}."
        )

    final_recs: list[FinalRecommendation] = []

    for idx, (gen_rec, expected) in enumerate(
        zip(raw_response.recommendations, expected_candidates, strict=True)
    ):
        expected_rank = idx + 1
        expected_name = expected.candidate.name

        if gen_rec.rank != expected_rank:
            raise ValueError(
                f"Gemini altered candidate rank at position {idx}: "
                f"got rank {gen_rec.rank}, expected {expected_rank}."
            )

        # Exact or clean normalized name match check
        if gen_rec.candidate_name.strip().lower() != expected_name.strip().lower():
            raise ValueError(
                f"Gemini introduced unknown or reordered candidate name at rank {expected_rank}: "
                f"got '{gen_rec.candidate_name}', expected '{expected_name}'."
            )

        # Gather sources from raw response or fallback to candidate evidence
        sources = gen_rec.evidence_sources
        if not sources:
            sources = []
            for r in expected.constraint_results:
                for s in r.supporting_evidence:
                    src_label = (
                        "Google Places"
                        if s.source_type == "google_places"
                        else "Google Search"
                    )
                    tids = f" [{','.join(s.fanout_task_ids)}]" if s.fanout_task_ids else ""
                    label = f"{src_label}{tids}"
                    if label not in sources:
                        sources.append(label)

        final_recs.append(
            FinalRecommendation(
                rank=expected_rank,
                candidate_name=expected_name,
                summary=gen_rec.summary,
                why_it_matches=gen_rec.why_it_matches,
                unknowns=gen_rec.unknowns,
                conflicts=gen_rec.conflicts,
                evidence_sources=sources,
                maps_url=expected.candidate.google_maps_url,
            )
        )

    citations = _collect_citations_from_ranked(ranked_candidates, max_candidates=max_candidates)

    return GroundedAnswer(
        summary=raw_response.answer_summary,
        recommendations=final_recs,
        caveats=raw_response.caveats,
        citations=citations,
    )


async def generate_grounded_answer(
    question: str,
    intent: SearchIntent,
    ranked_candidates: list[RankedCandidate],
    *,
    max_candidates: int = 3,
    client: Optional[genai.Client] = None,
) -> GroundedAnswer:
    """Generate a concise, grounded final answer from deterministically ranked Top candidates.

    Args:
        question: Original user query.
        intent: Structured SearchIntent.
        ranked_candidates: List of RankedCandidate models from deterministic ranking.
        max_candidates: Number of top candidates to explain (default: 3).
        client: Optional Google GenAI Client (useful for dependency injection / testing).

    Returns:
        GroundedAnswer Pydantic model containing structured summary and recommendations.

    Raises:
        ValueError: If input candidates list is empty or validation fails.
        RuntimeError: If Gemini API fails.
    """
    if not ranked_candidates:
        raise ValueError("Cannot generate grounded answer for empty ranked candidates list.")

    candidates_payload = _format_candidate_evidence_payload(
        ranked_candidates, max_candidates=max_candidates
    )

    prompt_payload = {
        "user_question": question,
        "search_intent": intent.model_dump(),
        "top_ranked_candidates": candidates_payload,
    }

    prompt_json = json.dumps(prompt_payload, indent=2)

    if client is None:
        api_key = settings.gemini_api_key
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not configured.")
        client = genai.Client(api_key=api_key)

    try:
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt_json,
            config=types.GenerateContentConfig(
                system_instruction=ANSWER_SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=GeminiGroundedAnswerResponse,
            ),
        )
    except Exception as exc:
        raise RuntimeError(f"Gemini API request failed during answer generation: {exc}") from exc

    raw_response: Optional[GeminiGroundedAnswerResponse] = None

    if hasattr(response, "parsed") and isinstance(response.parsed, GeminiGroundedAnswerResponse):
        raw_response = response.parsed
    elif hasattr(response, "text") and response.text:
        try:
            raw_response = GeminiGroundedAnswerResponse.model_validate_json(response.text)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to parse Gemini answer response as GeminiGroundedAnswerResponse: {exc}"
            ) from exc

    if raw_response is None:
        raise RuntimeError("Gemini API returned an empty or unparseable answer response.")

    return _validate_and_assemble_grounded_answer(
        raw_response,
        ranked_candidates,
        max_candidates=max_candidates,
    )
