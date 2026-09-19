"""Deterministic constraint evaluation module for AI Search Journey."""

import re
from typing import Optional

from ai_search_journey.models import (
    CandidateConstraintEvaluation,
    CandidateEvidence,
    CategoryEligibility,
    ConstraintEvaluationResult,
    ConstraintResult,
    ConstraintStatus,
    ConstraintSupport,
    Evidence,
    EvidenceSource,
    SearchIntent,
)


def _parse_time_str_to_minutes(time_str: str) -> Optional[int]:
    """Parse time string like '20:00', '8 PM', '12:00 AM' into minutes from midnight (0..1439)."""
    if not time_str:
        return None

    cleaned = time_str.strip().upper()

    # Case 1: 24-hour format HH:MM
    match_24 = re.match(r"^(\d{1,2}):(\d{2})$", cleaned)
    if match_24:
        hours = int(match_24.group(1))
        minutes = int(match_24.group(2))
        return hours * 60 + minutes

    # Case 2: 12-hour format with AM/PM e.g. "8 PM", "9:30 PM", "12 AM", "12:00 AM"
    match_12 = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)", cleaned)
    if match_12:
        hours = int(match_12.group(1))
        minutes = int(match_12.group(2)) if match_12.group(2) else 0
        meridiem = match_12.group(3)

        if meridiem == "AM":
            if hours == 12:
                hours = 0
        elif meridiem == "PM":
            if hours != 12:
                hours += 12

        return hours * 60 + minutes

    return None


def _dedupe_supports(supports: list[ConstraintSupport]) -> list[ConstraintSupport]:
    """Remove duplicate support items while preserving insertion order."""
    unique: list[ConstraintSupport] = []
    seen: set[tuple[str, Optional[str], Optional[str]]] = set()
    for s in supports:
        key = (s.source_type, s.evidence_text, s.source_url)
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique


