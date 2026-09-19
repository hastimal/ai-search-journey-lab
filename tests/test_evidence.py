"""Unit tests for evidence aggregation module."""

from ai_search_journey.evidence import aggregate_evidence, normalize_name
from ai_search_journey.models import (
    Candidate,
    EvidenceSource,
    SearchCitation,
    SearchGroundingResult,
    SearchSource,
)


def test_every_normalized_candidate_becomes_candidate_evidence() -> None:
    """Every input candidate becomes a CandidateEvidence entry in the exact input order."""
    c1 = Candidate(place_id="id_1", name="Place 1")
    c2 = Candidate(place_id="id_2", name="Place 2")

    result = aggregate_evidence([c1, c2], [])

    assert len(result.candidates) == 2
    assert result.candidates[0].candidate.place_id == "id_1"
    assert result.candidates[1].candidate.place_id == "id_2"
    assert result.unmatched_search_evidence == []


def test_places_fields_become_structured_evidence() -> None:
    """Candidate attributes (address, rating, hours, etc.) become structured evidence."""
    c = Candidate(
        place_id="place_1",
        name="Halcyon Southtown",
        formatted_address="1414 S Alamo St",
        latitude=29.4099,
        longitude=-98.4954,
        rating=4.2,
        user_rating_count=2493,
        website_url="http://halcyoncoffeebar.com",
        google_maps_url="https://maps.google.com/?cid=12345",
        opening_hours=["Monday: 8:00 AM – 12:00 AM"],
    )

    result = aggregate_evidence([c], [])
    ce = result.candidates[0]

    assert len(ce.structured_evidence) == 6
    attrs = {e.attribute for e in ce.structured_evidence}
    assert attrs == {
        "formatted_address",
        "rating",
        "opening_hours",
        "website_url",
        "google_maps_url",
        "location",
    }
    for e in ce.structured_evidence:
        assert e.source == EvidenceSource.GOOGLE_PLACES
        assert e.candidate_id == "place_1"


def test_exact_normalized_name_search_evidence_matches_candidate() -> None:
    """Exact or case/punctuation-insensitive name in citation matches canonical candidate."""
    c1 = Candidate(place_id="id_halcyon", name="Halcyon Southtown")
    c2 = Candidate(place_id="id_lazydaze", name="Lazydaze Coffeeshop")

    sr = SearchGroundingResult(
        planner_query="quiet coffee shops to work late",
        grounded_text="Halcyon Southtown has large group tables and couches.",
        executed_search_queries=["quiet coffee shops San Antonio"],
        sources=[SearchSource(title="SA Guide", url="https://example.com/sa-guide")],
        citations=[
            SearchCitation(
                start_index=0,
                end_index=53,
                source_indices=[0],
                cited_text="**Halcyon Southtown** has large group tables and couches.",
            )
        ],
    )

    result = aggregate_evidence([c1, c2], [sr])

    assert len(result.candidates[0].search_evidence) == 1
    se = result.candidates[0].search_evidence[0]
    assert se.candidate_id == "id_halcyon"
    assert se.claim == "**Halcyon Southtown** has large group tables and couches."
    assert se.source == EvidenceSource.GOOGLE_SEARCH
    assert se.source_url == "https://example.com/sa-guide"
    assert se.source_title == "SA Guide"
    assert se.planner_query == "quiet coffee shops to work late"
    assert se.executed_search_queries == ["quiet coffee shops San Antonio"]

    # lazydaze should have no search evidence
    assert len(result.candidates[1].search_evidence) == 0
    assert len(result.unmatched_search_evidence) == 0


def test_name_with_punctuation_and_casing_differences_matches() -> None:
    """Punctuation like ampersands or hyphens normalize cleanly."""
    c = Candidate(
        place_id="id_sip",
        name="Sip Brew Bar & Eatery",
    )

    sr = SearchGroundingResult(
        planner_query="quick coffee",
        grounded_text="Sip Brew Bar and Eatery offers high-traffic downtown seating.",
        executed_search_queries=["sip brew bar"],
        sources=[SearchSource(title="Tech District", url="https://sanantoniotechdistrict.com")],
        citations=[
            SearchCitation(
                start_index=0,
                end_index=60,
                source_indices=[0],
                cited_text="Sip Brew Bar and Eatery offers high-traffic downtown seating.",
            )
        ],
    )

    result = aggregate_evidence([c], [sr])
    assert len(result.candidates[0].search_evidence) == 1
    assert result.candidates[0].search_evidence[0].candidate_id == "id_sip"


