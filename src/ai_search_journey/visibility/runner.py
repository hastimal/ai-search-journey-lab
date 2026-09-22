"""Deterministic visibility-scan runner.

Connects observation extraction and persistence (V3 Milestone 5).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence
from uuid import uuid4

from pydantic import BaseModel, Field

from ai_search_journey.models import JourneyResult, StepExecutionStatus
from ai_search_journey.visibility.extractor import extract_visibility_scan_bundle
from ai_search_journey.visibility.models import (
    BrandProfile,
    PromptDefinition,
    ScanStatus,
    VisibilityProject,
    VisibilityScan,
    VisibilityScanBundle,
)
from ai_search_journey.visibility.repository import VisibilityRepository

# ======================================================================
# Runner Exceptions
# ======================================================================


class VisibilityRunnerError(Exception):
    """Base exception for visibility scan runner errors."""


class IncompleteJourneyError(VisibilityRunnerError, ValueError):
    """Raised when the provided JourneyResult is incomplete or failed."""


class InconsistentScanError(VisibilityRunnerError, ValueError):
    """Raised when scan, project, prompt, or brand inputs are inconsistent."""


# ======================================================================
# Runner Output Model
# ======================================================================


class VisibilityScanResult(BaseModel):
    """Result returned by run_visibility_scan exposing the saved bundle and scan metadata."""

    bundle: VisibilityScanBundle
    saved: bool = Field(
        default=True, description="Whether the bundle was persisted to the repository"
    )

    @property
    def scan(self) -> VisibilityScan:
        """Convenience property accessing the underlying VisibilityScan."""
        return self.bundle.scan

    @property
    def scan_id(self) -> str:
        """Convenience property accessing the unique scan ID."""
        return self.bundle.scan.scan_id


# ======================================================================
# Validation Helpers
# ======================================================================


def _validate_journey_result(journey: JourneyResult) -> None:
    """Verify that a JourneyResult is completed and valid for visibility extraction."""
    if not isinstance(journey, JourneyResult):
        raise IncompleteJourneyError(
            f"Expected JourneyResult instance, got {type(journey).__name__}"
        )

    if not journey.question or not journey.question.strip():
        raise IncompleteJourneyError("JourneyResult must contain a non-blank question")

    if journey.execution_trace is not None:
        trace = journey.execution_trace
        if not trace.is_complete:
            raise IncompleteJourneyError(
                "JourneyResult execution trace indicates journey is not complete "
                "(is_complete=False)"
            )
        if trace.failed_step_key is not None:
            raise IncompleteJourneyError(
                f"JourneyResult execution trace recorded a failed step: '{trace.failed_step_key}'"
            )
        for step in trace.steps:
            if step.status == StepExecutionStatus.FAILED:
                raise IncompleteJourneyError(
                    f"JourneyResult step '{step.key}' has FAILED status: "
                    f"{step.error or 'unknown error'}"
                )


def _validate_brand_profiles(
    target_brand: BrandProfile,
    competitor_brands: Sequence[BrandProfile],
) -> None:
    """Validate target and competitor brand profiles for uniqueness and consistency."""
    if not isinstance(target_brand, BrandProfile):
        raise InconsistentScanError(
            f"target_brand must be BrandProfile, got {type(target_brand).__name__}"
        )

    comp_ids: set[str] = set()
    for comp in competitor_brands:
        if not isinstance(comp, BrandProfile):
            raise InconsistentScanError(
                f"Competitor must be BrandProfile, got {type(comp).__name__}"
            )
        if comp.brand_id == target_brand.brand_id:
            raise InconsistentScanError(
                f"Target brand '{target_brand.brand_id}' must not appear in competitor_brands"
            )
        if comp.brand_id in comp_ids:
            raise InconsistentScanError(
                f"Duplicate competitor brand ID detected: '{comp.brand_id}'"
            )
        comp_ids.add(comp.brand_id)


# ======================================================================
# Runner Orchestration
# ======================================================================


def run_visibility_scan(
    *,
    journey: JourneyResult,
    target_brand: BrandProfile,
    competitor_brands: Sequence[BrandProfile],
    repository: VisibilityRepository,
    scan: VisibilityScan | None = None,
    project: VisibilityProject | None = None,
    prompt: PromptDefinition | None = None,
    scan_id: str | None = None,
    batch_id: str = "batch_default",
    model_name: str = "gemini-2.5-flash",
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> VisibilityScanResult:
    """Orchestrate deterministic visibility extraction and repository persistence for a journey.

    1. Validates that the journey is complete and non-failed.
    2. Validates consistency between scan, project, prompt, target, and competitor brands.
    3. Resolves or completes the VisibilityScan record.
    4. Calls extract_visibility_scan_bundle() exactly once.
    5. Saves the resulting bundle through the provided VisibilityRepository exactly once.
    6. Returns a VisibilityScanResult exposing the persisted bundle.
    """
    # 1. Validate completed JourneyResult
    _validate_journey_result(journey)

    # 2. Validate brand profiles
    _validate_brand_profiles(target_brand, competitor_brands)

    # 3. Validate project consistency if provided
    if project is not None:
        if project.target_brand_id != target_brand.brand_id:
            raise InconsistentScanError(
                f"project.target_brand_id '{project.target_brand_id}' does not match "
                f"target_brand.brand_id '{target_brand.brand_id}'"
            )
        for comp in competitor_brands:
            if comp.brand_id not in project.competitor_brand_ids:
                raise InconsistentScanError(
                    f"Competitor brand '{comp.brand_id}' is not configured in project "
                    f"competitor_brand_ids {project.competitor_brand_ids}"
                )

    # 4. Validate prompt consistency if provided
    if prompt is not None:
        if not prompt.enabled:
            raise InconsistentScanError(f"Prompt '{prompt.prompt_id}' is disabled")

    # 5. Resolve and validate VisibilityScan
    now_utc = datetime.now(timezone.utc)
    if scan is not None:
        if scan.status == ScanStatus.FAILED:
            raise InconsistentScanError("Cannot run visibility scan with FAILED status")

        if scan.brand_id != target_brand.brand_id:
            raise InconsistentScanError(
                f"scan.brand_id '{scan.brand_id}' does not match "
                f"target_brand.brand_id '{target_brand.brand_id}'"
            )

        if project is not None and scan.project_id != project.project_id:
            raise InconsistentScanError(
                f"scan.project_id '{scan.project_id}' does not match "
                f"project.project_id '{project.project_id}'"
            )

        if prompt is not None and scan.prompt_id != prompt.prompt_id:
            raise InconsistentScanError(
                f"scan.prompt_id '{scan.prompt_id}' does not match "
                f"prompt.prompt_id '{prompt.prompt_id}'"
            )

        # Transition pending or running scan to completed
        if scan.status in (ScanStatus.PENDING, ScanStatus.RUNNING):
            c_at = completed_at or now_utc
            dur = (
                scan.duration_seconds
                if scan.duration_seconds is not None
                else max(0.0, (c_at - scan.started_at).total_seconds())
            )
            resolved_scan = scan.model_copy(
                update={
                    "status": ScanStatus.COMPLETED,
                    "completed_at": c_at,
                    "duration_seconds": dur,
                }
            )
        else:
            resolved_scan = scan
    else:
        # Construct new completed scan from project/prompt/journey metadata
        s_at = started_at or now_utc
        c_at = completed_at or s_at
        dur = max(0.0, (c_at - s_at).total_seconds())

        proj_id = project.project_id if project else "project_default"
        p_id = prompt.prompt_id if prompt else "prompt_default"
        p_text = prompt.prompt_text if prompt else journey.question
        loc = (
            prompt.reference_location
            if prompt and prompt.reference_location
            else (
                journey.intent.reference_location
                if journey.intent.reference_location
                else (journey.reference_location.name if journey.reference_location else None)
            )
        )

        resolved_scan = VisibilityScan(
            scan_id=scan_id or f"scan_{uuid4().hex[:12]}",
            batch_id=batch_id,
            project_id=proj_id,
            brand_id=target_brand.brand_id,
            brand_name_snapshot=target_brand.name,
            brand_domain_snapshot=target_brand.domain,
            prompt_id=p_id,
            prompt_text_snapshot=p_text,
            model_name=model_name,
            location_snapshot=loc,
            started_at=s_at,
            completed_at=c_at,
            status=ScanStatus.COMPLETED,
            duration_seconds=dur,
        )

    # 6. Call extract_visibility_scan_bundle exactly once
    bundle = extract_visibility_scan_bundle(
        scan=resolved_scan,
        journey=journey,
        target_brand=target_brand,
        competitor_brands=list(competitor_brands),
    )

    # 7. Save the resulting bundle through VisibilityRepository exactly once
    repository.save_bundle(bundle)

    # 8. Return typed result exposing the persisted bundle
    return VisibilityScanResult(bundle=bundle, saved=True)
