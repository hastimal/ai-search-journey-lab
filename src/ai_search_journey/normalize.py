"""Candidate normalization and deduplication module."""

from collections.abc import Iterable
from typing import Optional

from ai_search_journey.models import Candidate


def _merge_candidate(canonical: Candidate, incoming: Candidate) -> Candidate:
    """Merge missing/empty fields from an incoming duplicate Candidate into a canonical one.

    Preserves first-seen data on the canonical record, but fills any fields that are
    None or empty with available non-empty values from the incoming duplicate.
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

    if updated_fields:
        return canonical.model_copy(update=updated_fields)

    return canonical


def normalize_candidates(
    candidates: Iterable[Candidate | Iterable[Candidate]],
) -> list[Candidate]:
    """Normalize and deduplicate candidates across multiple retrieval task results.

    Deduplication rules:
    - Primary authoritative key: `candidate.place_id`
    - Preserves first-seen insertion order
    - Merges missing optional fields from subsequent duplicates without complex conflict resolution
    - Candidates with identical or similar names but distinct Place IDs are NOT merged

    Args:
        candidates: An iterable of Candidate objects or nested iterables
            (e.g. list[list[Candidate]]).

    Returns:
        A list of deduplicated, normalized canonical Candidate objects.
    """
    canonical_map: dict[str, Candidate] = {}
    ordered_ids: list[str] = []

    def _process_item(item: Candidate) -> None:
        place_id = item.place_id
        if not place_id:
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
