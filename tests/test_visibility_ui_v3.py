"""Unit tests for AI Visibility Streamlit UI (V3 Milestone 6)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ai_search_journey.config import Settings
from ai_search_journey.models import (
    Candidate,
    JourneyExecutionTrace,
    JourneyResult,
    JourneyStepTiming,
    RankedCandidate,
    SearchIntent,
    StepExecutionStatus,
)
from ai_search_journey.visibility.models import (
    BrandObservation,
    BrandRole,
    CitationObservation,
    FanoutObservation,
    ScanStatus,
    VisibilityScan,
    VisibilityScanBundle,
)
from ai_search_journey.visibility.repository import (
    DuplicateScanError,
    InMemoryVisibilityRepository,
)
from ai_search_journey.visibility.runner import VisibilityScanResult
from ai_search_journey.visibility.ui import (
    derive_domain_from_url,
    extract_journey_candidates,
    is_bigquery_available,
    render_scan_results,
    render_visibility_tab,
    slugify_brand_name,
)

# ======================================================================
# Fixtures
# ======================================================================


def _make_sample_candidate(place_id: str, name: str, website: str | None = None) -> Candidate:
    return Candidate(
        place_id=place_id,
        name=name,
        formatted_address=f"123 {name} St",
        latitude=30.2672,
        longitude=-97.7431,
        website_url=website,
    )


def _make_completed_journey(candidate_count: int = 12) -> JourneyResult:
    candidates = [
        _make_sample_candidate(
            place_id=f"place_{i:03d}",
            name=f"Coffee Venue {i}",
            website=f"https://venue{i}.com" if i % 2 == 0 else None,
        )
        for i in range(1, candidate_count + 1)
    ]
    ranked = [
        RankedCandidate(
            candidate=c,
            score=100.0 - i,
            rank=i,
            best_retrieval_position=i,
            final_recommendation_position=i,
        )
        for i, c in enumerate(candidates[:5], 1)
    ]
    trace = JourneyExecutionTrace(
        steps=[
            JourneyStepTiming(key="intent", label="Intent", status=StepExecutionStatus.COMPLETED)
        ],
        total_duration_seconds=1.5,
        is_complete=True,
    )
    return JourneyResult(
        question="Find artisan coffee in Austin",
        intent=SearchIntent(category="coffee", reference_location="Austin"),
        candidates=candidates,
        ranked_candidates=ranked,
        execution_trace=trace,
    )


def _make_sample_bundle(target_id: str = "austin_artisan") -> VisibilityScanBundle:
    from datetime import datetime, timezone

    now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    scan = VisibilityScan(
        scan_id="scan_ui_001",
        batch_id="batch_001",
        project_id="proj_001",
        brand_id=target_id,
        brand_name_snapshot="Austin Artisan Coffee",
        prompt_id="prompt_001",
        prompt_text_snapshot="Find artisan coffee in Austin",
        model_name="gemini-2.5-flash",
        started_at=now,
        completed_at=now,
        status=ScanStatus.COMPLETED,
    )
    brand_obs = [
        BrandObservation(
            scan_id="scan_ui_001",
            brand_id=target_id,
            role=BrandRole.TARGET,
            retrieved=True,
            mentioned=True,
            mention_count=2,
            first_mention_position=1,
            recommended=True,
            recommendation_position=1,
            cited=True,
            citation_urls=["https://austinartisan.com/about"],
            citation_domains=["austinartisan.com"],
            best_retrieval_position=1,
        ),
        BrandObservation(
            scan_id="scan_ui_001",
            brand_id="houndstooth",
            role=BrandRole.COMPETITOR,
            retrieved=True,
            mentioned=False,
            mention_count=0,
            recommended=True,
            recommendation_position=2,
            cited=False,
            best_retrieval_position=2,
        ),
    ]
    citations = [
        CitationObservation(
            scan_id="scan_ui_001",
            url="https://austinartisan.com/about",
            domain="austinartisan.com",
            source_type="google_search",
            matched_brand_ids=[target_id],
            is_target_owned=True,
        )
    ]
    fanouts = [
        FanoutObservation(
            scan_id="scan_ui_001",
            task_id="F1",
            query_text="best coffee in Austin",
            tool="google_places",
            brand_id=target_id,
            brand_found=True,
            position_in_task=1,
        )
    ]
    return VisibilityScanBundle(
        scan=scan,
        brand_observations=brand_obs,
        fanout_observations=fanouts,
        citations=citations,
    )


# ======================================================================
# Unit Tests
# ======================================================================


def test_slugify_brand_name() -> None:
    """Verify brand name slugification handles special characters, casing, and spaces."""
    assert slugify_brand_name("Austin Artisan Coffee") == "austin_artisan_coffee"
    assert slugify_brand_name("Caffè & Bar (Central)!") == "caff_bar_central"
    assert slugify_brand_name("   ") == "brand"
    assert slugify_brand_name("123 Coffee") == "123_coffee"


def test_derive_domain_from_url() -> None:
    """Verify clean domain extraction from various URL formats."""
    assert derive_domain_from_url("https://www.austinartisan.com/about") == "austinartisan.com"
    assert derive_domain_from_url("http://sub.domain.co.uk/path?q=1") == "sub.domain.co.uk"
    assert derive_domain_from_url("austinartisan.com") == "austinartisan.com"
    assert derive_domain_from_url(None) is None
    assert derive_domain_from_url("   ") is None


def test_extract_journey_candidates_limits_to_10_and_preserves_order() -> None:
    """Verify candidate extraction pulls up to 10 unique candidates without hardcoding."""
    journey = _make_completed_journey(candidate_count=15)
    candidates = extract_journey_candidates(journey, limit=10)

    assert len(candidates) == 10
    # First candidate should match ranked candidate 1
    assert candidates[0].place_id == "place_001"
    # Ensure no duplicates
    pids = [c.place_id for c in candidates]
    assert len(pids) == len(set(pids))


def test_render_visibility_tab_with_no_journey(monkeypatch: object) -> None:
    """Verify clear guidance message is rendered when no journey is available."""
    mock_st = MagicMock()
    mock_st.session_state = {}

    with patch("ai_search_journey.visibility.ui.st", mock_st):
        render_visibility_tab(journey=None)

        mock_st.subheader.assert_called_once_with("AI Visibility [V3]")
        mock_st.caption.assert_called_once_with(
            "Measure how configured brands appear in completed AI search journeys."
        )
        mock_st.info.assert_called_once_with(
            "Run a Search to Decision journey first, then return here for visibility analysis."
        )
        # Should not render columns or inputs
        assert mock_st.columns.call_count == 0


def test_render_visibility_tab_with_incomplete_journey() -> None:
    """Verify guidance message when journey trace is not complete."""
    mock_st = MagicMock()
    mock_st.session_state = {}

    journey = _make_completed_journey()
    assert journey.execution_trace is not None
    journey.execution_trace.is_complete = False

    with patch("ai_search_journey.visibility.ui.st", mock_st):
        render_visibility_tab(journey=journey)
        mock_st.info.assert_called_once_with(
            "Run a Search to Decision journey first, then return here for visibility analysis."
        )
        assert mock_st.columns.call_count == 0


def test_is_bigquery_available_status() -> None:
    """Verify BigQuery availability returns boolean and descriptive string."""
    is_avail, msg = is_bigquery_available()
    assert isinstance(is_avail, bool)
    assert isinstance(msg, str)
    assert len(msg) > 0


def test_partial_or_missing_bigquery_config_leaves_history_unavailable() -> None:
    """Verify that partial or missing BigQuery configuration marks history unavailable."""
    # Simulate dependency installed
    mock_spec = MagicMock()
    with patch("importlib.util.find_spec", return_value=mock_spec):
        # 1. Missing project
        cfg_no_project = Settings(
            bigquery_project=None,
            bigquery_dataset="ai_search_journey_v3",
            bigquery_location="US",
        )
        is_avail, msg = is_bigquery_available(cfg_no_project)
        assert is_avail is False
        assert "bigquery_project" in msg

        # 2. Missing/blank dataset
        cfg_no_dataset = Settings(
            bigquery_project="test-proj",
            bigquery_dataset="",
            bigquery_location="US",
        )
        is_avail, msg = is_bigquery_available(cfg_no_dataset)
        assert is_avail is False
        assert "bigquery_dataset" in msg

        # 3. Missing/blank location
        cfg_no_loc = Settings(
            bigquery_project="test-proj",
            bigquery_dataset="ai_search_journey_v3",
            bigquery_location="",
        )
        is_avail, msg = is_bigquery_available(cfg_no_loc)
        assert is_avail is False
        assert "bigquery_location" in msg

        # 4. Invalid project identifier (e.g. contains special chars)
        cfg_bad_proj = Settings(
            bigquery_project="bad;project`id",
            bigquery_dataset="ai_search_journey_v3",
            bigquery_location="US",
        )
        is_avail, msg = is_bigquery_available(cfg_bad_proj)
        assert is_avail is False
        assert "configuration error" in msg

    # 5. Missing dependency simulated
    with patch("importlib.util.find_spec", return_value=None):
        cfg_valid = Settings(
            bigquery_project="valid-proj",
            bigquery_dataset="ai_search_journey_v3",
            bigquery_location="US",
        )
        is_avail, msg = is_bigquery_available(cfg_valid)
        assert is_avail is False
        assert "not installed" in msg


def test_partial_bigquery_config_safely_falls_back_to_session_only_in_ui() -> None:
    """Verify UI safely falls back to Session only repository when BigQuery config is partial."""
    mock_st = MagicMock()
    mock_st.session_state = {
        "v3_target_name_input": "Austin Artisan Coffee",
        "v3_target_domain_input": "",
        "v3_target_aliases_input": "",
        "v3_target_place_id_input": "",
        "v3_custom_competitors": [],
    }

    mock_st.button.side_effect = lambda label, **kwargs: label == "Run Visibility Analysis"
    mock_st.text_input.side_effect = lambda label, **kwargs: (
        "Austin Artisan Coffee" if "name" in str(label).lower() else str(kwargs.get("value", ""))
    )
    mock_st.multiselect.return_value = []
    mock_st.columns.side_effect = lambda spec, **kwargs: (
        [MagicMock() for _ in range(spec)]
        if isinstance(spec, int)
        else [MagicMock() for _ in range(len(spec))]
    )

    journey = _make_completed_journey()

    # Settings with missing project
    partial_settings = Settings(
        bigquery_project=None,
        bigquery_dataset="ai_search_journey_v3",
        bigquery_location="US",
    )

    with (
        patch("ai_search_journey.visibility.ui.settings", partial_settings),
        patch("ai_search_journey.visibility.ui.st", mock_st),
        patch("ai_search_journey.visibility.ui.run_visibility_scan") as mock_runner,
    ):
        mock_runner.return_value = VisibilityScanResult(
            bundle=_make_sample_bundle("austin_artisan_coffee"),
            saved=True,
        )

        render_visibility_tab(journey=journey)

        # Radio options must ONLY offer "Session only (In-Memory)" and be disabled
        radio_calls = mock_st.radio.call_args_list
        assert len(radio_calls) >= 1
        call_kwargs = radio_calls[0].kwargs
        call_args = radio_calls[0].args
        options_passed = call_kwargs.get("options", call_args[1] if len(call_args) > 1 else None)
        assert options_passed == ["Session only (In-Memory)"]
        assert call_kwargs.get("disabled") is True

        # Runner must be called with InMemoryVisibilityRepository
        assert mock_runner.call_count == 1
        used_repo = mock_runner.call_args.kwargs["repository"]
        assert isinstance(used_repo, InMemoryVisibilityRepository)


def test_render_scan_results_displays_kpi_cards_and_narrative_mention() -> None:
    """Verify KPI metric cards, brand table, and expanders render with narrative mention."""
    bundle = _make_sample_bundle("austin_artisan")
    scan_result = VisibilityScanResult(bundle=bundle, saved=True)

    repo = InMemoryVisibilityRepository()
    repo.save_bundle(bundle)

    mock_st = MagicMock()
    mock_cols = [MagicMock() for _ in range(6)]
    mock_st.columns.return_value = mock_cols

    with patch("ai_search_journey.visibility.ui.st", mock_st):
        render_scan_results(
            scan_result=scan_result,
            repository=repo,
            target_brand_id="austin_artisan",
        )

        # Check KPI card metrics
        metric_labels = [call.args[0] for call in mock_st.metric.call_args_list]
        assert "Total Scans" in metric_labels
        assert "Narrative Mention" in metric_labels
        assert "Recommendation" in metric_labels
        assert "Owned Citation" in metric_labels
        assert "Share of Voice" in metric_labels
        assert "Fan-out Coverage" in metric_labels

        # Check Brand Comparison Table dataframe call
        assert mock_st.dataframe.call_count >= 1
        df_args = mock_st.dataframe.call_args_list[0].args[0]
        assert isinstance(df_args, list)
        assert len(df_args) == 2
        row_0 = df_args[0]
        assert "Narrative Mention" in row_0
        assert row_0["Narrative Mention"] == "✓ Yes"
        assert row_0["Role"] == "Target"
        assert row_0["Brand"] == "austin_artisan"

        # Check expanders for citations, fanout, and raw json
        expander_titles = [call.args[0] for call in mock_st.expander.call_args_list]
        assert any("Citations Discovered" in title for title in expander_titles)
        assert any("Fan-Out Grounding Tasks" in title for title in expander_titles)
        assert any("Raw Visibility Scan Bundle" in title for title in expander_titles)


def test_ui_handles_duplicate_scan_error_cleanly() -> None:
    """Verify UI catches DuplicateScanError and displays warning."""
    mock_st = MagicMock()
    mock_st.session_state = {
        "v3_target_name_input": "Austin Artisan Coffee",
        "v3_target_domain_input": "austinartisan.com",
        "v3_target_aliases_input": "",
        "v3_target_place_id_input": "",
        "v3_custom_competitors": [],
    }

    # Simulate button click
    def mock_button(label: str, **kwargs: object) -> bool:
        if label == "Run Visibility Analysis":
            return True
        return False

    def mock_text_input(label: str, **kwargs: object) -> str:
        key = str(kwargs.get("key", ""))
        if "name" in str(label).lower() or key == "v3_target_name_input":
            return "Austin Artisan Coffee"
        return str(kwargs.get("value", ""))

    mock_st.button.side_effect = mock_button
    mock_st.text_input.side_effect = mock_text_input
    mock_st.multiselect.return_value = []
    mock_st.columns.return_value = [MagicMock(), MagicMock()]

    journey = _make_completed_journey()

    with (
        patch("ai_search_journey.visibility.ui.st", mock_st),
        patch("ai_search_journey.visibility.ui.run_visibility_scan") as mock_runner,
    ):
        mock_runner.side_effect = DuplicateScanError("Conflicting scan bundle already exists")
        render_visibility_tab(journey=journey)

        # Warning should be displayed for duplicate scan error
        mock_st.warning.assert_called()
        warning_msg = mock_st.warning.call_args[0][0]
        assert "Duplicate Scan" in warning_msg
