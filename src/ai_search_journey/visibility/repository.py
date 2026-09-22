"""Visibility scan repository interface and in-memory implementation (V3)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, Sequence, runtime_checkable

from ai_search_journey.visibility.metrics import (
    VisibilityTrendPoint,
    calculate_competitor_comparison,
    calculate_visibility_metrics,
    calculate_visibility_trend,
)
from ai_search_journey.visibility.models import (
    ScanStatus,
    VisibilityMetrics,
    VisibilityScanBundle,
)


class DuplicateScanError(Exception):
    """Raised when attempting to save a conflicting bundle under an existing scan_id."""


class InvalidRepositoryFilterError(ValueError):
    """Raised when query filters or pagination parameters are invalid."""


@runtime_checkable
class VisibilityRepository(Protocol):
    """Synchronous interface for persisting and querying visibility scan bundles."""

    def save_bundle(
        self,
        bundle: VisibilityScanBundle,
    ) -> None:
        """Persist a completed scan bundle idempotently."""
        ...

    def get_bundle(
        self,
        scan_id: str,
    ) -> VisibilityScanBundle | None:
        """Retrieve a scan bundle by scan_id, or None if not found."""
        ...

    def list_bundles(
        self,
        *,
        project_id: str | None = None,
        brand_id: str | None = None,
        prompt_id: str | None = None,
        batch_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int | None = None,
    ) -> list[VisibilityScanBundle]:
        """List scan bundles matching combined filters, ordered chronologically."""
        ...

    def get_metrics(
        self,
        brand_id: str,
        *,
        project_id: str | None = None,
        prompt_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> VisibilityMetrics:
        """Calculate historical visibility metrics for a brand across filtered bundles."""
        ...

    def get_competitor_comparison(
        self,
        brand_ids: Sequence[str],
        *,
        project_id: str | None = None,
        prompt_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[VisibilityMetrics]:
        """Calculate comparative visibility metrics for multiple brands across filtered bundles."""
        ...

    def get_trend(
        self,
        brand_id: str,
        *,
        project_id: str | None = None,
        prompt_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[VisibilityTrendPoint]:
        """Retrieve chronological visibility trend points for a brand across filtered bundles."""
        ...


class InMemoryVisibilityRepository:
    """Isolated, in-memory repository implementation for testing and local demonstration."""

    def __init__(self) -> None:
        self._bundles: dict[str, VisibilityScanBundle] = {}

    def save_bundle(self, bundle: VisibilityScanBundle) -> None:
        """Persist a completed scan bundle idempotently with defensive copying."""
        scan_id = bundle.scan.scan_id
        if not scan_id or not scan_id.strip():
            raise ValueError("scan_id cannot be blank")

        if bundle.scan.status != ScanStatus.COMPLETED:
            raise ValueError(
                f"Only COMPLETED scans can be saved, got {bundle.scan.status.value}"
            )

        # Idempotency check: same scan_id with exact same contents is a no-op
        if scan_id in self._bundles:
            existing = self._bundles[scan_id]
            if existing.model_dump() == bundle.model_dump():
                return
            raise DuplicateScanError(
                f"Conflicting scan bundle already exists for scan_id '{scan_id}'"
            )

        # Defensive deep copy on save
        self._bundles[scan_id] = bundle.model_copy(deep=True)

    def get_bundle(self, scan_id: str) -> VisibilityScanBundle | None:
        """Retrieve defensive copy of a scan bundle by scan_id."""
        if not scan_id or scan_id not in self._bundles:
            return None
        return self._bundles[scan_id].model_copy(deep=True)

    def list_bundles(
        self,
        *,
        project_id: str | None = None,
        brand_id: str | None = None,
        prompt_id: str | None = None,
        batch_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int | None = None,
    ) -> list[VisibilityScanBundle]:
        """List scan bundles matching combined filters, sorted by started_at and scan_id."""
        # Validate time filters
        if start_time is not None:
            if start_time.tzinfo is None or start_time.tzinfo.utcoffset(start_time) is None:
                raise InvalidRepositoryFilterError("start_time must be timezone-aware")
        if end_time is not None:
            if end_time.tzinfo is None or end_time.tzinfo.utcoffset(end_time) is None:
                raise InvalidRepositoryFilterError("end_time must be timezone-aware")
        if start_time is not None and end_time is not None and start_time > end_time:
            raise InvalidRepositoryFilterError(
                f"start_time ({start_time}) cannot be later than end_time ({end_time})"
            )

        # Validate limit
        if limit is not None and limit < 1:
            raise InvalidRepositoryFilterError(f"limit must be >= 1, got {limit}")

        matched: list[VisibilityScanBundle] = []
        for b in self._bundles.values():
            scan = b.scan

            # Project filter
            if project_id is not None and scan.project_id != project_id:
                continue

            # Brand filter: bundle must contain an observation for brand_id
            if brand_id is not None:
                if not any(obs.brand_id == brand_id for obs in b.brand_observations):
                    continue

            # Prompt filter
            if prompt_id is not None and scan.prompt_id != prompt_id:
                continue

            # Batch filter
            if batch_id is not None and scan.batch_id != batch_id:
                continue

            # Time filters (inclusive)
            if start_time is not None and scan.started_at < start_time:
                continue
            if end_time is not None and scan.started_at > end_time:
                continue

            matched.append(b)

        # Deterministic ordering: started_at ascending, scan_id ascending as tie-breaker
        matched.sort(key=lambda b: (b.scan.started_at, b.scan.scan_id))

        if limit is not None:
            matched = matched[:limit]

        # Return defensive deep copies
        return [b.model_copy(deep=True) for b in matched]

    def get_metrics(
        self,
        brand_id: str,
        *,
        project_id: str | None = None,
        prompt_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> VisibilityMetrics:
        """Calculate historical visibility metrics for a brand across filtered bundles."""
        bundles = self.list_bundles(
            project_id=project_id,
            brand_id=brand_id,
            prompt_id=prompt_id,
            start_time=start_time,
            end_time=end_time,
        )
        return calculate_visibility_metrics(bundles, brand_id)

    def get_competitor_comparison(
        self,
        brand_ids: Sequence[str],
        *,
        project_id: str | None = None,
        prompt_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[VisibilityMetrics]:
        """Calculate comparative visibility metrics across filtered bundles."""
        bundles = self.list_bundles(
            project_id=project_id,
            prompt_id=prompt_id,
            start_time=start_time,
            end_time=end_time,
        )
        return calculate_competitor_comparison(bundles, brand_ids)

    def get_trend(
        self,
        brand_id: str,
        *,
        project_id: str | None = None,
        prompt_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[VisibilityTrendPoint]:
        """Retrieve chronological visibility trend points across filtered bundles."""
        bundles = self.list_bundles(
            project_id=project_id,
            brand_id=brand_id,
            prompt_id=prompt_id,
            start_time=start_time,
            end_time=end_time,
        )
        return calculate_visibility_trend(bundles, brand_id)
