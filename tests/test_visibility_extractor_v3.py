"""Comprehensive unit tests for the deterministic visibility observation extractor (V3)."""

from datetime import datetime, timezone

import pytest

from ai_search_journey.models import (
    Candidate,
    Evidence,
    EvidenceSource,
    FanoutQuery,
    FinalRecommendation,
    GroundedAnswer,
    JourneyResult,
    RankedCandidate,
    RetrievalOccurrence,
    SearchGroundingResult,
    SearchIntent,
    SearchSource,
    ToolName,
)
from ai_search_journey.visibility import (
    AmbiguousBrandMatchError,
    BrandProfile,
    BrandRole,
    ScanStatus,
    VisibilityScan,
    build_answer_mention_corpus,
    extract_brand_mentions,
    extract_visibility_scan_bundle,
    match_candidate_to_brand,
)

# ======================================================================
# Fixtures and Helpers
# ======================================================================


@pytest.fixture
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _make_scan(
    utc_now: datetime,
    scan_id: str = "scan_001",
    brand_id: str = "target_merit",
    status: ScanStatus = ScanStatus.COMPLETED,
) -> VisibilityScan:
    return VisibilityScan(
        scan_id=scan_id,
        batch_id="batch_001",
        project_id="proj_austin",
        brand_id=brand_id,
        brand_name_snapshot="Merit Coffee",
        brand_domain_snapshot="meritcoffee.com",
        prompt_id="prompt_001",
        prompt_text_snapshot="best artisan coffee in Austin",
        model_name="gemini-2.5-flash",
        started_at=utc_now,
        completed_at=utc_now,
        status=status,
    )


def _make_target_brand() -> BrandProfile:
    return BrandProfile(
        brand_id="target_merit",
        name="Merit Coffee",
        domain="meritcoffee.com",
        aliases=["Merit Coffee Roasters", "Merit Austin"],
        place_ids=["place_merit_01"],
        domain_aliases=["merit.coffee"],
    )


def _make_competitor_brand() -> BrandProfile:
    return BrandProfile(
        brand_id="comp_houndstooth",
        name="Houndstooth Coffee",
        domain="houndstoothcoffee.com",
        aliases=["Houndstooth"],
        place_ids=["place_hound_01"],
        domain_aliases=[],
    )


def _make_journey(
    candidates: list[Candidate],
    ranking: list[RankedCandidate],
    answer: GroundedAnswer | None = None,
    fanout: list[FanoutQuery] | None = None,
    evidence: list[Evidence] | None = None,
    search_results: list[SearchGroundingResult] | None = None,
) -> JourneyResult:
    return JourneyResult(
        question="best artisan coffee in Austin",
        intent=SearchIntent(category="coffee", reference_location="Austin, TX"),
        candidates=candidates,
        ranking=ranking,
        answer=answer,
        fanout=fanout or [],
        evidence=evidence or [],
        search_results=search_results or [],
    )


# ======================================================================
# 1-4. Input Validation & Contract Invariants
# ======================================================================


def test_completed_scan_produces_valid_bundle(utc_now: datetime) -> None:
    scan = _make_scan(utc_now)
    target = _make_target_brand()
    comp = _make_competitor_brand()
    journey = _make_journey(candidates=[], ranking=[])

    bundle = extract_visibility_scan_bundle(
        scan=scan,
        journey=journey,
        target_brand=target,
        competitor_brands=[comp],
    )
    assert bundle.scan.scan_id == "scan_001"
    assert len(bundle.brand_observations) == 2
    assert bundle.brand_observations[0].role == BrandRole.TARGET
    assert bundle.brand_observations[0].brand_id == "target_merit"
    assert bundle.brand_observations[1].role == BrandRole.COMPETITOR
    assert bundle.brand_observations[1].brand_id == "comp_houndstooth"


