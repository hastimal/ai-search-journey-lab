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
    build_competitor_profiles,
    derive_domain_from_url,
    extract_journey_candidates,
    is_bigquery_available,
    normalize_brand_name,
    render_scan_results,
    render_visibility_tab,
    slugify_brand_name,
    validate_scan_inputs,
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
        ranking=ranked,
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


def test_zen_haus_cafe_scenario_enables_run_path() -> None:
    """Verify Zen Haus Cafe with blank optional fields and 3 competitors enables run path."""
    journey = _make_completed_journey(candidate_count=5)
    candidates = extract_journey_candidates(journey, limit=10)
    cand_lookup = {c.name: c for c in candidates}

    # 1. Test validation logic directly
    selected_names = [candidates[0].name, candidates[1].name, candidates[2].name]
    competitor_profiles, comp_errors = build_competitor_profiles(
        selected_candidate_names=selected_names,
        candidate_lookup=cand_lookup,
        custom_competitors=[],
    )
    assert len(competitor_profiles) == 3
    assert len(comp_errors) == 0

    target_profile, val_errors = validate_scan_inputs(
        target_name="Zen Haus Cafe",
        target_domain="",  # Optional blank
        target_aliases_raw="",  # Optional blank
        target_place_id="",  # Optional blank
        competitor_profiles=competitor_profiles,
        comp_build_errors=comp_errors,
    )
    assert target_profile is not None
    assert target_profile.brand_id == "zen_haus_cafe"
    assert target_profile.name == "Zen Haus Cafe"
    assert target_profile.domain is None
    assert target_profile.aliases == []
    assert target_profile.place_ids == []
    assert val_errors == []

    # 2. Test UI execution flow in render_visibility_tab
    mock_st = MagicMock()
    mock_st.session_state = {
        "v3_target_name": "Zen Haus Cafe",
        "v3_target_domain": "",
        "v3_target_aliases": "",
        "v3_target_place_id": "",
        "v3_custom_competitors": [],
        "v3_cand_multiselect": selected_names,
    }

    button_disabled_states: list[bool] = []

    def mock_button(label: str, **kwargs: object) -> bool:
        if label == "Run Visibility Analysis":
            button_disabled_states.append(bool(kwargs.get("disabled", False)))
            return True
        return False

    def mock_text_input(label: str, **kwargs: object) -> str:
        key = str(kwargs.get("key", ""))
        if key == "v3_target_name" or "name" in str(label).lower():
            return "Zen Haus Cafe"
        return ""

    mock_st.button.side_effect = mock_button
    mock_st.text_input.side_effect = mock_text_input
    mock_st.multiselect.return_value = selected_names
    mock_st.columns.side_effect = lambda spec, **kwargs: (
        [MagicMock() for _ in range(spec)]
        if isinstance(spec, int)
        else [MagicMock() for _ in range(len(spec))]
    )

    with (
        patch("ai_search_journey.visibility.ui.st", mock_st),
        patch("ai_search_journey.visibility.ui.run_visibility_scan") as mock_runner,
    ):
        mock_runner.return_value = VisibilityScanResult(
            bundle=_make_sample_bundle("zen_haus_cafe"),
            saved=True,
        )

        render_visibility_tab(journey=journey)

        # Run button must be enabled (disabled=False)
        assert len(button_disabled_states) == 1
        assert button_disabled_states[0] is False

        # No blocking validation error box shown
        warning_calls = [
            str(call.args[0]) for call in mock_st.warning.call_args_list if call.args
        ]
        assert not any("Cannot run visibility analysis" in w for w in warning_calls)

        # Runner executed with target and 3 competitors
        assert mock_runner.call_count == 1
        runner_kwargs = mock_runner.call_args.kwargs
        assert runner_kwargs["target_brand"].name == "Zen Haus Cafe"
        assert len(runner_kwargs["competitor_brands"]) == 3


