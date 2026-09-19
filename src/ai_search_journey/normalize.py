"""Candidate normalization and deduplication module."""

import re
from collections.abc import Iterable
from typing import Optional

from ai_search_journey.models import Candidate

GENERIC_LOCATION_STOP_WORDS = {
    "the",
    "a",
    "an",
    "in",
    "at",
    "near",
    "of",
    "for",
    "to",
    "san",
    "antonio",
    "tx",
    "texas",
    "downtown",
}


def _normalize_location_tokens(text: str) -> set[str]:
    """Extract normalized meaningful tokens from location or place text."""
    if not text:
        return set()
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    tokens = set(cleaned.split())
    meaningful = tokens - GENERIC_LOCATION_STOP_WORDS
    return meaningful if meaningful else tokens


def is_reference_location(candidate_name: str, reference_location: Optional[str]) -> bool:
    """Check whether a candidate place name represents the user's reference location.

    For example, if the user asks for 'coffee shop near Geekdom San Antonio',
    'Geekdom' itself is the reference location anchor and not an eligible coffee shop result.
    Similarly, for 'near Trinity University', 'Trinity University' is excluded.
    """
    if not candidate_name or not reference_location:
        return False

    cand_tokens = _normalize_location_tokens(candidate_name)
    ref_tokens = _normalize_location_tokens(reference_location)

    if not cand_tokens or not ref_tokens:
        return False

    # Exact token equality or candidate is an exact sub-anchor of the reference location
    if cand_tokens == ref_tokens:
        return True

    # e.g., candidate="Geekdom" (tokens: {"geekdom"}), ref="Geekdom San Antonio"
    if cand_tokens.issubset(ref_tokens) and len(cand_tokens) >= 1:
        return True

    return False


def _merge_candidate(canonical: Candidate, incoming: Candidate) -> Candidate:
    """Merge missing/empty fields from an incoming duplicate Candidate into a canonical one.

    Preserves first-seen data on the canonical record, but fills any fields that are
    None or empty with available non-empty values from the incoming duplicate.
    Also unions retrieval task IDs to preserve full provenance across multiple queries.
    """
    updated_fields: dict[str, Optional[object]] = {}

    # Prefer non-empty name if canonical name was generic or empty
    if not canonical.name and incoming.name:
        updated_fields["name"] = incoming.name

    if canonical.formatted_address is None and incoming.formatted_address is not None:
        updated_fields["formatted_address"] = incoming.formatted_address

    if canonical.latitude is None and incoming.latitude is not None:
        updated_fields["latitude"] = incoming.latitude

    if canonical.longitude is None and incoming.longitude is not None:
        updated_fields["longitude"] = incoming.longitude

    if canonical.rating is None and incoming.rating is not None:
        updated_fields["rating"] = incoming.rating

    if canonical.user_rating_count is None and incoming.user_rating_count is not None:
        updated_fields["user_rating_count"] = incoming.user_rating_count

    if canonical.website_url is None and incoming.website_url is not None:
        updated_fields["website_url"] = incoming.website_url

    if canonical.google_maps_url is None and incoming.google_maps_url is not None:
        updated_fields["google_maps_url"] = incoming.google_maps_url

    if not canonical.opening_hours and incoming.opening_hours:
        updated_fields["opening_hours"] = list(incoming.opening_hours)

    # Merge retrieval task IDs (e.g. ['F1'] + ['F2'] -> ['F1', 'F2'])
    merged_task_ids = list(canonical.retrieval_task_ids)
    for tid in incoming.retrieval_task_ids:
        if tid and tid not in merged_task_ids:
            merged_task_ids.append(tid)
    if merged_task_ids != canonical.retrieval_task_ids:
        updated_fields["retrieval_task_ids"] = merged_task_ids

    if updated_fields:
        return canonical.model_copy(update=updated_fields)

    return canonical


def normalize_candidates(
    candidates: Iterable[Candidate | Iterable[Candidate]],
    *,
    reference_location: Optional[str] = None,
) -> list[Candidate]:
    """Normalize and deduplicate candidates across multiple retrieval task results.

    Deduplication rules:
    - Primary authoritative key: `candidate.place_id`
    - Preserves first-seen insertion order
    - Merges missing optional fields from subsequent duplicates
    - Unions retrieval task IDs (e.g., F1 and F2)
    - Excludes the reference location if specified (e.g., 'Geekdom' for 'near Geekdom')
    - Candidates with identical or similar names but distinct Place IDs are NOT merged

    Args:
        candidates: An iterable of Candidate objects or nested iterables
            (e.g. list[list[Candidate]]).
        reference_location: Optional reference location string to filter out anchor landmarks.

    Returns:
        A list of deduplicated, normalized canonical Candidate objects.
    """
    canonical_map: dict[str, Candidate] = {}
    ordered_ids: list[str] = []

    def _process_item(item: Candidate) -> None:
        place_id = item.place_id
        if not place_id:
            return

        # Exclude reference location anchors
        if reference_location and is_reference_location(item.name, reference_location):
            return

        if place_id not in canonical_map:
            canonical_map[place_id] = item
            ordered_ids.append(place_id)
        else:
            canonical_map[place_id] = _merge_candidate(canonical_map[place_id], item)

    for item in candidates:
        if isinstance(item, Candidate):
            _process_item(item)
        elif isinstance(item, Iterable):
            for nested_item in item:
                if isinstance(nested_item, Candidate):
                    _process_item(nested_item)

    return [canonical_map[pid] for pid in ordered_ids]