def test_non_completed_scan_is_rejected(utc_now: datetime) -> None:
    target = _make_target_brand()
    journey = _make_journey(candidates=[], ranking=[])

    # Pending scan
    scan_pending = VisibilityScan(
        scan_id="s1",
        batch_id="b1",
        project_id="p1",
        brand_id="target_merit",
        brand_name_snapshot="Merit",
        prompt_id="pr1",
        prompt_text_snapshot="coffee",
        model_name="gemini",
        started_at=utc_now,
        status=ScanStatus.PENDING,
    )
    with pytest.raises(ValueError, match="scan.status must be COMPLETED"):
        extract_visibility_scan_bundle(
            scan=scan_pending,
            journey=journey,
            target_brand=target,
            competitor_brands=[],
        )


def test_scan_target_brand_mismatch_is_rejected(utc_now: datetime) -> None:
    scan = _make_scan(utc_now, brand_id="other_brand")
    target = _make_target_brand()
    journey = _make_journey(candidates=[], ranking=[])

    with pytest.raises(ValueError, match="does not match target_brand.brand_id"):
        extract_visibility_scan_bundle(
            scan=scan,
            journey=journey,
            target_brand=target,
            competitor_brands=[],
        )


def test_duplicate_brand_ids_are_rejected(utc_now: datetime) -> None:
    scan = _make_scan(utc_now)
    target = _make_target_brand()
    comp1 = _make_competitor_brand()
    comp_dup = BrandProfile(brand_id="comp_houndstooth", name="Houndstooth 2")
    journey = _make_journey(candidates=[], ranking=[])

    # Duplicate in competitors
    with pytest.raises(ValueError, match="Brand IDs across target and competitors must be unique"):
        extract_visibility_scan_bundle(
            scan=scan,
            journey=journey,
            target_brand=target,
            competitor_brands=[comp1, comp_dup],
        )

    # Target in competitors
    comp_same_as_target = BrandProfile(brand_id="target_merit", name="Merit Again")
    with pytest.raises(ValueError, match="Target brand must not appear in competitor_brands"):
        extract_visibility_scan_bundle(
            scan=scan,
            journey=journey,
            target_brand=target,
            competitor_brands=[comp_same_as_target],
        )


# ======================================================================
# 5-12. Candidate Matching Priority and Ambiguity
# ======================================================================


def test_exact_place_id_candidate_match() -> None:
    target = _make_target_brand()
    cand = Candidate(
        place_id="place_merit_01",
        name="Unrelated Store Name",  # Name differs, but place_id matches
    )
    matched = match_candidate_to_brand(cand, [target])
    assert matched is not None
    assert matched.brand_id == "target_merit"


def test_exact_normalized_domain_match() -> None:
    target = _make_target_brand()
    cand = Candidate(
        place_id="place_unknown_99",
        name="Random Coffee Spot",
        website_url="HTTPS://WWW.MeritCoffee.COM/menu",
    )
    matched = match_candidate_to_brand(cand, [target])
    assert matched is not None
    assert matched.brand_id == "target_merit"


def test_true_subdomain_match() -> None:
    target = _make_target_brand()
    cand = Candidate(
        place_id="place_unknown_99",
        name="South Lamar Location",
        website_url="https://southlamar.meritcoffee.com",
    )
    matched = match_candidate_to_brand(cand, [target])
    assert matched is not None
    assert matched.brand_id == "target_merit"


def test_deceptive_domain_suffix_rejected() -> None:
    target = _make_target_brand()
    cand = Candidate(
        place_id="place_unknown_99",
        name="Phishing Spot",
        website_url="https://meritcoffee.com.evil.test/login",
    )
    matched = match_candidate_to_brand(cand, [target])
    assert matched is None


def test_exact_normalized_name_match() -> None:
    target = _make_target_brand()
    cand = Candidate(
        place_id="place_unknown_99",
        name="  MERIT   COFFEE  ",
    )
    matched = match_candidate_to_brand(cand, [target])
    assert matched is not None
    assert matched.brand_id == "target_merit"