def _evaluate_open_after(
    open_after_str: str,
    opening_hours: list[str],
    structured_evidence: list[Evidence],
    search_evidence: Optional[list[Evidence]] = None,
) -> ConstraintResult:
    """Evaluate whether opening hours support being open after the requested time.

    Rule:
    - If opening_hours is empty/missing and no search evidence -> UNKNOWN
    - If any day has "Open 24 hours" -> SUPPORTED
    - Parses closing times across returned weekday descriptions.
      If latest closing time > target time (strictly after, or extends past midnight)
      -> SUPPORTED.
      If latest closing time <= target time (closes before or exactly at requested time)
      -> NOT_SATISFIED.
    - If Search evidence independently confirms late opening, it is included as multi-source.
    """
    effective_search_evidence = search_evidence or []
    target_minutes = _parse_time_str_to_minutes(open_after_str)
    hours_evidence = [e for e in structured_evidence if e.attribute == "opening_hours"]
    evidence_text = hours_evidence[0].claim if hours_evidence else None

    task_ids = (
        hours_evidence[0].fanout_task_ids
        if (hours_evidence and hours_evidence[0].fanout_task_ids)
        else (
            [hours_evidence[0].fanout_task_id]
            if (hours_evidence and hours_evidence[0].fanout_task_id)
            else ["F1"]
        )
    )

    places_status: ConstraintStatus = ConstraintStatus.UNKNOWN
    places_support: Optional[ConstraintSupport] = None
    explanation: str = ""

    if opening_hours and target_minutes is not None:
        if any("open 24 hours" in h.lower() for h in opening_hours):
            places_status = ConstraintStatus.SUPPORTED
            places_support = ConstraintSupport(
                source_type=EvidenceSource.GOOGLE_PLACES.value,
                fanout_task_ids=task_ids,
                evidence_text=evidence_text,
            )
            explanation = f"Place is open 24 hours, satisfying open after {open_after_str}."
        else:
            closing_minutes_list: list[int] = []
            for h in opening_hours:
                normalized_h = re.sub(r"[–—]", "-", h)
                ranges = re.findall(
                    r"(\d{1,2}(?::\d{2})?\s*(?:AM|PM)?)\s*-\s*(\d{1,2}(?::\d{2})?\s*(?:AM|PM))",
                    normalized_h,
                    re.IGNORECASE,
                )
                for _, close_str in ranges:
                    c_min = _parse_time_str_to_minutes(close_str)
                    if c_min is not None:
                        effective_c_min = c_min + 1440 if c_min <= 4 * 60 else c_min
                        closing_minutes_list.append(effective_c_min)

            if closing_minutes_list:
                max_close = max(closing_minutes_list)
                if max_close > target_minutes:
                    places_status = ConstraintStatus.SUPPORTED
                    places_support = ConstraintSupport(
                        source_type=EvidenceSource.GOOGLE_PLACES.value,
                        fanout_task_ids=task_ids,
                        evidence_text=evidence_text,
                    )
                    explanation = (
                        f"Schedule shows closing time of {max_close // 60}:{(max_close % 60):02d} "
                        f"which is after {open_after_str}."
                    )
                else:
                    places_status = ConstraintStatus.NOT_SATISFIED
                    places_support = ConstraintSupport(
                        source_type=EvidenceSource.GOOGLE_PLACES.value,
                        fanout_task_ids=task_ids,
                        evidence_text=evidence_text,
                    )
                    explanation = (
                        f"All schedule closing times (latest: "
                        f"{max_close // 60}:{(max_close % 60):02d}) do not extend after "
                        f"{open_after_str}."
                    )

    # Check Search evidence for independent confirmation
    search_supports: list[ConstraintSupport] = []
    late_keywords = ["open late", "open until midnight", "late night", "open past", "24 hours"]
    for se in effective_search_evidence:
        claim_lower = se.claim.lower()
        if any(kw in claim_lower for kw in late_keywords):
            se_task_ids = se.fanout_task_ids or ([se.fanout_task_id] if se.fanout_task_id else [])
            search_supports.append(
                ConstraintSupport(
                    source_type=EvidenceSource.GOOGLE_SEARCH.value,
                    fanout_task_ids=se_task_ids,
                    evidence_text=se.claim,
                    source_title=se.source_title,
                    source_url=se.source_url,
                    planner_query=se.planner_query,
                    citation_indices=se.source_indices,
                )
            )

    all_supports: list[ConstraintSupport] = []
    if places_support:
        all_supports.append(places_support)
    all_supports.extend(search_supports)
    all_supports = _dedupe_supports(all_supports)

    if places_status == ConstraintStatus.SUPPORTED:
        return ConstraintResult(
            constraint=f"Open after {open_after_str}",
            status=ConstraintStatus.SUPPORTED,
            supporting_evidence=all_supports,
            explanation=explanation,
        )
    elif places_status == ConstraintStatus.NOT_SATISFIED:
        return ConstraintResult(
            constraint=f"Open after {open_after_str}",
            status=ConstraintStatus.NOT_SATISFIED,
            supporting_evidence=all_supports if all_supports else [],
            explanation=explanation,
        )
    elif search_supports:
        return ConstraintResult(
            constraint=f"Open after {open_after_str}",
            status=ConstraintStatus.SUPPORTED,
            supporting_evidence=search_supports,
            explanation=f"Search evidence confirms late opening after {open_after_str}.",
        )

    return ConstraintResult(
        constraint=f"Open after {open_after_str}",
        status=ConstraintStatus.UNKNOWN,
        supporting_evidence=[],
        explanation="Opening hours are missing or could not be parsed.",
    )


