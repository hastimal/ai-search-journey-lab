"""Shared repository resolution and backend factory for AI Search Visibility (V3/V4)."""

from __future__ import annotations

import os
from typing import Any

from ai_search_journey.config import settings
from ai_search_journey.visibility.bigquery_repository import (
    BigQueryDependencyError,
    BigQueryVisibilityRepository,
    _get_bigquery_module,
)
from ai_search_journey.visibility.repository import VisibilityRepository
from ai_search_journey.visibility.sqlite_repository import SQLiteVisibilityRepository
from ai_search_journey.visibility.v4_analytics import (
    BigQueryVisibilityAnalyticsRepository,
    VisibilityAnalyticsRepository,
)


def get_configured_backend() -> str:
    """Return the normalized active visibility storage backend ('local' or 'bigquery')."""
    raw = (
        os.environ.get("AI_SEARCH_HISTORY_BACKEND")
        or settings.ai_search_history_backend
    )
    if not raw:
        has_bq = bool(
            settings.bigquery_project
            or os.environ.get("GOOGLE_CLOUD_PROJECT")
            or os.environ.get("BIGQUERY_PROJECT")
        )
        raw = "bigquery" if has_bq else "bigquery"  # Default to bigquery for backward compatibility
    backend = raw.strip().lower()
    if backend not in ("local", "bigquery"):
        raise ValueError(
            f"Invalid AI_SEARCH_HISTORY_BACKEND: '{raw}'. Must be 'local' or 'bigquery'."
        )
    return backend


def get_visibility_repository(*, db_path: str | None = None) -> VisibilityRepository:
    """Factory returning the appropriate VisibilityRepository (V3 write/query)."""
    backend = get_configured_backend()
    if backend == "local":
        path = (
            db_path
            or os.environ.get("LOCAL_HISTORY_DB_PATH")
            or settings.local_history_db_path
        )
        return SQLiteVisibilityRepository(db_path=path)

    if backend == "bigquery":
        project_id = (
            settings.bigquery_project
            or os.environ.get("GOOGLE_CLOUD_PROJECT")
            or os.environ.get("BIGQUERY_PROJECT")
        )
        if not project_id:
            raise RuntimeError("BigQuery repository unavailable: BIGQUERY_PROJECT not configured")
        if _get_bigquery_module() is None:
            raise BigQueryDependencyError(
                "Visibility history is configured for BigQuery, but google-cloud-bigquery "
                "is not installed. Install with: pip install -e '.[bigquery]' or switch "
                "AI_SEARCH_HISTORY_BACKEND=local."
            )
        return BigQueryVisibilityRepository(
            project_id=project_id,
            dataset_id=settings.bigquery_dataset,
            location=settings.bigquery_location,
        )

    raise ValueError(f"Unknown backend '{backend}'")


def get_visibility_analytics_repository(
    *,
    db_path: str | None = None,
    client: Any = None,
) -> VisibilityAnalyticsRepository:
    """Factory returning the appropriate VisibilityAnalyticsRepository (V4 read/analytics)."""
    backend = get_configured_backend()
    if backend == "local":
        path = (
            db_path
            or os.environ.get("LOCAL_HISTORY_DB_PATH")
            or settings.local_history_db_path
        )
        return SQLiteVisibilityRepository(db_path=path)

    if backend == "bigquery":
        project_id = (
            settings.bigquery_project
            or os.environ.get("GOOGLE_CLOUD_PROJECT")
            or os.environ.get("BIGQUERY_PROJECT")
        )
        if not project_id:
            raise RuntimeError("BigQuery repository unavailable: BIGQUERY_PROJECT not configured")
        if client is None and _get_bigquery_module() is None:
            raise BigQueryDependencyError(
                "Visibility history is configured for BigQuery, but google-cloud-bigquery "
                "is not installed. Install with: pip install -e '.[bigquery]' or switch "
                "AI_SEARCH_HISTORY_BACKEND=local."
            )
        return BigQueryVisibilityAnalyticsRepository(
            project_id=project_id,
            dataset_id=settings.bigquery_dataset,
            location=settings.bigquery_location,
            client=client,
        )

    raise ValueError(f"Unknown backend '{backend}'")