def test_alias_match() -> None:
    target = _make_target_brand()
    cand = Candidate(
        place_id="place_unknown_99",
        name="Merit Coffee Roasters",
    )
    matched = match_candidate_to_brand(cand, [target])
    assert matched is not None
    assert matched.brand_id == "target_merit"


def test_substring_candidate_name_rejected() -> None:
    target = _make_target_brand()
    # "Merit" is a substring of "Merit Coffee", but not an exact match
    cand = Candidate(
        place_id="place_unknown_99",
        name="Merit",
    )
    matched = match_candidate_to_brand(cand, [target])
    assert matched is None

    # "Super Merit Coffee" contains "Merit Coffee", but is not an exact match
    cand2 = Candidate(
        place_id="place_unknown_99",
        name="Super Merit Coffee",
    )
    assert match_candidate_to_brand(cand2, [target]) is None


def test_ambiguous_brand_match_raises_explicit_error() -> None:
    b1 = BrandProfile(brand_id="b1", name="Cafe Alpha", place_ids=["p1"])
    b2 = BrandProfile(brand_id="b2", name="Cafe Beta", place_ids=["p1"])
    cand = Candidate(place_id="p1", name="Shared Place")

    with pytest.raises(AmbiguousBrandMatchError, match="Priority 1"):
        match_candidate_to_brand(cand, [b1, b2])


# ======================================================================
# 13-14. Output Ordering & Stability
# ======================================================================


def test_target_first_and_competitor_order_stability(utc_now: datetime) -> None:
    scan = _make_scan(utc_now)
    target = _make_target_brand()
    comp1 = BrandProfile(brand_id="comp_1", name="Comp 1")
    comp2 = BrandProfile(brand_id="comp_2", name="Comp 2")
    comp3 = BrandProfile(brand_id="comp_3", name="Comp 3")
    journey = _make_journey(candidates=[], ranking=[])

    bundle = extract_visibility_scan_bundle(
        scan=scan,
        journey=journey,
        target_brand=target,
        competitor_brands=[comp1, comp2, comp3],
    )
    obs = bundle.brand_observations
    assert len(obs) == 4
    assert obs[0].brand_id == "target_merit"
    assert obs[0].role == BrandRole.TARGET
    assert obs[1].brand_id == "comp_1"
    assert obs[2].brand_id == "comp_2"
    assert obs[3].brand_id == "comp_3"


# ======================================================================
# 15-19. Answer Mention Extraction
# ======================================================================


def test_answer_mention_count_and_offset() -> None:
    brand = BrandProfile(
        brand_id="b1",
        name="Merit Coffee",
        aliases=["Merit"],
    )
    corpus = "Start: Merit Coffee is awesome. Also Merit serves great espresso."
    mentioned, count, pos = extract_brand_mentions(brand, corpus)
    assert mentioned is True
    # Two mentions: "Merit Coffee" at 7, "Merit" at 37
    assert count == 2
    assert pos == 7


def test_overlapping_aliases_are_not_double_counted() -> None:
    brand = BrandProfile(
        brand_id="b1",
        name="Local Coffee",
        aliases=["Local"],
    )
    corpus = "We recommend Local Coffee in Austin."
    mentioned, count, pos = extract_brand_mentions(brand, corpus)
    assert mentioned is True
    # "Local Coffee" matched; "Local" inside it must not double-count
    assert count == 1
    assert pos == 13


def test_phrase_boundary_prevents_partial_word_match() -> None:
    brand = BrandProfile(brand_id="b1", name="Merit")
    corpus = "We checked out Meritage and it was fine."
    mentioned, count, pos = extract_brand_mentions(brand, corpus)
    assert mentioned is False
    assert count == 0
    assert pos is None


def test_missing_answer_produces_no_mention(utc_now: datetime) -> None:
    scan = _make_scan(utc_now)
    target = _make_target_brand()
    # Journey with answer=None
    journey = _make_journey(candidates=[], ranking=[], answer=None)

    bundle = extract_visibility_scan_bundle(
        scan=scan,
        journey=journey,
        target_brand=target,
        competitor_brands=[],
    )
    target_obs = bundle.brand_observations[0]
    assert target_obs.mentioned is False
    assert target_obs.mention_count == 0
    assert target_obs.first_mention_position is None


