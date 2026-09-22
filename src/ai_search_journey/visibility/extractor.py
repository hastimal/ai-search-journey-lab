"""Deterministic visibility observation extractor for AI Search Visibility (V3)."""

from __future__ import annotations

import re
from typing import Optional

from ai_search_journey.models import (
    Candidate,
    Evidence,
    EvidenceSource,
    GroundedAnswer,
    JourneyResult,
    ToolName,
)
from ai_search_journey.visibility.models import (
    BrandObservation,
    BrandProfile,
    BrandRole,
    CitationObservation,
    FanoutObservation,
    ScanStatus,
    VisibilityScan,
    VisibilityScanBundle,
    normalize_domain,
)


class AmbiguousBrandMatchError(Exception):
    """Raised when a candidate matches multiple configured brands
    at the same highest priority level.
    """


def _normalize_name(name: str) -> str:
    """Normalize a brand or candidate name using Unicode casefold and whitespace collapse."""
    return " ".join(name.casefold().split())


def _is_matching_domain(cand_domain: str, verified_domain: str) -> bool:
    """Check if candidate domain exactly matches verified domain or is a true subdomain."""
    return cand_domain == verified_domain or cand_domain.endswith("." + verified_domain)


def match_candidate_to_brand(
    candidate: Candidate,
    brands: list[BrandProfile],
) -> Optional[BrandProfile]:
    """Match a candidate to a configured brand profile using strict priority:

    1. Exact Google Place ID match against BrandProfile.place_ids
    2. Verified candidate website domain match against domain or domain_aliases
    3. Exact normalized candidate name match against name or aliases

    Raises AmbiguousBrandMatchError if multiple brands match at the same highest priority level.
    """
    # Priority 1: Google Place ID
    place_matches = [b for b in brands if candidate.place_id in b.place_ids]
    if len(place_matches) > 1:
        matched_ids = [b.brand_id for b in place_matches]
        raise AmbiguousBrandMatchError(
            f"Candidate '{candidate.name}' (place_id='{candidate.place_id}') matches multiple "
            f"brands at Priority 1 (Place ID): {matched_ids}"
        )
    if len(place_matches) == 1:
        return place_matches[0]

    # Priority 2: Verified website domain
    if candidate.website_url:
        try:
            cand_domain = normalize_domain(candidate.website_url)
        except Exception:
            cand_domain = None

        if cand_domain:
            domain_matches = []
            for b in brands:
                b_domains = ([b.domain] if b.domain else []) + b.domain_aliases
                if any(_is_matching_domain(cand_domain, bd) for bd in b_domains):
                    domain_matches.append(b)

            if len(domain_matches) > 1:
                matched_ids = [b.brand_id for b in domain_matches]
                raise AmbiguousBrandMatchError(
                    f"Candidate '{candidate.name}' (domain='{cand_domain}') matches multiple "
                    f"brands at Priority 2 (Domain): {matched_ids}"
                )
            if len(domain_matches) == 1:
                return domain_matches[0]

    # Priority 3: Exact normalized name match
    cand_norm_name = _normalize_name(candidate.name)
    name_matches = []
    for b in brands:
        b_names = [_normalize_name(b.name)] + [_normalize_name(a) for a in b.aliases]
        if cand_norm_name in b_names:
            name_matches.append(b)

    if len(name_matches) > 1:
        matched_ids = [b.brand_id for b in name_matches]
        raise AmbiguousBrandMatchError(
            f"Candidate '{candidate.name}' matches multiple brands at Priority 3 (Name): "
            f"{matched_ids}"
        )
    if len(name_matches) == 1:
        return name_matches[0]

    return None


def build_answer_mention_corpus(answer: Optional[GroundedAnswer]) -> str:
    """Construct user-visible text corpus strictly from GroundedAnswer components."""
    if answer is None:
        return ""
    sections: list[str] = []
    if answer.summary and answer.summary.strip():
        sections.append(answer.summary.strip())
    for rec in answer.recommendations:
        if rec.summary and rec.summary.strip():
            sections.append(rec.summary.strip())
        for why in rec.why_it_matches:
            if why and why.strip():
                sections.append(why.strip())
    for caveat in answer.caveats:
        if caveat and caveat.strip():
            sections.append(caveat.strip())
    return "\n".join(sections)


def _term_to_regex(term: str) -> str:
    """Build a regex pattern enforcing word/phrase boundaries for a search term."""
    escaped = re.escape(term)
    prefix = r"(?<!\w)" if re.match(r"^\w", term, re.UNICODE) else r"(?<!\S)"
    suffix = r"(?!\w)" if re.search(r"\w$", term, re.UNICODE) else r"(?!\S)"
    return f"{prefix}{escaped}{suffix}"


