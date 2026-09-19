"""Unit tests for UI formatting and presentation components."""

from ai_search_journey.models import (
    Candidate,
    CandidateConstraintEvaluation,
    CategoryEligibility,
    ConstraintEvaluationResult,
    ConstraintResult,
    ConstraintStatus,
    ConstraintSupport,
    JourneyResult,
    RankedCandidate,
    SearchIntent,
)
from ai_search_journey.ui_formatters import (
    build_constraint_matrix_data,
    format_candidate_summary_card,
    format_constraint_cell,
    format_intent_attributes,
    format_source_badge,
    get_marker_label,
    redact_api_key,
)


def test_format_source_badge() -> None:
    """Verify source badge formatting logic."""
    assert format_source_badge("google_places") == "GOOGLE PLACES"
    assert format_source_badge("google_search") == "GOOGLE SEARCH"
    assert format_source_badge("places,search") == "PLACES + SEARCH"
    assert format_source_badge("derived") == "DERIVED"


def test_format_constraint_cell_provenance() -> None:
    """Verify matrix cell formatting for supported, unknown, and not satisfied."""
    r_unknown = ConstraintResult(constraint="Quiet", status=ConstraintStatus.UNKNOWN)
    assert format_constraint_cell(r_unknown) == "?"

    r_places = ConstraintResult(
        constraint="Open after 20:00",
        status=ConstraintStatus.SUPPORTED,
        supporting_evidence=[
            ConstraintSupport(source_type="google_places", fanout_task_ids=["F1"])
        ],
    )
    assert format_constraint_cell(r_places) == "✓ PLACES [F1]"

    r_both = ConstraintResult(
        constraint="Open after 20:00",
        status=ConstraintStatus.SUPPORTED,
        supporting_evidence=[
            ConstraintSupport(source_type="google_places", fanout_task_ids=["F1"]),
            ConstraintSupport(source_type="google_search", fanout_task_ids=["F3"]),
        ],
    )
    assert format_constraint_cell(r_both) == "✓ PLACES + SEARCH [F1,F3]"

    r_failed = ConstraintResult(
        constraint="Open after 20:00",
        status=ConstraintStatus.NOT_SATISFIED,
        supporting_evidence=[
            ConstraintSupport(source_type="google_places", fanout_task_ids=["F2"])
        ],
    )
    assert format_constraint_cell(r_failed) == "✗ PLACES [F2]"


def test_build_constraint_matrix_data() -> None:
    """Verify constraint matrix rows and headers generation."""
    c1 = Candidate(place_id="c1", name="Place One")
    eval1 = CandidateConstraintEvaluation(
        candidate=c1,
        results=[
            ConstraintResult(
                constraint="Category: coffee shop",
                status=ConstraintStatus.SUPPORTED,
                supporting_evidence=[
                    ConstraintSupport(source_type="google_places", fanout_task_ids=["F1"])
                ],
            ),
            ConstraintResult(
                constraint="Open after 20:00",
                status=ConstraintStatus.UNKNOWN,
            ),
        ],
    )

    journey = JourneyResult(
        question="Find coffee",
        intent=SearchIntent(category="coffee shop"),
        constraint_result=ConstraintEvaluationResult(evaluations=[eval1]),
    )

    headers, rows = build_constraint_matrix_data(journey)
    assert headers == ["Candidate", "Category: coffee shop", "Open after 20:00"]
    assert len(rows) == 1
    assert rows[0]["Candidate"] == "Place One"
    assert rows[0]["Category: coffee shop"] == "✓ PLACES [F1]"
    assert rows[0]["Open after 20:00"] == "?"


def test_marker_label_mapping() -> None:
    """Verify marker label mapping A/B/C."""
    assert get_marker_label(0) == "A"
    assert get_marker_label(1) == "B"
    assert get_marker_label(2) == "C"
    assert get_marker_label(3) == "4"


def test_format_candidate_summary_card() -> None:
    """Verify summary card extraction for Top 3 candidates."""
    cand = Candidate(
        place_id="p1",
        name="King William Coffee",
        primary_type="coffee_shop",
        place_types=["coffee_shop", "cafe"],
        rating=4.7,
        user_rating_count=350,
        google_maps_url="https://maps.google.com/test",
    )
    ranked = RankedCandidate(
        candidate=cand,
        score=65.5,
        rank=1,
        distance_miles=0.84,
        category_eligibility=CategoryEligibility(
            status=ConstraintStatus.SUPPORTED,
            requested_category="coffee shop",
            primary_type="coffee_shop",
            place_types=["coffee_shop"],
            explanation="Match",
        ),
    )

    card = format_candidate_summary_card(ranked, 0)
    assert card["letter"] == "A"
    assert card["rank"] == "#1"
    assert card["name"] == "King William Coffee"
    assert card["score"] == "65.50"
    assert card["distance"] == "0.84 mi"
    assert card["category_status"] == "SUPPORTED"
    assert card["primary_type"] == "coffee_shop"
    assert card["google_maps_url"] == "https://maps.google.com/test"


