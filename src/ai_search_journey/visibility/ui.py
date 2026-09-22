"""Streamlit UI component for AI Visibility [V3] (Milestone 6).

Provides an interactive dashboard to measure brand visibility, share of voice,
citations, and retrieval provenance across completed AI search journeys.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlparse

import streamlit as st

from ai_search_journey.config import Settings, settings
from ai_search_journey.models import Candidate, JourneyResult
from ai_search_journey.visibility.bigquery_schema import (
    validate_dataset_id,
    validate_location,
    validate_project_id,
)
from ai_search_journey.visibility.models import (
    BrandProfile,
    BrandRole,
    VisibilityScanBundle,
    normalize_domain,
)
from ai_search_journey.visibility.repository import (
    DuplicateScanError,
    InMemoryVisibilityRepository,
    VisibilityRepository,
)
from ai_search_journey.visibility.runner import (
    IncompleteJourneyError,
    InconsistentScanError,
    VisibilityRunnerError,
    VisibilityScanResult,
    run_visibility_scan,
)

# ======================================================================
# Helpers
# ======================================================================


def slugify_brand_name(name: str) -> str:
    """Derive a URL/database safe brand_id slug from a human-readable brand name."""
    clean = re.sub(r"[^a-zA-Z0-9_]+", "_", name.lower().strip())
    clean = clean.strip("_")
    return clean or "brand"


def extract_journey_candidates(journey: JourneyResult, limit: int = 10) -> list[Candidate]:
    """Dynamically extract up to limit unique candidates from a completed journey."""
    candidates: list[Candidate] = []
    seen_ids: set[str] = set()

    # Prioritize ranked candidates order if available
    if journey.ranked_candidates:
        for rc in journey.ranked_candidates:
            cand = rc.candidate
            if cand.place_id not in seen_ids:
                seen_ids.add(cand.place_id)
                candidates.append(cand)
            if len(candidates) >= limit:
                break

    # Supplement with unranked candidates if needed
    if len(candidates) < limit and journey.candidates:
        for cand in journey.candidates:
            if cand.place_id not in seen_ids:
                seen_ids.add(cand.place_id)
                candidates.append(cand)
            if len(candidates) >= limit:
                break

    return candidates


def derive_domain_from_url(url: Optional[str]) -> Optional[str]:
    """Extract clean domain from website URL."""
    if not url or not url.strip():
        return None
    try:
        parsed = urlparse(url.strip())
        netloc = parsed.netloc or parsed.path
        netloc = netloc.split(":")[0]  # Remove port if any
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return normalize_domain(netloc)
    except Exception:
        return None


def is_bigquery_available(cfg: Optional[Settings] = None) -> tuple[bool, str]:
    """Check if Google Cloud BigQuery is installed and completely configured."""
    import importlib.util

    try:
        spec = importlib.util.find_spec("google.cloud.bigquery")
        if spec is None:
            return False, "google-cloud-bigquery library is not installed."
    except (ImportError, ModuleNotFoundError, ValueError):
        return False, "google-cloud-bigquery library is not installed."

    active_settings = cfg if cfg is not None else settings
    project = active_settings.bigquery_project
    dataset = active_settings.bigquery_dataset
    location = active_settings.bigquery_location

    if not project or not project.strip():
        return False, "V3 BigQuery setting 'bigquery_project' is not configured."
    if not dataset or not dataset.strip():
        return False, "V3 BigQuery setting 'bigquery_dataset' is not configured."
    if not location or not location.strip():
        return False, "V3 BigQuery setting 'bigquery_location' is not configured."

    try:
        valid_project = validate_project_id(project)
        valid_dataset = validate_dataset_id(dataset)
        valid_location = validate_location(location)
    except Exception as ex:
        return False, f"V3 BigQuery configuration error: {ex}"

    return True, f"Configured for {valid_project}.{valid_dataset} ({valid_location})"


def init_v3_session_state() -> None:
    """Initialize V3-namespaced session state variables."""
    if "v3_repo" not in st.session_state:
        st.session_state["v3_repo"] = InMemoryVisibilityRepository()
    if "v3_scan_result" not in st.session_state:
        st.session_state["v3_scan_result"] = None
    if "v3_custom_competitors" not in st.session_state:
        st.session_state["v3_custom_competitors"] = []
    if "v3_scan_error" not in st.session_state:
        st.session_state["v3_scan_error"] = None


# ======================================================================
# Main UI Component
# ======================================================================


def render_visibility_tab(journey: Optional[JourneyResult]) -> None:
    """Render the AI Visibility [V3] Streamlit tab."""
    init_v3_session_state()

    # 1. Header Hierarchy
    st.subheader("AI Visibility [V3]")
    st.caption("Measure how configured brands appear in completed AI search journeys.")

    # 2. Source Journey Validation
    if (
        journey is None
        or journey.execution_trace is None
        or not journey.execution_trace.is_complete
    ):
        st.info("Run a Search to Decision journey first, then return here for visibility analysis.")
        return

    st.markdown("---")

    # 3. Dynamic Candidates and Brand Configuration
    candidates = extract_journey_candidates(journey, limit=10)
    candidate_lookup = {cand.name: cand for cand in candidates}

    col_target, col_competitors = st.columns([1, 1], gap="medium")

    # ---------------- Target Brand Configuration ----------------
    with col_target:
        st.markdown("### 🎯 Target Brand (Required)")
        st.caption("Configure the primary brand to analyze visibility and citations for.")

        target_name = st.text_input(
            "Brand Name *",
            value=st.session_state.get("v3_target_name", ""),
            placeholder="e.g. Austin Artisan Coffee",
            key="v3_target_name_input",
            help="Full business or brand name.",
        ).strip()

        target_domain_raw = st.text_input(
            "Brand Domain (optional)",
            value=st.session_state.get("v3_target_domain", ""),
            placeholder="e.g. austinartisan.com",
            key="v3_target_domain_input",
            help="Owned domain used to calculate owned citation rates.",
        ).strip()

        target_aliases_raw = st.text_input(
            "Brand Aliases (optional, comma-separated)",
            value=st.session_state.get("v3_target_aliases", ""),
            placeholder="e.g. Artisan Coffee, Austin Artisan",
            key="v3_target_aliases_input",
            help="Alternative names or abbreviations to match narrative mentions.",
        ).strip()

        target_place_id = st.text_input(
            "Google Places ID (optional)",
            value=st.session_state.get("v3_target_place_id", ""),
            placeholder="e.g. ChIJN1t_tDeuEmsRUsoyG83frY4",
            key="v3_target_place_id_input",
            help="Google Places ID for exact retrieval matching.",
        ).strip()

    # ---------------- Competitor Brands Configuration ----------------
    with col_competitors:
        st.markdown("### 🥊 Competitor Brands (0–3)")
        st.caption("Select up to 3 competitors from journey candidates or add custom competitors.")

        candidate_names = list(candidate_lookup.keys())
        selected_cand_names: list[str] = st.multiselect(
            "Select from Journey Candidates",
            options=candidate_names,
            default=[],
            max_selections=3,
            key="v3_cand_multiselect",
            help="Candidates retrieved during the search journey. Select 0 to 3.",
        )

        # Custom Competitor Management
        with st.expander("➕ Add Custom Competitor", expanded=False):
            st.caption("Add an off-journey competitor not found in retrieved candidates.")
            c_col1, c_col2 = st.columns(2)
            with c_col1:
                custom_name = st.text_input("Competitor Name", key="v3_custom_name").strip()
                custom_domain = st.text_input(
                    "Competitor Domain", key="v3_custom_domain", placeholder="e.g. comp.com"
                ).strip()
            with c_col2:
                custom_aliases = st.text_input(
                    "Aliases (comma-separated)", key="v3_custom_aliases"
                ).strip()
                custom_pid = st.text_input("Places ID", key="v3_custom_pid").strip()

            if st.button("Add to Competitor List", key="v3_btn_add_custom"):
                if not custom_name:
                    st.warning("Please enter a competitor name.")
                else:
                    custom_entry = {
                        "name": custom_name,
                        "domain": custom_domain or None,
                        "aliases": [a.strip() for a in custom_aliases.split(",") if a.strip()],
                        "place_id": custom_pid or None,
                    }
                    existing_names = [
                        c["name"].lower() for c in st.session_state["v3_custom_competitors"]
                    ]
                    if custom_name.lower() in existing_names:
                        st.warning(f"Competitor '{custom_name}' is already added.")
                    else:
                        st.session_state["v3_custom_competitors"].append(custom_entry)
                        st.success(f"Added '{custom_name}' to custom competitors.")

        # Show registered custom competitors
        custom_competitors: list[dict[str, Any]] = st.session_state["v3_custom_competitors"]
        active_custom_names: list[str] = []
        if custom_competitors:
            st.markdown("**Custom Competitors Registered:**")
            for idx, c in enumerate(custom_competitors):
                col_cname, col_cdel = st.columns([4, 1])
                with col_cname:
                    st.text(f"• {c['name']} ({c.get('domain') or 'no domain'})")
                with col_cdel:
                    if st.button("✕", key=f"v3_del_custom_{idx}", help=f"Remove {c['name']}"):
                        st.session_state["v3_custom_competitors"].pop(idx)
                        st.rerun()
                active_custom_names.append(c["name"])

    # Build active competitor profiles list (Candidate-derived + Custom)
    competitor_profiles: list[BrandProfile] = []
    comp_build_errors: list[str] = []

    # 1. From selected candidates
    for c_name in selected_cand_names:
        cand = candidate_lookup[c_name]
        c_slug = slugify_brand_name(c_name)
        c_domain = derive_domain_from_url(cand.website_url)
        p_ids = [cand.place_id] if cand.place_id else []
        try:
            competitor_profiles.append(
                BrandProfile(
                    brand_id=c_slug,
                    name=cand.name,
                    domain=c_domain,
                    aliases=[],
                    place_ids=p_ids,
                )
            )
        except Exception as ex:
            comp_build_errors.append(f"Invalid candidate competitor '{c_name}': {ex}")

    # 2. From custom competitors
    for c in custom_competitors:
        c_slug = slugify_brand_name(c["name"])
        try:
            competitor_profiles.append(
                BrandProfile(
                    brand_id=c_slug,
                    name=c["name"],
                    domain=c.get("domain") or None,
                    aliases=c.get("aliases") or [],
                    place_ids=[c["place_id"]] if c.get("place_id") else [],
                )
            )
        except Exception as ex:
            comp_build_errors.append(f"Invalid custom competitor '{c['name']}': {ex}")

    # Display configured competitors preview
    if competitor_profiles:
        st.markdown("**Configured Competitors:**")
        comp_summary = ", ".join([f"`{cp.name}`" for cp in competitor_profiles])
        st.markdown(comp_summary)

    # 4. Storage Selection & BigQuery Option
    st.markdown("---")
    bq_available, bq_msg = is_bigquery_available()

    col_storage, col_run = st.columns([1, 1], gap="medium")
    with col_storage:
        st.markdown("### 💾 Storage Backend")
        if bq_available:
            storage_choice = st.radio(
                "Visibility Repository",
                options=["Session only (In-Memory)", "BigQuery history"],
                index=0,
                key="v3_storage_choice",
                help="Store scans in memory for this session or persist to BigQuery.",
            )
            st.caption(f"✓ BigQuery available: {bq_msg}")
        else:
            storage_choice = st.radio(
                "Visibility Repository",
                options=["Session only (In-Memory)"],
                index=0,
                disabled=True,
                key="v3_storage_choice_disabled",
            )
            st.caption(
                f"💡 {bq_msg} To persist visibility history, configure complete V3 BigQuery "
                "settings (bigquery_project, bigquery_dataset, bigquery_location) in .env "
                "and install google-cloud-bigquery."
            )

    # 5. Execution Button & Action
    with col_run:
        st.markdown("### 🚀 Execute Analysis")
        st.caption("Extract visibility observations and calculate brand presence metrics.")
        run_scan_clicked = st.button(
            "Run Visibility Analysis",
            type="primary",
            use_container_width=True,
            key="v3_btn_run_scan",
        )

    # Handle Scan Execution
    if run_scan_clicked:
        st.session_state["v3_scan_error"] = None

        # Input Validations
        if not target_name:
            st.error("⚠️ Target Brand Name is required. Please specify a brand name.")
            return

        if len(competitor_profiles) > 3:
            st.error("⚠️ Maximum of 3 competitors allowed. Please remove excess competitors.")
            return

        target_slug = slugify_brand_name(target_name)
        comp_slugs = [cp.brand_id for cp in competitor_profiles]
        if target_slug in comp_slugs:
            st.error(
                f"⚠️ Target brand '{target_name}' cannot also be configured as a competitor."
            )
            return

        if len(comp_slugs) != len(set(comp_slugs)):
            st.error("⚠️ Duplicate competitor brands detected. Each competitor must be unique.")
            return

        if comp_build_errors:
            for err in comp_build_errors:
                st.error(f"⚠️ {err}")
            return

        # Build Target Brand Profile
        target_aliases = [a.strip() for a in target_aliases_raw.split(",") if a.strip()]
        target_pids = [target_place_id] if target_place_id else []
        try:
            target_profile = BrandProfile(
                brand_id=target_slug,
                name=target_name,
                domain=target_domain_raw or None,
                aliases=target_aliases,
                place_ids=target_pids,
            )
        except Exception as e:
            st.error(f"⚠️ Invalid target brand configuration: {e}")
            return

        # Select Repository
        repository: VisibilityRepository
        if bq_available and storage_choice == "BigQuery history":
            try:
                from ai_search_journey.visibility.bigquery_repository import (
                    BigQueryVisibilityRepository,
                )

                assert settings.bigquery_project is not None
                repository = BigQueryVisibilityRepository(
                    project_id=settings.bigquery_project,
                    dataset_id=settings.bigquery_dataset,
                    location=settings.bigquery_location,
                )
            except Exception as bq_err:
                st.error(f"Failed to initialize BigQuery repository: {bq_err}")
                return
        else:
            repository = st.session_state["v3_repo"]

        # Run Scan Deterministically
        try:
            with st.spinner("Extracting visibility observations..."):
                scan_result: VisibilityScanResult = run_visibility_scan(
                    journey=journey,
                    target_brand=target_profile,
                    competitor_brands=competitor_profiles,
                    repository=repository,
                )
                st.session_state["v3_scan_result"] = scan_result
                st.session_state["v3_active_target_id"] = target_profile.brand_id
                st.session_state["v3_active_repo"] = repository
                st.success(
                    f"✓ Visibility scan completed and saved (Scan ID: `{scan_result.scan_id}`)."
                )
        except DuplicateScanError as dup_err:
            st.warning(f"⚠️ Duplicate Scan: {dup_err}")
        except (IncompleteJourneyError, InconsistentScanError) as val_err:
            st.error(f"⚠️ Journey validation failed: {val_err}")
        except VisibilityRunnerError as run_err:
            st.error(f"⚠️ Visibility Runner error: {run_err}")
        except Exception as ex:
            st.error(f"⚠️ Unexpected error executing visibility scan: {ex}")

    # 6. Render Results if Scan Result is in Session State
    active_result = st.session_state.get("v3_scan_result")
    if active_result and isinstance(active_result, VisibilityScanResult):
        render_scan_results(
            scan_result=active_result,
            repository=st.session_state.get("v3_active_repo", st.session_state["v3_repo"]),
            target_brand_id=st.session_state.get(
                "v3_active_target_id", active_result.bundle.scan.brand_id
            ),
        )


# ======================================================================
# Results Visualizer
# ======================================================================


def render_scan_results(
    scan_result: VisibilityScanResult,
    repository: VisibilityRepository,
    target_brand_id: str,
) -> None:
    """Render KPI metrics, brand comparison table, and expandable technical details."""
    bundle: VisibilityScanBundle = scan_result.bundle

    st.markdown("---")
    st.markdown("### 📊 AI Search Visibility Metrics")

    # Fetch aggregated metrics for target brand
    try:
        metrics = repository.get_metrics(target_brand_id)
    except Exception:
        metrics = None

    # 1. KPI Metric Cards
    if metrics:
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
            st.metric("Total Scans", f"{metrics.total_scans}")
        with col2:
            st.metric("Narrative Mention", f"{metrics.mention_rate:.1%}")
        with col3:
            st.metric("Recommendation", f"{metrics.recommendation_rate:.1%}")
        with col4:
            st.metric("Owned Citation", f"{metrics.citation_rate:.1%}")
        with col5:
            st.metric("Share of Voice", f"{metrics.share_of_voice:.1%}")
        with col6:
            st.metric("Fan-out Coverage", f"{metrics.fanout_coverage:.1%}")

    # 2. Brand Comparison Table
    st.markdown("#### 🏆 Brand Comparison Table")
    st.caption(
        "Direct comparison across target and competitor brands for this scan. "
        "Note: A brand may be recommended without appearing in the narrative text."
    )

    brand_table_rows: list[dict[str, Any]] = []
    for bo in bundle.brand_observations:
        role_label = "Target" if bo.role == BrandRole.TARGET else "Competitor"
        ret_pos = f"#{bo.best_retrieval_position}" if bo.best_retrieval_position else "-"
        rec_pos = (
            f"#{bo.recommendation_position}" if bo.recommendation_position else "-"
        )
        brand_table_rows.append(
            {
                "Brand": bo.brand_id,
                "Role": role_label,
                "Narrative Mention": "✓ Yes" if bo.mentioned else "✗ No",
                "Mentions": bo.mention_count,
                "Recommended": "✓ Yes" if bo.recommended else "✗ No",
                "Cited": "✓ Yes" if bo.cited else "✗ No",
                "Retrieval Position": ret_pos,
                "Recommendation Position": rec_pos,
            }
        )

    if brand_table_rows:
        st.dataframe(brand_table_rows, use_container_width=True, hide_index=True)

    # 3. Technical Details (Expanders)
    with st.expander(f"🔗 Citations Discovered ({len(bundle.citations)})", expanded=False):
        if bundle.citations:
            citation_rows = [
                {
                    "URL": c.url,
                    "Domain": c.domain,
                    "Source Type": c.source_type,
                    "Matched Brands": ", ".join(c.matched_brand_ids) or "none",
                }
                for c in bundle.citations
            ]
            st.dataframe(citation_rows, use_container_width=True, hide_index=True)
        else:
            st.caption("No citations detected in grounding or final answer.")

    with st.expander(
        f"📡 Fan-Out Grounding Tasks ({len(bundle.fanout_observations)})", expanded=False
    ):
        if bundle.fanout_observations:
            fo_rows = [
                {
                    "Task ID": fo.task_id,
                    "Tool": fo.tool,
                    "Brand": fo.brand_id,
                    "Brand Found": "✓ Yes" if fo.brand_found else "✗ No",
                    "Position in Task": (
                        f"#{fo.position_in_task}" if fo.position_in_task else "-"
                    ),
                }
                for fo in bundle.fanout_observations
            ]
            st.dataframe(fo_rows, use_container_width=True, hide_index=True)
        else:
            st.caption("No fan-out observations recorded.")

    with st.expander("📦 Raw Visibility Scan Bundle (JSON)", expanded=False):
        bundle_dict = bundle.model_dump(mode="json")
        st.json(bundle_dict)