def test_selected_candidates_and_displayed_competitors_are_identical() -> None:
    """Verify competitor BrandProfiles and displayed output exactly match current selections."""
    journey = _make_completed_journey(candidate_count=5)
    candidates = extract_journey_candidates(journey, limit=10)
    cand_lookup = {c.name: c for c in candidates}

    # Selected candidate names
    selected_names = [candidates[0].name, candidates[1].name, candidates[2].name]

    # Directly derived profiles
    competitor_profiles, errors = build_competitor_profiles(
        selected_candidate_names=selected_names,
        candidate_lookup=cand_lookup,
        custom_competitors=[],
    )

    assert errors == []
    assert len(competitor_profiles) == 3
    derived_names = [cp.name for cp in competitor_profiles]
    assert derived_names == selected_names

    # Check UI rendering
    mock_st = MagicMock()
    mock_st.session_state = {
        "v3_target_name": "Zen Haus Cafe",
        "v3_cand_multiselect": selected_names,
        "v3_custom_competitors": [],
    }
    mock_st.multiselect.return_value = selected_names
    mock_st.text_input.side_effect = lambda label, **kwargs: (
        "Zen Haus Cafe" if "name" in str(label).lower() else ""
    )
    mock_st.columns.side_effect = lambda spec, **kwargs: (
        [MagicMock() for _ in range(spec)]
        if isinstance(spec, int)
        else [MagicMock() for _ in range(len(spec))]
    )

    with patch("ai_search_journey.visibility.ui.st", mock_st):
        render_visibility_tab(journey=journey)

        # Find markdown call for Configured Competitors preview
        markdown_calls = [str(call.args[0]) for call in mock_st.markdown.call_args_list]
        expected_summary = ", ".join([f"`{name}`" for name in selected_names])
        assert any(expected_summary in m for m in markdown_calls)


def test_invalid_cases_show_actionable_error_box_rather_than_silent_disable() -> None:
    """Verify invalid states display actionable validation warnings above disabled button."""
    journey = _make_completed_journey(candidate_count=5)
    candidates = extract_journey_candidates(journey, limit=10)

    # 1. Blank Target Name
    mock_st = MagicMock()
    mock_st.session_state = {
        "v3_target_name": "",
        "v3_cand_multiselect": [candidates[0].name],
        "v3_custom_competitors": [],
    }
    mock_st.text_input.return_value = ""
    mock_st.multiselect.return_value = [candidates[0].name]
    mock_st.columns.side_effect = lambda spec, **kwargs: (
        [MagicMock() for _ in range(spec)]
        if isinstance(spec, int)
        else [MagicMock() for _ in range(len(spec))]
    )

    disabled_flag: list[bool] = []

    def mock_button_blank(label: str, **kwargs: object) -> bool:
        if label == "Run Visibility Analysis":
            disabled_flag.append(bool(kwargs.get("disabled", False)))
        return False

    mock_st.button.side_effect = mock_button_blank

    with patch("ai_search_journey.visibility.ui.st", mock_st):
        render_visibility_tab(journey=journey)

        # Button must be disabled
        assert len(disabled_flag) == 1
        assert disabled_flag[0] is True

        # Validation box must explain the error actionably
        warning_calls = [
            str(call.args[0]) for call in mock_st.warning.call_args_list if call.args
        ]
        assert any("Target Brand Name is required" in w for w in warning_calls)

    # 2. More than 3 competitors
    mock_st_excess = MagicMock()
    excess_selected = [candidates[i].name for i in range(4)]
    mock_st_excess.session_state = {
        "v3_target_name": "Zen Haus Cafe",
        "v3_cand_multiselect": excess_selected,
        "v3_custom_competitors": [],
    }
    mock_st_excess.text_input.return_value = "Zen Haus Cafe"
    mock_st_excess.multiselect.return_value = excess_selected
    mock_st_excess.columns.side_effect = lambda spec, **kwargs: (
        [MagicMock() for _ in range(spec)]
        if isinstance(spec, int)
        else [MagicMock() for _ in range(len(spec))]
    )

    disabled_flag_excess: list[bool] = []

    def mock_button_excess(label: str, **kwargs: object) -> bool:
        if label == "Run Visibility Analysis":
            disabled_flag_excess.append(bool(kwargs.get("disabled", False)))
        return False

    mock_st_excess.button.side_effect = mock_button_excess

    with patch("ai_search_journey.visibility.ui.st", mock_st_excess):
        render_visibility_tab(journey=journey)

        assert len(disabled_flag_excess) == 1
        assert disabled_flag_excess[0] is True

        warning_calls_excess = [
            str(call.args[0]) for call in mock_st_excess.warning.call_args_list if call.args
        ]
        assert any("Maximum of 3 competitors allowed" in w for w in warning_calls_excess)