def extract_brand_mentions(
    brand: BrandProfile,
    corpus: str,
) -> tuple[bool, int, Optional[int]]:
    """Extract non-overlapping mentions of brand name and aliases within text corpus."""
    if not corpus:
        return False, 0, None

    # Collect unique terms, deduplicated case-insensitively, sorted by length descending
    seen_terms: set[str] = set()
    unique_terms: list[str] = []
    for raw in [brand.name] + brand.aliases:
        stripped = raw.strip()
        if not stripped:
            continue
        cf = stripped.casefold()
        if cf not in seen_terms:
            seen_terms.add(cf)
            unique_terms.append(stripped)

    unique_terms.sort(key=len, reverse=True)

    matched_spans: list[tuple[int, int]] = []
    for term in unique_terms:
        pattern = _term_to_regex(term)
        for m in re.finditer(pattern, corpus, flags=re.IGNORECASE | re.UNICODE):
            start, end = m.span()
            overlaps = any(
                not (end <= existing_start or start >= existing_end)
                for existing_start, existing_end in matched_spans
            )
            if not overlaps:
                matched_spans.append((start, end))

    if not matched_spans:
        return False, 0, None

    matched_spans.sort(key=lambda s: s[0])
    first_pos = matched_spans[0][0]
    count = len(matched_spans)
    return True, count, first_pos


def _collect_all_evidence(journey: JourneyResult) -> list[Evidence]:
    """Collect all structured evidence items from JourneyResult."""
    items: list[Evidence] = list(journey.evidence)
    if journey.evidence_result:
        for ce in journey.evidence_result.candidates:
            items.extend(ce.structured_evidence)
            items.extend(ce.search_evidence)
        items.extend(journey.evidence_result.unmatched_search_evidence)
    return items