def test_different_businesses_with_similar_generic_names_not_merged() -> None:
    """Businesses sharing generic words (e.g. 'Coffee', 'Restaurant') are not wrongly merged."""
    c1 = Candidate(place_id="id_1", name="Local Coffee")
    c2 = Candidate(place_id="id_2", name="Gold Coffee")

    sr = SearchGroundingResult(
        planner_query="coffee query",
        grounded_text="Just some general notes about coffee.",
        executed_search_queries=[],
        sources=[],
        citations=[
            SearchCitation(
                start_index=0,
                end_index=36,
                source_indices=[],
                cited_text="Just some general notes about coffee.",
            )
        ],
    )

    result = aggregate_evidence([c1, c2], [sr])
    assert len(result.candidates[0].search_evidence) == 0
    assert len(result.candidates[1].search_evidence) == 0
    assert len(result.unmatched_search_evidence) == 1


def test_ambiguous_search_evidence_remains_unmatched() -> None:
    """When a citation text mentions multiple candidates or is ambiguous, it stays unmatched."""
    c1 = Candidate(place_id="id_1", name="Estate Coffee Company")
    c2 = Candidate(place_id="id_2", name="Halcyon Southtown")

    sr = SearchGroundingResult(
        planner_query="group coffee",
        grounded_text="Comparing Estate Coffee Company and Halcyon Southtown.",
        executed_search_queries=[],
        sources=[],
        citations=[
            SearchCitation(
                start_index=0,
                end_index=54,
                source_indices=[],
                cited_text="Comparing Estate Coffee Company and Halcyon Southtown.",
            )
        ],
    )

    result = aggregate_evidence([c1, c2], [sr])
    assert len(result.candidates[0].search_evidence) == 0
    assert len(result.candidates[1].search_evidence) == 0
    assert len(result.unmatched_search_evidence) == 1


def test_search_only_places_not_added_as_canonical_candidates() -> None:
    """Places found solely in Search are kept in unmatched evidence, never added as candidates."""
    c = Candidate(place_id="id_places_1", name="Halcyon Southtown")

    sr = SearchGroundingResult(
        planner_query="coffee near geekdom",
        grounded_text="Rosella Coffee flagship on Jones Ave features large communal desks.",
        executed_search_queries=[],
        sources=[SearchSource(title="Rosella", url="https://rosellacoffee.com")],
        citations=[
            SearchCitation(
                start_index=0,
                end_index=67,
                source_indices=[0],
                cited_text="Rosella Coffee flagship on Jones Ave features large communal desks.",
            )
        ],
    )

    result = aggregate_evidence([c], [sr])

    # Candidate list must contain only canonical Places candidate
    assert len(result.candidates) == 1
    assert result.candidates[0].candidate.place_id == "id_places_1"
    assert len(result.candidates[0].search_evidence) == 0

    # Unmatched evidence contains Rosella mention
    assert len(result.unmatched_search_evidence) == 1
    assert result.unmatched_search_evidence[0].candidate_id == "unmatched"
    assert "Rosella Coffee" in result.unmatched_search_evidence[0].claim


def test_duplicate_evidence_records_deduplicated() -> None:
    """Duplicate citations for the same candidate and URL are added only once."""
    c = Candidate(place_id="id_1", name="Halcyon Southtown")

    sr = SearchGroundingResult(
        planner_query="query 1",
        grounded_text="text",
        executed_search_queries=["q1"],
        sources=[SearchSource(title="SA Guide", url="https://example.com/guide")],
        citations=[
            SearchCitation(
                start_index=0,
                end_index=30,
                source_indices=[0],
                cited_text="Halcyon Southtown has couches.",
            ),
            SearchCitation(
                start_index=35,
                end_index=65,
                source_indices=[0],
                cited_text="Halcyon Southtown has couches.",
            ),
        ],
    )

    result = aggregate_evidence([c], [sr])
    assert len(result.candidates[0].search_evidence) == 1


def test_empty_search_results_still_returns_places_candidate_evidence() -> None:
    """When search_results is empty, candidate structured evidence is still produced."""
    c = Candidate(place_id="id_1", name="Halcyon", rating=4.5)
    result = aggregate_evidence([c], [])

    assert len(result.candidates) == 1
    assert len(result.candidates[0].structured_evidence) == 1
    assert len(result.candidates[0].search_evidence) == 0
    assert result.unmatched_search_evidence == []


def test_empty_candidates_handles_all_search_as_unmatched() -> None:
    """Empty candidate list treats all search citations as unmatched evidence without error."""
    sr = SearchGroundingResult(
        planner_query="query",
        grounded_text="Some text",
        executed_search_queries=[],
        sources=[],
        citations=[
            SearchCitation(
                start_index=0,
                end_index=9,
                source_indices=[],
                cited_text="Some text",
            )
        ],
    )

    result = aggregate_evidence([], [sr])
    assert len(result.candidates) == 0
    assert len(result.unmatched_search_evidence) == 1


def test_normalize_name_utility() -> None:
    """Verify name normalization strips markdown, punctuation, and extra whitespace."""
    assert normalize_name("**Halcyon Southtown**!") == "halcyon southtown"
    assert normalize_name("Sip Brew Bar & Eatery") == "sip brew bar eatery"
    assert normalize_name("   The Monk's   Indian   Fusion  ") == "the monk s indian fusion"