def test_punctuation_apostrophe_ampersand_unicode_names() -> None:
    b1 = BrandProfile(brand_id="b1", name="Ben & Jerry's", aliases=["Ben&Jerry's"])
    b2 = BrandProfile(brand_id="b2", name="Café Rosa", aliases=["Rosa's"])
    b3 = BrandProfile(brand_id="b3", name="A-1 Coffee", aliases=["St. Elmo's"])

    corpus = "Visit Ben & Jerry's, then stop by Café Rosa and A-1 Coffee!"
    m1, c1, p1 = extract_brand_mentions(b1, corpus)
    assert m1 is True
    assert c1 == 1
    assert p1 == 6

    m2, c2, p2 = extract_brand_mentions(b2, corpus)
    assert m2 is True
    assert c2 == 1
    assert p2 == 34

    m3, c3, p3 = extract_brand_mentions(b3, corpus)
    assert m3 is True
    assert c3 == 1
    assert p3 == 48


# ======================================================================
# 20-22. Retrieval and Recommendation Observations
# ======================================================================


def test_retrieval_and_recommendation_positions(utc_now: datetime) -> None:
    scan = _make_scan(utc_now)
    target = _make_target_brand()

    # Two matching candidates for the same brand (e.g. two branches)
    cand1 = Candidate(
        place_id="place_merit_01",
        name="Merit Coffee Downtown",
        retrieval_occurrences=[
            RetrievalOccurrence(query_text="coffee", position=3, place_id="place_merit_01")
        ],
    )
    cand2 = Candidate(
        place_id="place_merit_02",
        name="Merit Coffee North",
        website_url="https://meritcoffee.com",
        retrieval_occurrences=[
            RetrievalOccurrence(query_text="coffee", position=1, place_id="place_merit_02")
        ],
    )

    # Only cand1 is in final ranking (rank=2)
    ranked1 = RankedCandidate(
        candidate=cand1,
        rank=2,
        score=8.5,
        preference_supported=1,
    )

    journey = _make_journey(candidates=[cand1, cand2], ranking=[ranked1])
    bundle = extract_visibility_scan_bundle(
        scan=scan,
        journey=journey,
        target_brand=target,
        competitor_brands=[],
    )
    obs = bundle.brand_observations[0]

    # Best retrieval position is min(3, 1) = 1
    assert obs.retrieved is True
    assert obs.best_retrieval_position == 1

    # Recommendation position is 2
    assert obs.recommended is True
    assert obs.recommendation_position == 2


def test_retrieved_but_unranked_is_not_recommended(utc_now: datetime) -> None:
    scan = _make_scan(utc_now)
    target = _make_target_brand()
    cand = Candidate(
        place_id="place_merit_01",
        name="Merit Coffee",
        retrieval_occurrences=[
            RetrievalOccurrence(query_text="coffee", position=4, place_id="place_merit_01")
        ],
    )
    # Empty ranking
    journey = _make_journey(candidates=[cand], ranking=[])
    bundle = extract_visibility_scan_bundle(
        scan=scan,
        journey=journey,
        target_brand=target,
        competitor_brands=[],
    )
    obs = bundle.brand_observations[0]
    assert obs.retrieved is True
    assert obs.best_retrieval_position == 4
    assert obs.recommended is False
    assert obs.recommendation_position is None


# ======================================================================
# 23-28. Citation Extraction and Domain Ownership
# ======================================================================