def test_format_intent_attributes() -> None:
    """Verify format_intent_attributes extracts clean key-values."""
    intent = SearchIntent(
        category="coffee shop",
        reference_location="Geekdom San Antonio",
        group_size=6,
        open_after="20:00",
        hard_constraints=["quiet"],
        preferences=["wifi"],
    )
    attrs = dict(format_intent_attributes(intent))
    assert attrs["Requested Category"] == "coffee shop"
    assert attrs["Reference Location"] == "Geekdom San Antonio"
    assert attrs["Group Size"] == "6"
    assert attrs["Open After"] == "20:00"
    assert attrs["Hard Constraints"] == "quiet"
    assert attrs["Preferences"] == "wifi"


def test_api_key_redaction() -> None:
    """Verify API keys are properly redacted from displayed URLs."""
    url = "https://maps.googleapis.com/maps/api/staticmap?center=29.4,-98.5&key=AIzaSyA_RealSecretKey123"
    redacted = redact_api_key(url)
    assert "AIzaSyA_RealSecretKey123" not in redacted
    assert "key=REDACTED" in redacted
    assert redact_api_key(None) == ""


def test_ui_assets_fallback_and_loading(tmp_path: object) -> None:
    """Verify load_optional_image returns None for missing files and Path for existing files."""
    from pathlib import Path

    from PIL import Image

    from ai_search_journey.ui_assets import (
        autocrop_image,
        get_available_branding_assets,
        load_and_autocrop_image,
        load_optional_image,
        render_demo_context,
        render_header_logos,
    )

    # Missing file returns None gracefully
    missing_file = Path("assets/nonexistent_logo.png")
    assert load_optional_image(missing_file) is None
    assert load_and_autocrop_image(missing_file) is None

    # Empty dictionary keys if assets do not exist
    assets = get_available_branding_assets()
    assert isinstance(assets, dict)
    assert "gdg" in assets
    assert "google_startup" in assets

    # Real file returns valid Path
    temp_dir = Path(str(tmp_path))
    test_img_path = temp_dir / "test_logo.png"

    # Create a 100x100 white image with a small 20x20 red square in the center
    img = Image.new("RGB", (100, 100), color="white")
    for x in range(40, 60):
        for y in range(40, 60):
            img.putpixel((x, y), (255, 0, 0))
    img.save(test_img_path)

    loaded = load_optional_image(test_img_path)
    assert loaded is not None
    assert loaded == test_img_path

    # Autocrop trims surrounding white background
    cropped = load_and_autocrop_image(test_img_path, padding=2)
    assert cropped is not None
    # Cropped dimensions should be significantly smaller than original 100x100
    assert cropped.size[0] < 100
    assert cropped.size[1] < 100

    # Direct autocrop helper
    cropped_direct = autocrop_image(img, padding=2)
    assert cropped_direct.size[0] < 100

    # Helpers execute without error
    render_demo_context()
    render_header_logos()


def test_format_step_status_symbol() -> None:
    """Verify execution step status symbols format correctly."""
    from ai_search_journey.models import StepExecutionStatus
    from ai_search_journey.ui_formatters import (
        format_step_duration,
        format_step_status_symbol,
    )

    assert format_step_status_symbol(StepExecutionStatus.COMPLETED) == "✓"
    assert format_step_status_symbol(StepExecutionStatus.RUNNING) == "→"
    assert format_step_status_symbol(StepExecutionStatus.FAILED) == "✗"
    assert format_step_status_symbol(StepExecutionStatus.PENDING) == "○"
    assert format_step_status_symbol("unknown") == "○"

    assert format_step_duration(None) == ""
    assert format_step_duration(0.012) == "0.01s"
    assert format_step_duration(1.84) == "1.8s"


def test_render_execution_timeline_mock() -> None:
    """Verify render_execution_timeline executes without exceptions for valid trace."""
    from ai_search_journey.models import (
        JourneyExecutionTrace,
        JourneyStepTiming,
        StepExecutionStatus,
    )
    from ai_search_journey.ui_formatters import render_execution_timeline

    trace = JourneyExecutionTrace(
        steps=[
            JourneyStepTiming(
                key="intent",
                label="Understanding intent",
                status=StepExecutionStatus.COMPLETED,
                duration_seconds=0.8,
                detail="Category: 'coffee shop'",
            ),
            JourneyStepTiming(
                key="fanout",
                label="Planning query fan-out",
                status=StepExecutionStatus.RUNNING,
            ),
            JourneyStepTiming(
                key="places",
                label="Retrieving Google Places candidates",
                status=StepExecutionStatus.PENDING,
            ),
        ],
        total_duration_seconds=1.2,
        is_complete=False,
    )

    # Calling with valid trace executes without error
    render_execution_timeline(trace, total_elapsed=1.2)
    # Calling with non-trace returns gracefully
    render_execution_timeline(None)