def _evaluate_group_size(
    group_size: int,
    search_evidence: list[Evidence],
) -> ConstraintResult:
    """Evaluate whether evidence supports the requested group size."""
    constraint_name = f"Group size {group_size}"

    pos_keywords = [
        f"group of {group_size}",
        f"groups of {group_size}",
        f"{group_size} people",
        f"{group_size} students",
        f"{group_size} or more",
        f"{group_size}+",
        "large group",
        "large groups",
        "large party",
        "large parties",
        "communal table",
        "communal tables",
        "private room",
        "private dining room",
        "banquet hall",
        "party room",
        "spacious seating",
        "large tables",
    ]

    neg_keywords = [
        "unsuitable for",
        "not suitable for group",
        "not suitable for groups",
        "compact space",
        "small footprint",
        "grab-and-go",
        "grab and go only",
        "limited to two-top",
        "tight seating",
        "cannot accommodate",
    ]

    supports: list[ConstraintSupport] = []
    is_neg = False

    for se in search_evidence:
        claim_lower = se.claim.lower()
        task_ids = se.fanout_task_ids or ([se.fanout_task_id] if se.fanout_task_id else [])
        if any(kw in claim_lower for kw in pos_keywords):
            supports.append(
                ConstraintSupport(
                    source_type=EvidenceSource.GOOGLE_SEARCH.value,
                    fanout_task_ids=task_ids,
                    evidence_text=se.claim,
                    source_title=se.source_title,
                    source_url=se.source_url,
                    planner_query=se.planner_query,
                    citation_indices=se.source_indices,
                )
            )
        elif any(kw in claim_lower for kw in neg_keywords):
            is_neg = True
            supports.append(
                ConstraintSupport(
                    source_type=EvidenceSource.GOOGLE_SEARCH.value,
                    fanout_task_ids=task_ids,
                    evidence_text=se.claim,
                    source_title=se.source_title,
                    source_url=se.source_url,
                    planner_query=se.planner_query,
                    citation_indices=se.source_indices,
                )
            )

    supports = _dedupe_supports(supports)

    if supports and not is_neg:
        return ConstraintResult(
            constraint=constraint_name,
            status=ConstraintStatus.SUPPORTED,
            supporting_evidence=supports,
            explanation=f"Evidence confirms seating for groups of {group_size}.",
        )
    elif supports and is_neg:
        return ConstraintResult(
            constraint=constraint_name,
            status=ConstraintStatus.NOT_SATISFIED,
            supporting_evidence=supports,
            explanation=f"Evidence indicates seating is unsuitable for groups of {group_size}.",
        )

    return ConstraintResult(
        constraint=constraint_name,
        status=ConstraintStatus.UNKNOWN,
        supporting_evidence=[],
        explanation=f"No conclusive evidence found for group of {group_size}.",
    )


def _evaluate_qualitative_constraint(
    constraint_text: str,
    search_evidence: list[Evidence],
    *,
    is_preference: bool = False,
) -> ConstraintResult:
    """Evaluate a qualitative constraint or preference (e.g. 'quiet', 'vegetarian options')."""
    c_lower = constraint_text.lower().strip()
    tag = " (Preference)" if is_preference else ""
    full_constraint_name = f"{constraint_text}{tag}"

    if "quiet" in c_lower or "noise" in c_lower:
        pos = ["quiet", "calm", "peaceful", "low noise", "focus oriented", "study friendly"]
        neg = ["loud", "noisy", "bustling", "high traffic", "party atmosphere"]
    elif "veg" in c_lower:
        pos = ["vegetarian", "vegan", "plant based", "meatless"]
        neg = ["no vegetarian", "no vegan", "strictly meat"]
    elif "work" in c_lower or "laptop" in c_lower or "study" in c_lower:
        pos = ["work", "laptop", "remote workers", "wifi", "outlets", "study"]
        neg = ["no wifi", "no laptops", "laptops prohibited"]
    else:
        terms = [t for t in c_lower.split() if len(t) > 3]
        pos = terms
        neg = [f"no {t}" for t in terms]

    supports: list[ConstraintSupport] = []
    is_neg = False

    for se in search_evidence:
        claim_lower = se.claim.lower()
        task_ids = se.fanout_task_ids or ([se.fanout_task_id] if se.fanout_task_id else [])
        if any(p in claim_lower for p in pos):
            supports.append(
                ConstraintSupport(
                    source_type=EvidenceSource.GOOGLE_SEARCH.value,
                    fanout_task_ids=task_ids,
                    evidence_text=se.claim,
                    source_title=se.source_title,
                    source_url=se.source_url,
                    planner_query=se.planner_query,
                    citation_indices=se.source_indices,
                )
            )
        elif any(n in claim_lower for n in neg):
            is_neg = True
            supports.append(
                ConstraintSupport(
                    source_type=EvidenceSource.GOOGLE_SEARCH.value,
                    fanout_task_ids=task_ids,
                    evidence_text=se.claim,
                    source_title=se.source_title,
                    source_url=se.source_url,
                    planner_query=se.planner_query,
                    citation_indices=se.source_indices,
                )
            )

    supports = _dedupe_supports(supports)

    if supports and not is_neg:
        return ConstraintResult(
            constraint=full_constraint_name,
            status=ConstraintStatus.SUPPORTED,
            supporting_evidence=supports,
            explanation=f"Search evidence supports '{constraint_text}'.",
        )
    elif supports and is_neg:
        return ConstraintResult(
            constraint=full_constraint_name,
            status=ConstraintStatus.NOT_SATISFIED,
            supporting_evidence=supports,
            explanation=f"Search evidence contradicts '{constraint_text}'.",
        )

    return ConstraintResult(
        constraint=full_constraint_name,
        status=ConstraintStatus.UNKNOWN,
        supporting_evidence=[],
        explanation=f"No specific evidence found verifying '{constraint_text}'.",
    )