def test_target_competitor_collision_exact_vs_substring() -> None:
    """Verify collision check blocks exact normalized matches but allows substrings."""
    assert normalize_brand_name("  Zen   Haus  Cafe  ") == "zen haus cafe"
    cand_lookup = {
        "Zen Haus Cafe": _make_sample_candidate("p1", "Zen Haus Cafe"),
        "Zen Haus": _make_sample_candidate("p2", "Zen Haus"),
        "Haus Cafe": _make_sample_candidate("p3", "Haus Cafe"),
    }

    # Case 1: Exact normalized collision ("zen  haus   cafe" vs "Zen Haus Cafe")
    exact_profiles, _ = build_competitor_profiles(
        selected_candidate_names=["Zen Haus Cafe"],
        candidate_lookup=cand_lookup,
        custom_competitors=[],
    )
    _, errors_exact = validate_scan_inputs(
        target_name="  zen   haus   cafe  ",
        target_domain=None,
        target_aliases_raw="",
        target_place_id=None,
        competitor_profiles=exact_profiles,
        comp_build_errors=[],
    )
    assert len(errors_exact) == 1
    assert "cannot also be configured as a competitor" in errors_exact[0]

    # Case 2: Substring non-collision ("Zen Haus" competitor vs "Zen Haus Cafe" target)
    sub_profiles, _ = build_competitor_profiles(
        selected_candidate_names=["Zen Haus"],
        candidate_lookup=cand_lookup,
        custom_competitors=[],
    )
    _, errors_sub = validate_scan_inputs(
        target_name="Zen Haus Cafe",
        target_domain=None,
        target_aliases_raw="",
        target_place_id=None,
        competitor_profiles=sub_profiles,
        comp_build_errors=[],
    )
    assert errors_sub == []

    # Case 3: Another substring non-collision ("Haus Cafe" competitor vs "Zen Haus Cafe" target)
    sub2_profiles, _ = build_competitor_profiles(
        selected_candidate_names=["Haus Cafe"],
        candidate_lookup=cand_lookup,
        custom_competitors=[],
    )
    _, errors_sub2 = validate_scan_inputs(
        target_name="Zen Haus Cafe",
        target_domain=None,
        target_aliases_raw="",
        target_place_id=None,
        competitor_profiles=sub2_profiles,
        comp_build_errors=[],
    )
    assert errors_sub2 == []


def test_reset_v3_configuration_clears_only_v3_keys() -> None:
    """Verify reset_v3_session_state resets only V3 keys and leaves journey state intact."""
    from ai_search_journey.visibility.ui import reset_v3_session_state

    mock_st = MagicMock()
    mock_st.session_state = {
        "journey_result": "mock_journey_object",
        "v3_target_name": "Zen Haus Cafe",
        "v3_target_domain": "zenhaus.com",
        "v3_target_aliases": "Zen",
        "v3_target_place_id": "pid_123",
        "v3_cand_multiselect": ["Candidate 1", "Candidate 2"],
        "v3_custom_competitors": [{"name": "Custom 1"}],
        "v3_scan_result": "mock_scan_result",
        "v3_scan_error": "mock_err",
        "v3_active_target_id": "zen_haus_cafe",
    }

    with patch("ai_search_journey.visibility.ui.st", mock_st):
        reset_v3_session_state()

        # V1/V2 journey state must remain untouched
        assert mock_st.session_state["journey_result"] == "mock_journey_object"

        # V3 keys must be cleared
        assert mock_st.session_state["v3_target_name"] == ""
        assert mock_st.session_state["v3_target_domain"] == ""
        assert mock_st.session_state["v3_target_aliases"] == ""
        assert mock_st.session_state["v3_target_place_id"] == ""
        assert mock_st.session_state["v3_cand_multiselect"] == []
        assert mock_st.session_state["v3_custom_competitors"] == []
        assert mock_st.session_state["v3_scan_result"] is None
        assert mock_st.session_state["v3_scan_error"] is None
        assert mock_st.session_state["v3_active_target_id"] is None