def test_format_preview_list_and_extract_source_domain() -> None:
    """Verify preview list truncation and source domain extraction."""
    from ai_search_journey.ui_formatters import (
        extract_source_domain,
        format_preview_list,
    )

    items = [f"item {i}" for i in range(8)]
    preview = format_preview_list(items, max_items=5)
    assert len(preview) == 6
    assert preview[0] == "- item 0"
    assert preview[4] == "- item 4"
    assert "+ 3 more" in preview[5]

    short_items = ["a", "b"]
    short_preview = format_preview_list(short_items, max_items=5)
    assert len(short_preview) == 2
    assert short_preview == ["- a", "- b"]
    assert format_preview_list([]) == []

    # Domain extraction
    assert extract_source_domain("https://www.sacurrent.com/dining/halcyon") == "sacurrent.com"
    assert extract_source_domain("https://yelp.com/biz/local-coffee") == "yelp.com"
    assert extract_source_domain("") == ""


def test_render_execution_timeline_with_full_journey() -> None:
    """Verify render_execution_timeline handles complete journey inspection without error."""
    from ai_search_journey.models import (
        Candidate,
        CandidateConstraintEvaluation,
        CandidateEvidence,
        ConstraintEvaluationResult,
        ConstraintResult,
        ConstraintStatus,
        Evidence,
        EvidenceAggregationResult,
        EvidenceSource,
        FanoutQuery,
        JourneyExecutionTrace,
        JourneyResult,
        JourneyStepTiming,
        RankedCandidate,
        SearchGroundingResult,
        SearchIntent,
        SearchSource,
        StepExecutionStatus,
        ToolName,
    )
    from ai_search_journey.ui_formatters import render_execution_timeline

    trace = JourneyExecutionTrace(
        steps=[
            JourneyStepTiming(
                key="normalize",
                label="Normalizing candidates",
                status=StepExecutionStatus.COMPLETED,
                duration_seconds=0.05,
                detail="20 raw records → 10 unique candidates (10 duplicates removed)",
            ),
            JourneyStepTiming(
                key="search",
                label="Grounding with Google Search",
                status=StepExecutionStatus.COMPLETED,
                duration_seconds=1.5,
                detail="1 tasks · 2 queries · 2 sources",
            ),
            JourneyStepTiming(
                key="evidence",
                label="Aggregating evidence",
                status=StepExecutionStatus.COMPLETED,
                duration_seconds=0.1,
                detail="4 claims across 1 candidates",
            ),
            JourneyStepTiming(
                key="constraints",
                label="Evaluating constraints",
                status=StepExecutionStatus.COMPLETED,
                duration_seconds=0.02,
            ),
            JourneyStepTiming(
                key="ranking",
                label="Ranking candidates",
                status=StepExecutionStatus.COMPLETED,
                duration_seconds=0.01,
            ),
        ],
        total_duration_seconds=2.0,
        is_complete=True,
    )

    c1 = Candidate(place_id="p1", name="Kafe Krave", primary_type="coffee_shop")
    journey = JourneyResult(
        question="Coffee",
        intent=SearchIntent(category="coffee shop"),
        fanout=[
            FanoutQuery(
                task_id="F3",
                goal="Check seating",
                query="seating",
                tool=ToolName.GOOGLE_SEARCH,
            )
        ],
        candidates=[c1],
        search_results=[
            SearchGroundingResult(
                task_id="F3",
                planner_query="Kafe Krave seating",
                grounded_text="Spacious seating available",
                executed_search_queries=[
                    "Kafe Krave seating reviews",
                    "Kafe Krave group capacity",
                ],
                sources=[
                    SearchSource(
                        title="Current Review",
                        url="https://www.sacurrent.com/krave",
                    ),
                    SearchSource(
                        title="Yelp Page",
                        url="https://yelp.com/krave",
                    ),
                ],
            )
        ],
        evidence_result=EvidenceAggregationResult(
            candidates=[
                CandidateEvidence(
                    candidate=c1,
                    structured_evidence=[
                        Evidence(
                            candidate_id="p1",
                            attribute="opening_hours",
                            claim="Open late",
                            source=EvidenceSource.GOOGLE_PLACES,
                        )
                    ],
                    search_evidence=[
                        Evidence(
                            candidate_id="p1",
                            attribute="group_seating",
                            claim="Large communal tables",
                            source=EvidenceSource.GOOGLE_SEARCH,
                            source_url="https://sacurrent.com/krave",
                            fanout_task_id="F3",
                        )
                    ],
                )
            ]
        ),
        constraint_result=ConstraintEvaluationResult(
            evaluations=[
                CandidateConstraintEvaluation(
                    candidate=c1,
                    results=[
                        ConstraintResult(
                            constraint="Open after 8pm",
                            status=ConstraintStatus.SUPPORTED,
                        )
                    ],
                )
            ]
        ),
        ranking=[
            RankedCandidate(
                candidate=c1,
                score=78.5,
                rank=1,
                hard_supported=1,
                distance_miles=0.5,
                proximity_score=4.5,
                quality_score=2.0,
            )
        ],
        execution_trace=trace,
    )

    # Render complete journey details
    render_execution_timeline(trace, journey=journey)