def evaluate_category_eligibility(
    requested_category: Optional[str],
    primary_type: Optional[str],
    place_types: list[str],
) -> CategoryEligibility:
    """Deterministically evaluate candidate category compatibility against SearchIntent.category.

    Rules:
    - If no requested category: SUPPORTED
    - If candidate has no type information at all: UNKNOWN
    - Normalized token matching across requested category tokens and candidate place types:
      - Direct type match / substring match (e.g. 'coffee_shop', 'cafe', 'espresso_bar',
        'indian_restaurant', 'restaurant') -> SUPPORTED
      - Incompatible / unrelated types without category match
        (e.g., store, university, lodging without cafe/restaurant) -> NOT_SATISFIED
      - Ambiguous / unverified -> UNKNOWN
    """
    if not requested_category or not requested_category.strip():
        return CategoryEligibility(
            status=ConstraintStatus.SUPPORTED,
            requested_category=requested_category or "",
            primary_type=primary_type,
            place_types=place_types,
            explanation="No specific category filter requested.",
        )

    clean_req = requested_category.strip().lower()
    all_candidate_types = [t.lower() for t in place_types]
    if primary_type:
        all_candidate_types.insert(0, primary_type.lower())

    if not all_candidate_types:
        return CategoryEligibility(
            status=ConstraintStatus.UNKNOWN,
            requested_category=requested_category,
            primary_type=primary_type,
            place_types=place_types,
            explanation=(
                f"No Places type metadata available to verify category '{requested_category}'."
            ),
        )

    # Token-level category compatibility mappings
    # Coffee shop scenario
    if "coffee" in clean_req:
        compatible_primary = {
            "coffee_shop",
            "cafe",
            "coffee_store",
            "coffee_roastery",
            "espresso_bar",
            "tea_house",
        }
        # If primary_type is provided, it must be a compatible coffee/cafe type
        if primary_type:
            if primary_type.lower() in compatible_primary:
                return CategoryEligibility(
                    status=ConstraintStatus.SUPPORTED,
                    requested_category=requested_category,
                    primary_type=primary_type,
                    place_types=place_types,
                    explanation=f"Compatible coffee primary type verified: {primary_type}.",
                )
            else:
                return CategoryEligibility(
                    status=ConstraintStatus.NOT_SATISFIED,
                    requested_category=requested_category,
                    primary_type=primary_type,
                    place_types=place_types,
                    explanation=(
                        f"Primary type '{primary_type}' is not a dedicated coffee shop or cafe."
                    ),
                )
        # If no primary_type, check if any place_type matches
        if any(t in compatible_primary for t in all_candidate_types):
            return CategoryEligibility(
                status=ConstraintStatus.SUPPORTED,
                requested_category=requested_category,
                primary_type=primary_type,
                place_types=place_types,
                explanation=(
                    "Compatible coffee category type verified in place types: "
                    f"{all_candidate_types[0]}."
                ),
            )
        return CategoryEligibility(
            status=ConstraintStatus.NOT_SATISFIED,
            requested_category=requested_category,
            primary_type=primary_type,
            place_types=place_types,
            explanation=(
                f"Candidate types {all_candidate_types[:4]} are not a "
                "dedicated coffee shop or cafe."
            ),
        )

    # Restaurant / Indian restaurant scenario
    if "restaurant" in clean_req or "food" in clean_req or "cuisine" in clean_req:
        # Check specific cuisines
        if "indian" in clean_req:
            if "indian_restaurant" in all_candidate_types:
                return CategoryEligibility(
                    status=ConstraintStatus.SUPPORTED,
                    requested_category=requested_category,
                    primary_type=primary_type,
                    place_types=place_types,
                    explanation="Compatible type 'indian_restaurant' verified.",
                )
            if any("restaurant" in t for t in all_candidate_types):
                # Generic restaurant type for Indian query without specific indian_restaurant type
                return CategoryEligibility(
                    status=ConstraintStatus.UNKNOWN,
                    requested_category=requested_category,
                    primary_type=primary_type,
                    place_types=place_types,
                    explanation=(
                        "Restaurant type verified, but specific Indian cuisine type is unverified."
                    ),
                )
        else:
            if any("restaurant" in t or "food" in t or "cafe" in t for t in all_candidate_types):
                matched_type = primary_type or all_candidate_types[0]
                return CategoryEligibility(
                    status=ConstraintStatus.SUPPORTED,
                    requested_category=requested_category,
                    primary_type=primary_type,
                    place_types=place_types,
                    explanation=f"Compatible restaurant type verified: {matched_type}.",
                )

    # Generic substring / word token match
    req_tokens = set(re.findall(r"\w+", clean_req))
    matched_tokens: set[str] = set()
    for t in all_candidate_types:
        type_tokens = set(t.split("_"))
        matched_tokens.update(req_tokens.intersection(type_tokens))

    if matched_tokens:
        return CategoryEligibility(
            status=ConstraintStatus.SUPPORTED,
            requested_category=requested_category,
            primary_type=primary_type,
            place_types=place_types,
            explanation=f"Category tokens {matched_tokens} match candidate place types.",
        )

    # Default fallback to UNKNOWN rather than guessing
    return CategoryEligibility(
        status=ConstraintStatus.UNKNOWN,
        requested_category=requested_category,
        primary_type=primary_type,
        place_types=place_types,
        explanation=(
            f"Candidate types {all_candidate_types[:3]} do not definitively verify "
            f"'{requested_category}'."
        ),
    )