def test_citation_extraction_sources_and_ownership(utc_now: datetime) -> None:
    scan = _make_scan(utc_now)
    target = _make_target_brand()
    comp = _make_competitor_brand()

    # 1. Search grounding source
    sr = SearchGroundingResult(
        planner_query="artisan roasters Austin",
        grounded_text="text",
        sources=[
            SearchSource(url="https://meritcoffee.com/about"),
            SearchSource(url="https://austinmonthly.com/best-coffee"),
        ],
    )

    # 2. Candidate evidence source
    ev = Evidence(
        candidate_id="place_merit_01",
        attribute="wifi",
        claim="Fast wifi",
        source=EvidenceSource.GOOGLE_SEARCH,
        source_url="https://menu.merit.coffee/drinks",
    )

    # 3. Grounded answer citations
    ans = GroundedAnswer(
        summary="Summary text",
        citations=[
            "https://meritcoffee.com/about",  # duplicate URL across sources
            "https://houndstoothcoffee.com/locations",
            "https://yelp.com/biz/merit-coffee",  # third-party mention
            "https://meritcoffee.com.evil.test/scam",  # deceptive suffix
        ],
    )

    journey = _make_journey(
        candidates=[],
        ranking=[],
        answer=ans,
        search_results=[sr],
        evidence=[ev],
    )

    bundle = extract_visibility_scan_bundle(
        scan=scan,
        journey=journey,
        target_brand=target,
        competitor_brands=[comp],
    )

    # Unique citations collected
    urls = [c.url for c in bundle.citations]
    assert "https://meritcoffee.com/about" in urls
    assert "https://austinmonthly.com/best-coffee" in urls
    assert "https://menu.merit.coffee/drinks" in urls
    assert "https://houndstoothcoffee.com/locations" in urls
    assert "https://yelp.com/biz/merit-coffee" in urls
    assert "https://meritcoffee.com.evil.test/scam" in urls

    # Check deduplication by (scan_id, url, source_type)
    assert len(bundle.citations) == 7

    # Verify owned domain citations
    target_obs = bundle.brand_observations[0]
    assert target_obs.cited is True
    # meritcoffee.com and subdomain menu.merit.coffee
    assert set(target_obs.citation_domains) == {"meritcoffee.com", "menu.merit.coffee"}
    assert "https://meritcoffee.com/about" in target_obs.citation_urls
    assert "https://menu.merit.coffee/drinks" in target_obs.citation_urls
    # Third party and deceptive suffixes not classified as target-owned
    assert "https://austinmonthly.com/best-coffee" not in target_obs.citation_urls
    assert "https://yelp.com/biz/merit-coffee" not in target_obs.citation_urls
    assert "https://meritcoffee.com.evil.test/scam" not in target_obs.citation_urls

    comp_obs = bundle.brand_observations[1]
    assert comp_obs.cited is True
    assert comp_obs.citation_domains == ["houndstoothcoffee.com"]
    assert comp_obs.citation_urls == ["https://houndstoothcoffee.com/locations"]


# ======================================================================
# 29-32. Fan-out Observations (Places vs Search)
# ======================================================================


