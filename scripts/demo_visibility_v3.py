"""Deterministic CLI demonstration of AI Search Visibility (V3 Milestone 5).

Demonstrates:
- Connecting completed JourneyResult to VisibilityScanBundle extraction.
- Orchestration through run_visibility_scan().
- Persistence in VisibilityRepository.
- Historical visibility metrics calculation.
- Zero network calls, zero external API credentials.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ai_search_journey.models import (
    Candidate,
    Evidence,
    EvidenceSource,
    FanoutQuery,
    FinalRecommendation,
    GroundedAnswer,
    JourneyExecutionTrace,
    JourneyResult,
    JourneyStepTiming,
    RankedCandidate,
    ReferenceLocation,
    RetrievalOccurrence,
    SearchGroundingResult,
    SearchIntent,
    SearchSource,
    StepExecutionStatus,
    ToolName,
)
from ai_search_journey.visibility.models import (
    BrandProfile,
    PromptDefinition,
    VisibilityProject,
)
from ai_search_journey.visibility.repository import InMemoryVisibilityRepository
from ai_search_journey.visibility.runner import run_visibility_scan


def create_demo_journey_fixture() -> JourneyResult:
    """Construct a deterministic completed JourneyResult fixture."""
    # 1. Search intent & location
    intent = SearchIntent(
        category="artisan coffee",
        reference_location="Downtown Austin",
        group_size=2,
        open_after="07:00",
        hard_constraints=["specialty coffee roaster", "wifi available"],
        preferences=["quiet seating", "single origin espresso"],
    )
    ref_loc = ReferenceLocation(
        query="Downtown Austin",
        place_id="ref_austin_downtown",
        name="Downtown Austin",
        latitude=30.2672,
        longitude=-97.7431,
        city="Austin",
        state="TX",
    )

    # 2. Fan-out tasks
    t1 = FanoutQuery(
        task_id="task_places_1",
        goal="Discover candidate specialty roasters",
        query="artisan coffee roasters Downtown Austin",
        tool=ToolName.GOOGLE_PLACES,
    )
    t2 = FanoutQuery(
        task_id="task_search_1",
        goal="Verify quiet workspace and wifi evidence",
        query="Austin Artisan Coffee wifi quiet workspace reviews",
        tool=ToolName.GOOGLE_SEARCH,
    )
    t3 = FanoutQuery(
        task_id="task_places_2",
        goal="Competitor place verification",
        query="Houndstooth Coffee Austin seating",
        tool=ToolName.GOOGLE_PLACES,
    )

    # 3. Candidates
    c1 = Candidate(
        place_id="place_austin_artisan",
        name="Austin Artisan Coffee",
        address="100 Congress Ave, Austin, TX",
        website="https://austinartisan.com",
        rating=4.9,
        user_ratings_total=420,
        retrieval_occurrences=[
            RetrievalOccurrence(
                query_task_id="task_places_1",
                query_text="artisan coffee roasters Downtown Austin",
                position=1,
                place_id="place_austin_artisan",
            )
        ],
    )
    c2 = Candidate(
        place_id="place_houndstooth",
        name="Houndstooth Coffee",
        address="401 Congress Ave, Austin, TX",
        website="https://houndstoothcoffee.com",
        rating=4.7,
        user_ratings_total=850,
        retrieval_occurrences=[
            RetrievalOccurrence(
                query_task_id="task_places_2",
                query_text="Houndstooth Coffee Austin seating",
                position=1,
                place_id="place_houndstooth",
            )
        ],
    )
    c3 = Candidate(
        place_id="place_flat_track",
        name="Flat Track Coffee",
        address="1619 E Cesar Chavez St, Austin, TX",
        website="https://flattrackcoffee.com",
        rating=4.6,
        user_ratings_total=310,
        retrieval_occurrences=[
            RetrievalOccurrence(
                query_task_id="task_places_1",
                query_text="artisan coffee roasters Downtown Austin",
                position=3,
                place_id="place_flat_track",
            )
        ],
    )

    # 4. Search Grounding & Evidence
    search_res = SearchGroundingResult(
        task_id="task_search_1",
        planner_query="Austin Artisan Coffee wifi quiet workspace reviews",
        grounded_text="Austin Artisan Coffee features quiet seating and fast wifi for working.",
        sources=[
            SearchSource(
                title="Austin Artisan Coffee Official Site",
                url="https://austinartisan.com/about",
            ),
            SearchSource(
                title="Eater Austin - Best Roasters",
                url="https://austin.eater.com/maps/best-austin-coffee-shops",
            ),
        ],
    )
    ev1 = Evidence(
        candidate_id="place_austin_artisan",
        attribute="quiet workspace",
        claim="Fast fiber wifi and dedicated laptop tables available",
        source=EvidenceSource.GOOGLE_SEARCH,
        source_url="https://austinartisan.com/about",
        fanout_task_ids=["task_search_1"],
    )

    # 5. Ranking
    ranked1 = RankedCandidate(
        candidate=c1,
        score=9.4,
        rank=1,
        best_retrieval_position=1,
        final_recommendation_position=1,
    )
    ranked2 = RankedCandidate(
        candidate=c2,
        score=8.7,
        rank=2,
        best_retrieval_position=1,
        final_recommendation_position=2,
    )
    ranked3 = RankedCandidate(
        candidate=c3,
        score=7.9,
        rank=3,
        best_retrieval_position=3,
        final_recommendation_position=3,
    )

    # 6. Answer
    answer = GroundedAnswer(
        summary=(
            "Austin Artisan Coffee is the top recommendation for specialty coffee "
            "with quiet seating."
        ),
        recommendations=[
            FinalRecommendation(
                rank=1,
                candidate_name="Austin Artisan Coffee",
                summary="Superb single-origin pour-overs and comfortable quiet workspaces.",
                why_it_matches=["Single origin espresso", "High-speed wifi", "Quiet ambiance"],
            ),
            FinalRecommendation(
                rank=2,
                candidate_name="Houndstooth Coffee",
                summary="Iconic Downtown Austin espresso bar with prime location.",
                why_it_matches=["Excellent espresso", "Convenient location"],
            ),
        ],
        citations=[
            "https://austinartisan.com/about",
            "https://austin.eater.com/maps/best-austin-coffee-shops",
        ],
    )

    # 7. Trace
    trace = JourneyExecutionTrace(
        steps=[
            JourneyStepTiming(
                key="intent", label="Intent Extraction", status=StepExecutionStatus.COMPLETED
            ),
            JourneyStepTiming(
                key="fanout", label="Query Fanout", status=StepExecutionStatus.COMPLETED
            ),
            JourneyStepTiming(
                key="retrieval", label="Candidate Retrieval", status=StepExecutionStatus.COMPLETED
            ),
            JourneyStepTiming(
                key="grounding", label="Evidence Grounding", status=StepExecutionStatus.COMPLETED
            ),
            JourneyStepTiming(
                key="ranking", label="Candidate Ranking", status=StepExecutionStatus.COMPLETED
            ),
            JourneyStepTiming(
                key="answer", label="Answer Synthesis", status=StepExecutionStatus.COMPLETED
            ),
        ],
        total_duration_seconds=2.45,
        is_complete=True,
    )

    return JourneyResult(
        question="Where can I find the best artisan coffee in Austin for working quietly?",
        intent=intent,
        reference_location=ref_loc,
        fanout=[t1, t2, t3],
        candidates=[c1, c2, c3],
        search_results=[search_res],
        evidence=[ev1],
        ranking=[ranked1, ranked2, ranked3],
        answer=answer,
        execution_trace=trace,
    )


def run_demo() -> None:
    print("=" * 80)
    print("AI SEARCH JOURNEY LAB — V3 VISIBILITY SCAN RUNNER DEMO")
    print("Article #14: Beyond Rankings: AI Search Visibility with Gemini and BigQuery")
    print("=" * 80)

    # 1. Setup Profiles
    target_brand = BrandProfile(
        brand_id="austin_artisan",
        name="Austin Artisan Coffee",
        domain="austinartisan.com",
        place_ids=["place_austin_artisan"],
        aliases=["Austin Artisan"],
    )
    comp_houndstooth = BrandProfile(
        brand_id="houndstooth",
        name="Houndstooth Coffee",
        domain="houndstoothcoffee.com",
        place_ids=["place_houndstooth"],
    )
    comp_flattrack = BrandProfile(
        brand_id="flat_track",
        name="Flat Track Coffee",
        domain="flattrackcoffee.com",
        place_ids=["place_flat_track"],
    )

    project = VisibilityProject(
        project_id="austin_specialty_coffee",
        name="Austin Specialty Coffee Track",
        target_brand_id="austin_artisan",
        competitor_brand_ids=["houndstooth", "flat_track"],
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    prompt = PromptDefinition(
        prompt_id="prompt_coffee_work_austin",
        prompt_text="Where can I find the best artisan coffee in Austin for working quietly?",
        category="specialty_coffee",
        reference_location="Austin, TX",
        enabled=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    # 2. Setup In-Memory Visibility Repository
    repository = InMemoryVisibilityRepository()

    # 3. Create Journey Fixture
    journey = create_demo_journey_fixture()

    print(f"\n[1] PROJECT: {project.name} ({project.project_id})")
    print(f"    Target Brand : {target_brand.name} ({target_brand.brand_id})")
    print(f"    Competitors  : {comp_houndstooth.name}, {comp_flattrack.name}")
    print("\n[2] PROMPT DEFINITION:")
    print(f"    Text: \"{prompt.prompt_text}\"")

    # 4. Execute Visibility Scan via Runner
    scan_id = "scan_austin_coffee_001"
    print(f"\n[3] EXECUTING run_visibility_scan(scan_id='{scan_id}')...")
    result = run_visibility_scan(
        journey=journey,
        target_brand=target_brand,
        competitor_brands=[comp_houndstooth, comp_flattrack],
        repository=repository,
        project=project,
        prompt=prompt,
        scan_id=scan_id,
        batch_id="batch_demo_2026_01",
        started_at=datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 1, 15, 10, 30, 3, tzinfo=timezone.utc),
    )

    print(f"[OK] Scan completed and persisted: saved={result.saved}, scan_id={result.scan_id}")

    # 5. Inspect Extracted Bundle
    bundle = result.bundle
    print("\n[4] EXTRACTED BRAND OBSERVATIONS:")
    header = (
        f"{'Brand':<24} {'Role':<12} {'Mentioned':<10} {'Mentions':<9} "
        f"{'Retrieved Pos':<14} {'Rec Pos':<8} {'Cited':<6}"
    )
    print(header)
    print("-" * 88)
    for bo in bundle.brand_observations:
        brand_name = (
            target_brand.name
            if bo.brand_id == target_brand.brand_id
            else (comp_houndstooth.name if bo.brand_id == "houndstooth" else comp_flattrack.name)
        )
        rec_str = str(bo.recommendation_position) if bo.recommendation_position else "-"
        ret_str = str(bo.best_retrieval_position) if bo.best_retrieval_position else "-"
        print(
            f"{brand_name:<24} {bo.role.value:<12} {str(bo.mentioned):<10} "
            f"{bo.mention_count:<9} {ret_str:<14} {rec_str:<8} {str(bo.cited):<6}"
        )

    print(f"\n[5] CITATIONS DISCOVERED ({len(bundle.citations)} total):")
    for cit in bundle.citations:
        print(f"    - URL    : {cit.url}")
        print(f"      Domain : {cit.domain} ({cit.source_type})")
        print(f"      Brands : {', '.join(cit.matched_brand_ids) or 'none'}")

    # 6. Retrieve Historical Metrics from Repository
    print("\n[6] REPOSITORY METRICS CALCULATION:")
    metrics = repository.get_metrics(target_brand.brand_id)
    print(f"    Target Brand           : {metrics.brand_id}")
    print(f"    Total Scans            : {metrics.total_scans}")
    print(f"    Mention Rate           : {metrics.mention_rate:.1%}")
    print(f"    Recommendation Rate    : {metrics.recommendation_rate:.1%}")
    print(f"    Owned Citation Rate    : {metrics.citation_rate:.1%}")
    print(f"    Avg Recommendation Pos : {metrics.average_recommendation_position}")
    print(f"    Share of Voice         : {metrics.share_of_voice:.1%}")
    print(f"    Fan-out Coverage       : {metrics.fanout_coverage:.1%}")

    # 7. Competitor Comparison
    comp_metrics = repository.get_competitor_comparison(
        [target_brand.brand_id, comp_houndstooth.brand_id, comp_flattrack.brand_id]
    )
    print("\n[7] COMPETITOR COMPARISON TABLE:")
    print(f"{'Brand ID':<16} {'Mention Rate':<14} {'Rec Rate':<10} {'SOV':<8} {'Fanout Cov':<12}")
    print("-" * 62)
    for m in comp_metrics:
        print(
            f"{m.brand_id:<16} {m.mention_rate:<14.1%} {m.recommendation_rate:<10.1%} "
            f"{m.share_of_voice:<8.1%} {m.fanout_coverage:<12.1%}"
        )

    print(
        "\n[SUCCESS] V3 Visibility Runner Demo completed deterministically without network calls."
    )
    print("=" * 80)


if __name__ == "__main__":
    run_demo()
