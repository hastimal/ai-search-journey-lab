"""Evidence aggregation module combining Places candidates and Search grounding."""

import re
from typing import Optional

from ai_search_journey.models import (
    Candidate,
    CandidateEvidence,
    Evidence,
    EvidenceAggregationResult,
    EvidenceSource,
    SearchGroundingResult,
    SearchSource,
)

GENERIC_STOP_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "in",
    "at",
    "near",
    "of",
    "for",
    "to",
    "co",
    "inc",
    "llc",
    "bar",
    "cafe",
    "coffee",
    "restaurant",
    "shop",
    "place",
    "kitchen",
    "cuisine",
}


def normalize_name(name: str) -> str:
    """Normalize a place or business name for robust deterministic entity matching.

    - Converts to lowercase
    - Replaces punctuation and special characters with spaces
    - Collapses multiple whitespace characters and strips edges
    """
    if not name:
        return ""
    # Strip markdown bolding/italics e.g. **Halcyon Southtown**
    cleaned = re.sub(r"[*_`#]+", "", name.lower())
    # Replace non-alphanumeric characters with spaces
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    # Collapse multiple whitespace
    return " ".join(cleaned.split())


def _get_meaningful_tokens(normalized_name: str) -> set[str]:
    """Get non-generic tokens for safe matching validation."""
    tokens = set(normalized_name.split())
    meaningful = tokens - GENERIC_STOP_WORDS
    return meaningful if meaningful else tokens


def _places_to_structured_evidence(
    candidate: Candidate,
    fanout_task_id: Optional[str] = None,
) -> list[Evidence]:
    """Extract structured factual evidence items from a canonical Candidate model."""
    evidence_list: list[Evidence] = []
    pid = candidate.place_id

    task_ids = candidate.retrieval_task_ids or ([fanout_task_id] if fanout_task_id else [])
    formatted_task_id = ", ".join(task_ids) if task_ids else fanout_task_id

    if candidate.formatted_address:
        evidence_list.append(
            Evidence(
                candidate_id=pid,
                attribute="formatted_address",
                claim=f"Address: {candidate.formatted_address}",
                source=EvidenceSource.GOOGLE_PLACES,
                source_url=candidate.google_maps_url,
                fanout_task_id=formatted_task_id,
                fanout_task_ids=task_ids,
            )
        )

    if candidate.rating is not None:
        reviews_str = (
            f" ({candidate.user_rating_count} reviews)"
            if candidate.user_rating_count is not None
            else ""
        )
        evidence_list.append(
            Evidence(
                candidate_id=pid,
                attribute="rating",
                claim=f"Rating: {candidate.rating}{reviews_str}",
                source=EvidenceSource.GOOGLE_PLACES,
                source_url=candidate.google_maps_url,
                fanout_task_id=formatted_task_id,
                fanout_task_ids=task_ids,
            )
        )

    if candidate.opening_hours:
        evidence_list.append(
            Evidence(
                candidate_id=pid,
                attribute="opening_hours",
                claim=f"Opening Hours: {'; '.join(candidate.opening_hours)}",
                source=EvidenceSource.GOOGLE_PLACES,
                source_url=candidate.google_maps_url,
                fanout_task_id=formatted_task_id,
                fanout_task_ids=task_ids,
            )
        )

    if candidate.website_url:
        evidence_list.append(
            Evidence(
                candidate_id=pid,
                attribute="website_url",
                claim=f"Website: {candidate.website_url}",
                source=EvidenceSource.GOOGLE_PLACES,
                source_url=candidate.website_url,
                fanout_task_id=formatted_task_id,
                fanout_task_ids=task_ids,
            )
        )

    if candidate.google_maps_url:
        evidence_list.append(
            Evidence(
                candidate_id=pid,
                attribute="google_maps_url",
                claim=f"Google Maps URL: {candidate.google_maps_url}",
                source=EvidenceSource.GOOGLE_PLACES,
                source_url=candidate.google_maps_url,
                fanout_task_id=formatted_task_id,
                fanout_task_ids=task_ids,
            )
        )

    if candidate.latitude is not None and candidate.longitude is not None:
        evidence_list.append(
            Evidence(
                candidate_id=pid,
                attribute="location",
                claim=f"Location coordinates: ({candidate.latitude}, {candidate.longitude})",
                source=EvidenceSource.GOOGLE_PLACES,
                source_url=candidate.google_maps_url,
                fanout_task_id=formatted_task_id,
                fanout_task_ids=task_ids,
            )
        )

    return evidence_list