def extract_visibility_scan_bundle(
    *,
    scan: VisibilityScan,
    journey: JourneyResult,
    target_brand: BrandProfile,
    competitor_brands: list[BrandProfile],
) -> VisibilityScanBundle:
    """Extract a complete deterministic VisibilityScanBundle from a completed JourneyResult.

    Pure function: zero external API calls, zero state mutation.
    """
    # 1. Validation invariants
    if scan.status != ScanStatus.COMPLETED:
        raise ValueError(
            f"scan.status must be COMPLETED, got {scan.status.value}"
        )
    if scan.brand_id != target_brand.brand_id:
        raise ValueError(
            f"scan.brand_id '{scan.brand_id}' does not match "
            f"target_brand.brand_id '{target_brand.brand_id}'"
        )

    if any(c.brand_id == target_brand.brand_id for c in competitor_brands):
        raise ValueError("Target brand must not appear in competitor_brands")

    all_brands = [target_brand] + list(competitor_brands)
    brand_ids = [b.brand_id for b in all_brands]
    if len(brand_ids) != len(set(brand_ids)):
        raise ValueError("Brand IDs across target and competitors must be unique")

    # 2. Map candidates to brands using strict priority
    candidate_brand_map: dict[str, str] = {}
    matched_candidates_by_brand: dict[str, list[Candidate]] = {b.brand_id: [] for b in all_brands}
    for candidate in journey.candidates:
        matched_brand = match_candidate_to_brand(candidate, all_brands)
        if matched_brand:
            candidate_brand_map[candidate.place_id] = matched_brand.brand_id
            matched_candidates_by_brand[matched_brand.brand_id].append(candidate)

    # 3. Citation collection and matching
    raw_citations: list[tuple[str, str]] = []

    # 3a. Google Search grounding sources
    for sr in journey.search_results:
        for src in sr.sources:
            if src.url:
                raw_citations.append((src.url, "google_search"))

    # 3b. Evidence source URLs
    all_evidence = _collect_all_evidence(journey)
    for ev in all_evidence:
        if ev.source_url:
            st = ev.source.value if hasattr(ev.source, "value") else str(ev.source)
            raw_citations.append((ev.source_url, st))

    # 3c. Grounded-answer citations
    if journey.answer:
        for cit_url in journey.answer.citations:
            if cit_url:
                raw_citations.append((cit_url, "grounded_answer"))

    # Deduplicate citations by (scan_id, url, source_type) preserving first-seen order
    deduped_citations: list[CitationObservation] = []
    seen_citation_keys: set[tuple[str, str, str]] = set()

    for raw_url, st in raw_citations:
        url_clean = raw_url.strip()
        if not url_clean:
            continue
        key = (scan.scan_id, url_clean, st.strip().lower())
        if key in seen_citation_keys:
            continue
        seen_citation_keys.add(key)

        try:
            dom = normalize_domain(url_clean)
        except Exception:
            dom = None
        if not dom:
            continue

        matched_brand_ids = [
            b.brand_id
            for b in all_brands
            if any(
                _is_matching_domain(dom, bd)
                for bd in (([b.domain] if b.domain else []) + b.domain_aliases)
            )
        ]

        deduped_citations.append(
            CitationObservation(
                scan_id=scan.scan_id,
                url=url_clean,
                domain=dom,
                source_type=st,
                matched_brand_ids=matched_brand_ids,
            )
        )

    # 4. Answer mention corpus
    corpus = build_answer_mention_corpus(journey.answer)

    # 5. Build BrandObservation for each brand (target first, then competitors in order)
    brand_observations: list[BrandObservation] = []
    for brand in all_brands:
        role = BrandRole.TARGET if brand.brand_id == target_brand.brand_id else BrandRole.COMPETITOR

        # Mentions
        mentioned, mention_count, first_mention_pos = extract_brand_mentions(brand, corpus)

        # Retrieval
        matched_cands = matched_candidates_by_brand[brand.brand_id]
        retrieval_positions = [
            c.best_retrieval_position
            for c in matched_cands
            if c.best_retrieval_position is not None and c.best_retrieval_position >= 1
        ]
        if retrieval_positions:
            retrieved = True
            best_retrieval_pos: Optional[int] = min(retrieval_positions)
        else:
            retrieved = False
            best_retrieval_pos = None

        # Recommendations
        matched_ranked = [
            rc
            for rc in journey.ranking
            if candidate_brand_map.get(rc.candidate.place_id) == brand.brand_id
        ]
        if matched_ranked:
            recommended = True
            recommendation_pos: Optional[int] = min(rc.rank for rc in matched_ranked)
        else:
            recommended = False
            recommendation_pos = None

        # Citations
        brand_cits = [c for c in deduped_citations if brand.brand_id in c.matched_brand_ids]
        if brand_cits:
            cited = True
            citation_urls = list(dict.fromkeys(c.url for c in brand_cits))
            citation_domains = list(dict.fromkeys(c.domain for c in brand_cits))
        else:
            cited = False
            citation_urls = []
            citation_domains = []

        brand_observations.append(
            BrandObservation(
                scan_id=scan.scan_id,
                brand_id=brand.brand_id,
                role=role,
                mentioned=mentioned,
                mention_count=mention_count,
                first_mention_position=first_mention_pos,
                retrieved=retrieved,
                best_retrieval_position=best_retrieval_pos,
                recommended=recommended,
                recommendation_position=recommendation_pos,
                cited=cited,
                citation_urls=citation_urls,
                citation_domains=citation_domains,
            )
        )

    # 6. Fan-out observations (configured brands × journey.fanout tasks)
    fanout_observations: list[FanoutObservation] = []
    all_search_evidence = [
        ev for ev in all_evidence
        if ev.source == EvidenceSource.GOOGLE_SEARCH
        or (hasattr(ev.source, "value") and ev.source.value == "google_search")
    ]

    for brand in all_brands:
        matched_cands = matched_candidates_by_brand[brand.brand_id]
        matched_place_ids = {c.place_id for c in matched_cands}

        for idx, task in enumerate(journey.fanout):
            task_id = (task.task_id or f"task_{idx}").strip()
            tool_val = (
                task.tool.value
                if hasattr(task.tool, "value")
                else str(task.tool).strip().lower()
            )

            if tool_val == ToolName.GOOGLE_PLACES.value:
                # Places occurrences
                matching_occ_positions: list[int] = []
                for c in matched_cands:
                    for occ in c.retrieval_occurrences:
                        if occ.query_task_id == task.task_id and occ.position >= 1:
                            matching_occ_positions.append(occ.position)
                if matching_occ_positions:
                    brand_found = True
                    pos_in_task: Optional[int] = min(matching_occ_positions)
                else:
                    brand_found = False
                    pos_in_task = None

            elif tool_val == ToolName.GOOGLE_SEARCH.value:
                # Structured search evidence linked to this task_id
                has_search_evidence = False
                for ev in all_search_evidence:
                    if ev.candidate_id in matched_place_ids:
                        if ev.fanout_task_id == task.task_id or task.task_id in ev.fanout_task_ids:
                            has_search_evidence = True
                            break
                if has_search_evidence:
                    brand_found = True
                    pos_in_task = None
                else:
                    brand_found = False
                    pos_in_task = None

            else:
                brand_found = False
                pos_in_task = None

            fanout_observations.append(
                FanoutObservation(
                    scan_id=scan.scan_id,
                    task_id=task_id,
                    query_text=task.query,
                    tool=task.tool,
                    brand_id=brand.brand_id,
                    brand_found=brand_found,
                    position_in_task=pos_in_task,
                )
            )

    return VisibilityScanBundle(
        scan=scan.model_copy(deep=True),
        brand_observations=brand_observations,
        fanout_observations=fanout_observations,
        citations=deduped_citations,
    )