def test_places_and_search_fanout_observations(utc_now: datetime) -> None:
    scan = _make_scan(utc_now)
    target = _make_target_brand()

    # Candidate with Places retrieval occurrence on task_places_1
    cand = Candidate(
        place_id="place_merit_01",
        name="Merit Coffee",
        retrieval_occurrences=[
            RetrievalOccurrence(
                query_task_id="task_places_1",
                query_text="coffee",
                position=3,
                place_id="place_merit_01",
            )
        ],
    )

    # Evidence linking candidate to search task_search_1
    ev = Evidence(
        candidate_id="place_merit_01",
        attribute="wifi",
        claim="fast wifi",
        source=EvidenceSource.GOOGLE_SEARCH,
        fanout_task_id="task_search_1",
    )

    tasks = [
        FanoutQuery(
            task_id="task_places_1",
            goal="find places",
            query="places query",
            tool=ToolName.GOOGLE_PLACES,
        ),
        FanoutQuery(
            task_id="task_places_2",
            goal="find other places",
            query="other places query",
            tool=ToolName.GOOGLE_PLACES,
        ),
        FanoutQuery(
            task_id="task_search_1",
            goal="search reviews",
            query="search query",
            tool=ToolName.GOOGLE_SEARCH,
        ),
        FanoutQuery(
            task_id="task_search_2",
            goal="search unlinked",
            query="unlinked search",
            tool=ToolName.GOOGLE_SEARCH,
        ),
    ]

    journey = _make_journey(
        candidates=[cand],
        ranking=[],
        fanout=tasks,
        evidence=[ev],
    )

    bundle = extract_visibility_scan_bundle(
        scan=scan,
        journey=journey,
        target_brand=target,
        competitor_brands=[],
    )

    fo_by_task = {fo.task_id: fo for fo in bundle.fanout_observations}

    # Places task 1: brand found with position 3
    assert fo_by_task["task_places_1"].brand_found is True
    assert fo_by_task["task_places_1"].position_in_task == 3

    # Places task 2: brand not found
    assert fo_by_task["task_places_2"].brand_found is False
    assert fo_by_task["task_places_2"].position_in_task is None

    # Search task 1: brand found with structured evidence, position is None (not invented)
    assert fo_by_task["task_search_1"].brand_found is True
    assert fo_by_task["task_search_1"].position_in_task is None

    # Search task 2: no structured evidence linkage -> brand_found is False
    assert fo_by_task["task_search_2"].brand_found is False
    assert fo_by_task["task_search_2"].position_in_task is None


# ======================================================================
# 33-35. Determinism, Immutability & Offline Safety
# ======================================================================


def test_repeated_extraction_is_identical_and_pure(utc_now: datetime) -> None:
    scan = _make_scan(utc_now)
    target = _make_target_brand()
    comp = _make_competitor_brand()

    cand = Candidate(
        place_id="place_merit_01",
        name="Merit Coffee",
        website_url="https://meritcoffee.com",
        retrieval_occurrences=[
            RetrievalOccurrence(
                query_task_id="t1",
                query_text="coffee",
                position=1,
                place_id="place_merit_01",
            )
        ],
    )
    ranked = RankedCandidate(candidate=cand, rank=1, score=10.0)
    ans = GroundedAnswer(
        summary="Merit Coffee is recommended.",
        recommendations=[
            FinalRecommendation(rank=1, candidate_name="Merit Coffee", summary="Great")
        ],
        citations=["https://meritcoffee.com"],
    )
    fanout = [
        FanoutQuery(task_id="t1", goal="places", query="coffee", tool=ToolName.GOOGLE_PLACES)
    ]

    journey = _make_journey(
        candidates=[cand],
        ranking=[ranked],
        answer=ans,
        fanout=fanout,
    )

    # First call
    b1 = extract_visibility_scan_bundle(
        scan=scan,
        journey=journey,
        target_brand=target,
        competitor_brands=[comp],
    )

    # Second call
    b2 = extract_visibility_scan_bundle(
        scan=scan,
        journey=journey,
        target_brand=target,
        competitor_brands=[comp],
    )

    assert b1.model_dump() == b2.model_dump()

    # Inputs not mutated
    assert scan.status == ScanStatus.COMPLETED
    assert len(journey.candidates) == 1
    assert journey.candidates[0].place_id == "place_merit_01"
    assert target.brand_id == "target_merit"
    assert comp.brand_id == "comp_houndstooth"


def test_corpus_construction_handles_all_sections() -> None:
    ans = GroundedAnswer(
        summary="Overall summary.",
        recommendations=[
            FinalRecommendation(
                rank=1,
                candidate_name="Store 1",
                summary="Rec summary.",
                why_it_matches=["Match reason 1", "Match reason 2"],
            )
        ],
        caveats=["Caveat 1"],
    )
    corpus = build_answer_mention_corpus(ans)
    assert "Overall summary." in corpus
    assert "Rec summary." in corpus
    assert "Match reason 1" in corpus
    assert "Match reason 2" in corpus
    assert "Caveat 1" in corpus