def _match_candidate_for_text(
    text: str,
    candidates: list[Candidate],
) -> Optional[Candidate]:
    """Find a confident, unambiguous Candidate match for a text segment.

    Rules:
    - Normalizes text and candidate names
    - Requires matching the candidate's normalized name as a distinct phrase or having
      unique non-generic token overlap
    - Prevents matches on only generic stop words (e.g. 'Coffee', 'Restaurant')
    - If multiple distinct candidates match the same text segment with equal confidence,
      treats as ambiguous and returns None.
    """
    if not text or not candidates:
        return None

    normalized_text = normalize_name(text)
    if not normalized_text:
        return None

    matched_candidates: list[Candidate] = []

    for c in candidates:
        norm_c_name = normalize_name(c.name)
        if not norm_c_name:
            continue

        meaningful_tokens = _get_meaningful_tokens(norm_c_name)

        # 1. Exact phrase match in normalized text
        # e.g., "halcyon southtown" in "halcyon southtown address 1414 s alamo st"
        pattern = r"\b" + re.escape(norm_c_name) + r"\b"
        if re.search(pattern, normalized_text):
            matched_candidates.append(c)
            continue

        # 2. Check if all meaningful tokens of candidate name appear in text
        # e.g. "Commonwealth Coffeehouse (Weston Centre)" -> "commonwealth weston centre"
        if len(meaningful_tokens) >= 2 and all(
            re.search(r"\b" + re.escape(t) + r"\b", normalized_text)
            for t in meaningful_tokens
        ):
            matched_candidates.append(c)
            continue

        # 3. If candidate has a distinctive single meaningful token (length >= 5 and not generic)
        # e.g., "halcyon" or "kohinoor"
        if len(meaningful_tokens) == 1:
            token = next(iter(meaningful_tokens))
            if len(token) >= 5 and token not in GENERIC_STOP_WORDS:
                if re.search(r"\b" + re.escape(token) + r"\b", normalized_text):
                    matched_candidates.append(c)

    # Return match only if exactly one candidate confidently matches
    if len(matched_candidates) == 1:
        return matched_candidates[0]

    return None


def _extract_source_info(
    source_indices: list[int],
    sources: list[SearchSource],
) -> tuple[Optional[str], Optional[str]]:
    """Resolve source URL and title from grounding source indices."""
    if not source_indices or not sources:
        return None, None

    first_idx = source_indices[0]
    if 0 <= first_idx < len(sources):
        src = sources[first_idx]
        return src.url, src.title

    return None, None


def aggregate_evidence(
    candidates: list[Candidate],
    search_results: list[SearchGroundingResult],
    *,
    places_task_id: Optional[str] = "F1",
) -> EvidenceAggregationResult:
    """Aggregate Places candidates with Search grounding evidence into candidate records.

    Architecture invariants:
    - Google Places candidates remain the canonical candidate universe.
    - Search Grounding enriches existing Places candidates.
    - Unmatched search grounding items are preserved as `unmatched_search_evidence`.
    - Pure deterministic function without API calls or ranking logic.
    """
    candidate_evidence_map: dict[str, CandidateEvidence] = {
        c.place_id: CandidateEvidence(
            candidate=c,
            structured_evidence=_places_to_structured_evidence(c, fanout_task_id=places_task_id),
            search_evidence=[],
        )
        for c in candidates
    }

    unmatched_evidence: list[Evidence] = []
    seen_evidence_keys: set[tuple[str, str, Optional[str]]] = set()

    for sr in search_results:
        planner_query = sr.planner_query
        task_id = sr.task_id
        executed_queries = sr.executed_search_queries
        sources = sr.sources

        # Process citation supports first if present
        if sr.citations:
            for citation in sr.citations:
                claim_text = citation.cited_text or ""
                if not claim_text.strip():
                    continue

                source_url, source_title = _extract_source_info(
                    citation.source_indices, sources
                )

                # Attempt deterministic entity match against Places candidates
                matched_cand = _match_candidate_for_text(claim_text, candidates)
                cid = matched_cand.place_id if matched_cand else "unmatched"

                # Deduplication key within aggregation
                dedupe_key = (cid, claim_text.strip(), source_url)
                if dedupe_key in seen_evidence_keys:
                    continue
                seen_evidence_keys.add(dedupe_key)

                evidence_item = Evidence(
                    candidate_id=cid,
                    attribute="search_grounding_finding",
                    claim=claim_text.strip(),
                    source=EvidenceSource.GOOGLE_SEARCH,
                    source_url=source_url,
                    source_title=source_title,
                    citation=claim_text.strip(),
                    planner_query=planner_query,
                    fanout_task_id=task_id,
                    fanout_task_ids=[task_id] if task_id else [],
                    executed_search_queries=executed_queries,
                    source_indices=citation.source_indices,
                )

                if matched_cand and matched_cand.place_id in candidate_evidence_map:
                    candidate_evidence_map[matched_cand.place_id].search_evidence.append(
                        evidence_item
                    )
                else:
                    unmatched_evidence.append(evidence_item)

        # If no citations were returned but grounded_text exists, break down paragraphs
        elif sr.grounded_text and sr.grounded_text.strip():
            paragraphs = [p.strip() for p in sr.grounded_text.split("\n\n") if p.strip()]
            for p in paragraphs:
                matched_cand = _match_candidate_for_text(p, candidates)
                cid = matched_cand.place_id if matched_cand else "unmatched"

                first_source_url = sources[0].url if sources else None
                first_source_title = sources[0].title if sources else None

                dedupe_key = (cid, p, first_source_url)
                if dedupe_key in seen_evidence_keys:
                    continue
                seen_evidence_keys.add(dedupe_key)

                evidence_item = Evidence(
                    candidate_id=cid,
                    attribute="search_grounding_finding",
                    claim=p,
                    source=EvidenceSource.GOOGLE_SEARCH,
                    source_url=first_source_url,
                    source_title=first_source_title,
                    citation=p,
                    planner_query=planner_query,
                    fanout_task_id=task_id,
                    fanout_task_ids=[task_id] if task_id else [],
                    executed_search_queries=executed_queries,
                    source_indices=[],
                )

                if matched_cand and matched_cand.place_id in candidate_evidence_map:
                    candidate_evidence_map[matched_cand.place_id].search_evidence.append(
                        evidence_item
                    )
                else:
                    unmatched_evidence.append(evidence_item)

    return EvidenceAggregationResult(
        candidates=[candidate_evidence_map[c.place_id] for c in candidates],
        unmatched_search_evidence=unmatched_evidence,
    )