def evaluate_constraints(
    intent: SearchIntent,
    candidate_evidences: list[CandidateEvidence],
) -> ConstraintEvaluationResult:
    """Evaluate explicit hard constraints and preferences against candidate evidence.

    Deterministic rules:
    - Never converts missing/insufficient evidence into NOT_SATISFIED (UNKNOWN != FALSE).
    - Preserves provenance (supporting_evidence with full ConstraintSupport metadata).
    - Evaluates category compatibility as a primary constraint.
    - Pure computation with no LLM or API calls.
    """
    evaluations: list[CandidateConstraintEvaluation] = []

    for ce in candidate_evidences:
        candidate = ce.candidate
        results: list[ConstraintResult] = []

        # 0. Evaluate category compatibility constraint
        if intent.category:
            cat_elig = evaluate_category_eligibility(
                intent.category,
                candidate.primary_type,
                candidate.place_types,
            )
            cat_support: list[ConstraintSupport] = []
            if cat_elig.status == ConstraintStatus.SUPPORTED:
                type_summary = (
                    f"Primary Type: {candidate.primary_type or 'N/A'}, "
                    f"Types: {','.join(candidate.place_types[:4])}"
                )
                cat_support.append(
                    ConstraintSupport(
                        source_type="google_places",
                        fanout_task_ids=candidate.retrieval_task_ids or ["F1"],
                        evidence_text=type_summary,
                    )
                )
            results.append(
                ConstraintResult(
                    constraint=f"Category: {intent.category}",
                    status=cat_elig.status,
                    supporting_evidence=cat_support,
                    explanation=cat_elig.explanation,
                )
            )

        # 1. Evaluate open_after constraint
        if intent.open_after:
            results.append(
                _evaluate_open_after(
                    intent.open_after,
                    candidate.opening_hours,
                    ce.structured_evidence,
                    ce.search_evidence,
                )
            )

        # 2. Evaluate group_size constraint
        if intent.group_size:
            results.append(_evaluate_group_size(intent.group_size, ce.search_evidence))

        # 3. Evaluate other hard constraints
        for hc in intent.hard_constraints:
            hc_lower = hc.lower()
            if intent.category and intent.category.lower() in hc_lower:
                continue
            if intent.open_after and ("open after" in hc_lower or "late" in hc_lower):
                continue
            if intent.group_size and ("group" in hc_lower or str(intent.group_size) in hc_lower):
                continue

            results.append(
                _evaluate_qualitative_constraint(
                    hc,
                    ce.search_evidence,
                    is_preference=False,
                )
            )

        # 4. Evaluate preferences
        for pref in intent.preferences:
            results.append(
                _evaluate_qualitative_constraint(
                    pref,
                    ce.search_evidence,
                    is_preference=True,
                )
            )

        evaluations.append(
            CandidateConstraintEvaluation(
                candidate=candidate,
                results=results,
            )
        )

    return ConstraintEvaluationResult(evaluations=evaluations)
