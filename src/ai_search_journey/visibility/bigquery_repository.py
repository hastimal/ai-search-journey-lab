"""BigQuery implementation of VisibilityRepository (V3 Milestone 4)."""

from __future__ import annotations

import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Sequence

from ai_search_journey.visibility.bigquery_schema import (
    LOCK_KEY_BUNDLE_WRITE,
    TABLE_BRAND_OBSERVATIONS,
    TABLE_BUNDLE_PAYLOADS,
    TABLE_CITATIONS,
    TABLE_FANOUT_OBSERVATIONS,
    TABLE_REPOSITORY_LOCKS,
    TABLE_VISIBILITY_SCANS,
    calculate_bundle_sha256,
    serialize_bundle_canonically,
    validate_dataset_id,
    validate_location,
    validate_project_id,
)
from ai_search_journey.visibility.metrics import VisibilityTrendPoint
from ai_search_journey.visibility.models import (
    ScanStatus,
    VisibilityMetrics,
    VisibilityScanBundle,
)
from ai_search_journey.visibility.repository import (
    DuplicateScanError,
    InvalidRepositoryFilterError,
)

# ======================================================================
# Exceptions
# ======================================================================


class BigQueryDependencyError(ImportError):
    """Raised when BigQuery optional dependencies are not installed."""


class BigQueryWriteError(Exception):
    """Raised when writing to BigQuery fails."""


# ======================================================================
# Lazy BigQuery Helpers and Mock Fallbacks
# ======================================================================


def _get_bigquery_module() -> Any:
    try:
        from google.cloud import bigquery

        return bigquery
    except ImportError:
        return None


class MockScalarQueryParameter:
    """Mock query parameter when google-cloud-bigquery is not installed."""

    def __init__(self, name: str, type_: str, value: Any) -> None:
        self.name = name
        self.type_ = type_
        self.value = value

    def __repr__(self) -> str:
        return f"ScalarQueryParameter({self.name!r}, {self.type_!r}, {self.value!r})"


class MockArrayQueryParameter:
    """Mock array query parameter when google-cloud-bigquery is not installed."""

    def __init__(self, name: str, array_type: str, values: list[Any]) -> None:
        self.name = name
        self.array_type = array_type
        self.values = values

    def __repr__(self) -> str:
        return f"ArrayQueryParameter({self.name!r}, {self.array_type!r}, {self.values!r})"


class MockQueryJobConfig:
    """Mock query job config when google-cloud-bigquery is not installed."""

    def __init__(self, query_parameters: list[Any]) -> None:
        self.query_parameters = query_parameters


def _param(name: str, type_: str, value: Any) -> Any:
    bq = _get_bigquery_module()
    if bq is not None:
        return bq.ScalarQueryParameter(name, type_, value)
    return MockScalarQueryParameter(name, type_, value)


def _array_param(name: str, elem_type: str, values: list[Any]) -> Any:
    bq = _get_bigquery_module()
    if bq is not None:
        return bq.ArrayQueryParameter(name, elem_type, values)
    return MockArrayQueryParameter(name, elem_type, values)


def _job_config(params: list[Any]) -> Any:
    bq = _get_bigquery_module()
    if bq is not None:
        return bq.QueryJobConfig(query_parameters=params)
    return MockQueryJobConfig(query_parameters=params)


def _get_val(row: Any, key: str, index: int | None = None) -> Any:
    """Extract column value from dict, namedtuple, or SDK Row object."""
    if isinstance(row, dict):
        return row.get(key)
    if hasattr(row, key):
        return getattr(row, key)
    if hasattr(row, "get"):
        return row.get(key)
    if index is not None:
        try:
            return row[index]
        except (IndexError, TypeError):
            pass
    try:
        return row[key]
    except (KeyError, TypeError):
        return None


# ======================================================================
# BigQuery Visibility Repository Implementation
# ======================================================================


class BigQueryVisibilityRepository:
    """BigQuery-backed persistence implementation satisfying VisibilityRepository."""

    def __init__(
        self,
        project_id: str,
        dataset_id: str = "ai_search_journey_v3",
        location: str = "US",
        *,
        client: Any = None,
        default_history_days: int = 30,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.project_id = validate_project_id(project_id)
        self.dataset_id = validate_dataset_id(dataset_id)
        self.location = validate_location(location)

        if default_history_days < 1:
            raise ValueError(f"default_history_days must be >= 1, got {default_history_days}")
        self.default_history_days = default_history_days
        self.clock = clock or (lambda: datetime.now(timezone.utc))

        if client is not None:
            self._client = client
        else:
            bq = _get_bigquery_module()
            if bq is None:
                raise BigQueryDependencyError(
                    "google-cloud-bigquery is required for BigQueryVisibilityRepository. "
                    'Install with: pip install -e ".[bigquery]"'
                )
            self._client = bq.Client(project=self.project_id, location=self.location)

    def _execute_query(self, sql: str, params: list[Any]) -> list[Any]:
        """Execute parameterized query using client and return rows as list."""
        config = _job_config(params)
        job = self._client.query(sql, job_config=config)
        if hasattr(job, "result"):
            res = job.result()
            return list(res)
        return list(job)

    def _validate_effective_bounds(
        self,
        start_time: datetime | None,
        end_time: datetime | None,
    ) -> tuple[datetime, datetime]:
        """Resolve bounded history and validate timezone-awareness and range."""
        if start_time is not None:
            if start_time.tzinfo is None or start_time.tzinfo.utcoffset(start_time) is None:
                raise InvalidRepositoryFilterError("start_time must be timezone-aware")

        if end_time is not None:
            if end_time.tzinfo is None or end_time.tzinfo.utcoffset(end_time) is None:
                raise InvalidRepositoryFilterError("end_time must be timezone-aware")

        eff_end = end_time if end_time is not None else self.clock()
        eff_start = (
            start_time
            if start_time is not None
            else eff_end - timedelta(days=self.default_history_days)
        )

        if eff_start.tzinfo is None or eff_start.tzinfo.utcoffset(eff_start) is None:
            raise InvalidRepositoryFilterError("Resolved start_time must be timezone-aware")
        if eff_end.tzinfo is None or eff_end.tzinfo.utcoffset(eff_end) is None:
            raise InvalidRepositoryFilterError("Resolved end_time must be timezone-aware")

        if eff_start > eff_end:
            raise InvalidRepositoryFilterError(
                f"start_time ({eff_start}) cannot be later than end_time ({eff_end})"
            )

        return eff_start, eff_end

    def save_bundle(self, bundle: VisibilityScanBundle) -> None:
        """Persist a completed scan bundle atomically using a multi-statement transaction."""
        scan = bundle.scan
        scan_id = scan.scan_id
        if not scan_id or not scan_id.strip():
            raise ValueError("scan_id cannot be blank")

        if scan.status != ScanStatus.COMPLETED:
            raise ValueError(f"Only COMPLETED scans can be saved, got {scan.status.value}")

        canonical_json = serialize_bundle_canonically(bundle)
        payload_sha256 = calculate_bundle_sha256(bundle)
        created_at = self.clock()

        p_id = self.project_id
        d_id = self.dataset_id

        # Base parameters
        params: list[Any] = [
            _param("lock_key", "STRING", LOCK_KEY_BUNDLE_WRITE),
            _param("scan_id", "STRING", scan.scan_id.strip()),
            _param("payload_sha256", "STRING", payload_sha256),
            _param("bundle_json", "STRING", canonical_json),
            _param("created_at", "TIMESTAMP", created_at),
            _param("started_at", "TIMESTAMP", scan.started_at),
            _param("batch_id", "STRING", scan.batch_id),
            _param("project_id", "STRING", scan.project_id),
            _param("brand_id", "STRING", scan.brand_id),
            _param("brand_name_snapshot", "STRING", scan.brand_name_snapshot),
            _param("brand_domain_snapshot", "STRING", scan.brand_domain_snapshot),
            _param("prompt_id", "STRING", scan.prompt_id),
            _param("prompt_text_snapshot", "STRING", scan.prompt_text_snapshot),
            _param("model_name", "STRING", scan.model_name),
            _param("location_snapshot", "STRING", scan.location_snapshot),
            _param("completed_at", "TIMESTAMP", scan.completed_at),
            _param("status", "STRING", scan.status.value),
            _param("duration_seconds", "FLOAT64", scan.duration_seconds),
            _param("error_code", "STRING", scan.error_code),
            _param("error_message", "STRING", scan.error_message),
        ]

        # Scan insert
        scan_insert_sql = f"""INSERT INTO `{p_id}.{d_id}.{TABLE_VISIBILITY_SCANS}` (
    scan_id, batch_id, project_id, brand_id, brand_name_snapshot,
    brand_domain_snapshot, prompt_id, prompt_text_snapshot, model_name,
    location_snapshot, started_at, completed_at, status, duration_seconds,
    error_code, error_message
  ) VALUES (
    @scan_id, @batch_id, @project_id, @brand_id, @brand_name_snapshot,
    @brand_domain_snapshot, @prompt_id, @prompt_text_snapshot, @model_name,
    @location_snapshot, @started_at, @completed_at, @status, @duration_seconds,
    @error_code, @error_message
  );"""

        # Brand observations inserts
        bo_sqls: list[str] = []
        for i, bo in enumerate(bundle.brand_observations):
            bo_prefix = f"bo_{i}"
            bo_sqls.append(
                f"""INSERT INTO `{p_id}.{d_id}.{TABLE_BRAND_OBSERVATIONS}` (
    scan_id, project_id, prompt_id, started_at, brand_id, role,
    mentioned, mention_count, first_mention_position, retrieved,
    best_retrieval_position, recommended, recommendation_position, cited,
    citation_urls, citation_domains
  ) VALUES (
    @scan_id, @project_id, @prompt_id, @started_at, @{bo_prefix}_brand_id, @{bo_prefix}_role,
    @{bo_prefix}_mentioned, @{bo_prefix}_mention_count, @{bo_prefix}_first_mention_position,
    @{bo_prefix}_retrieved, @{bo_prefix}_best_retrieval_position, @{bo_prefix}_recommended,
    @{bo_prefix}_recommendation_position, @{bo_prefix}_cited, @{bo_prefix}_citation_urls,
    @{bo_prefix}_citation_domains
  );"""
            )
            params.extend([
                _param(f"{bo_prefix}_brand_id", "STRING", bo.brand_id),
                _param(f"{bo_prefix}_role", "STRING", bo.role.value),
                _param(f"{bo_prefix}_mentioned", "BOOL", bo.mentioned),
                _param(f"{bo_prefix}_mention_count", "INT64", bo.mention_count),
                _param(f"{bo_prefix}_first_mention_position", "INT64", bo.first_mention_position),
                _param(f"{bo_prefix}_retrieved", "BOOL", bo.retrieved),
                _param(f"{bo_prefix}_best_retrieval_position", "INT64", bo.best_retrieval_position),
                _param(f"{bo_prefix}_recommended", "BOOL", bo.recommended),
                _param(f"{bo_prefix}_recommendation_position", "INT64", bo.recommendation_position),
                _param(f"{bo_prefix}_cited", "BOOL", bo.cited),
                _array_param(f"{bo_prefix}_citation_urls", "STRING", bo.citation_urls),
                _array_param(f"{bo_prefix}_citation_domains", "STRING", bo.citation_domains),
            ])

        # Fanout observations inserts
        fo_sqls: list[str] = []
        for j, fo in enumerate(bundle.fanout_observations):
            fo_prefix = f"fo_{j}"
            fo_sqls.append(
                f"""INSERT INTO `{p_id}.{d_id}.{TABLE_FANOUT_OBSERVATIONS}` (
    scan_id, project_id, prompt_id, started_at, task_id,
    query_text, tool, brand_id, brand_found, position_in_task
  ) VALUES (
    @scan_id, @project_id, @prompt_id, @started_at, @{fo_prefix}_task_id,
    @{fo_prefix}_query_text, @{fo_prefix}_tool, @{fo_prefix}_brand_id,
    @{fo_prefix}_brand_found, @{fo_prefix}_position_in_task
  );"""
            )
            params.extend([
                _param(f"{fo_prefix}_task_id", "STRING", fo.task_id),
                _param(f"{fo_prefix}_query_text", "STRING", fo.query_text),
                _param(f"{fo_prefix}_tool", "STRING", fo.tool),
                _param(f"{fo_prefix}_brand_id", "STRING", fo.brand_id),
                _param(f"{fo_prefix}_brand_found", "BOOL", fo.brand_found),
                _param(f"{fo_prefix}_position_in_task", "INT64", fo.position_in_task),
            ])

        # Citations inserts
        cit_sqls: list[str] = []
        for k, cit in enumerate(bundle.citations):
            cit_prefix = f"cit_{k}"
            cit_sqls.append(
                f"""INSERT INTO `{p_id}.{d_id}.{TABLE_CITATIONS}` (
    scan_id, project_id, prompt_id, started_at, url,
    domain, source_type, matched_brand_ids
  ) VALUES (
    @scan_id, @project_id, @prompt_id, @started_at, @{cit_prefix}_url,
    @{cit_prefix}_domain, @{cit_prefix}_source_type, @{cit_prefix}_matched_brand_ids
  );"""
            )
            params.extend([
                _param(f"{cit_prefix}_url", "STRING", cit.url),
                _param(f"{cit_prefix}_domain", "STRING", cit.domain),
                _param(f"{cit_prefix}_source_type", "STRING", cit.source_type),
                _array_param(f"{cit_prefix}_matched_brand_ids", "STRING", cit.matched_brand_ids),
            ])

        brand_inserts = "\n  ".join(bo_sqls)
        fanout_inserts = "\n  ".join(fo_sqls)
        citation_inserts = "\n  ".join(cit_sqls)

        tx_sql = f"""DECLARE existing_hash STRING;

BEGIN TRANSACTION;

-- a. Serialization gate: update repository_locks
UPDATE `{p_id}.{d_id}.{TABLE_REPOSITORY_LOCKS}`
SET lock_version = lock_version + 1
WHERE lock_key = @lock_key;

IF @@row_count = 0 THEN
  ROLLBACK TRANSACTION;
  RAISE USING MESSAGE =
    'Repository lock row missing. Run setup_bigquery_v3.py --apply to initialize repository_locks.';
END IF;

-- b. Read/check existing bundle_payloads row for scan_id
SET existing_hash = (
  SELECT payload_sha256
  FROM `{p_id}.{d_id}.{TABLE_BUNDLE_PAYLOADS}`
  WHERE scan_id = @scan_id
  LIMIT 1
);

-- c & d. Check hash match or mismatch
IF existing_hash IS NOT NULL THEN
  IF existing_hash = @payload_sha256 THEN
    COMMIT TRANSACTION;
  ELSE
    ROLLBACK TRANSACTION;
    RAISE USING MESSAGE =
      'DUPLICATE_SCAN_ERROR: Conflicting scan bundle already exists for scan_id: ' || @scan_id;
  END IF;
ELSE
  -- e. Remove legacy orphan fact rows in partition, insert facts, insert payload marker
  DELETE FROM `{p_id}.{d_id}.{TABLE_VISIBILITY_SCANS}`
  WHERE DATE(started_at) = DATE(@started_at) AND scan_id = @scan_id;

  DELETE FROM `{p_id}.{d_id}.{TABLE_BRAND_OBSERVATIONS}`
  WHERE DATE(started_at) = DATE(@started_at) AND scan_id = @scan_id;

  DELETE FROM `{p_id}.{d_id}.{TABLE_FANOUT_OBSERVATIONS}`
  WHERE DATE(started_at) = DATE(@started_at) AND scan_id = @scan_id;

  DELETE FROM `{p_id}.{d_id}.{TABLE_CITATIONS}`
  WHERE DATE(started_at) = DATE(@started_at) AND scan_id = @scan_id;

  {scan_insert_sql}
  {brand_inserts}
  {fanout_inserts}
  {citation_inserts}

  INSERT INTO `{p_id}.{d_id}.{TABLE_BUNDLE_PAYLOADS}` (
    scan_id, payload_sha256, bundle_json, created_at
  ) VALUES (
    @scan_id, @payload_sha256, @bundle_json, @created_at
  );

  COMMIT TRANSACTION;
END IF;"""

        # Updated retry logic with bounded exponential backoff and jitter
        max_attempts = 4  # total attempts including the initial try
        base_delay = 0.7  # seconds
        jitter_factor = 0.3  # up to 30% jitter

        for attempt in range(max_attempts):
            try:
                self._execute_query(tx_sql, params)
                return
            except DuplicateScanError:
                # Duplicate scans are not retryable
                raise
            except Exception as exc:
                msg = str(exc).lower()
                # Duplicate scan detection
                if "duplicate_scan_error" in msg or "duplicate scan" in msg:
                    raise DuplicateScanError(
                        f"Conflicting scan bundle already exists for scan_id: {scan_id}"
                    ) from exc
                # Concurrency retry detection
                if "repository_locks" in msg and "concurrent update" in msg:
                    if attempt < max_attempts - 1:
                        delay = base_delay * (2 ** attempt)
                        jitter = random.uniform(0, jitter_factor * delay)
                        time.sleep(delay + jitter)
                        continue
                    # Exhausted retries – raise user‑friendly error
                    raise BigQueryWriteError(
                        "Another visibility write is still in progress. "
                        "Please try again in a moment."
                    ) from exc
                # Any other error is non‑retryable
                raise BigQueryWriteError(
                    f"Failed to save bundle '{scan_id}' to BigQuery: {exc}"
                ) from exc

    def get_bundle(self, scan_id: str) -> VisibilityScanBundle | None:
        """Retrieve bundle by scan_id from bundle_payloads only."""
        if not scan_id or not scan_id.strip():
            raise ValueError("scan_id cannot be blank")

        sql = f"""SELECT bundle_json
FROM `{self.project_id}.{self.dataset_id}.{TABLE_BUNDLE_PAYLOADS}`
WHERE scan_id = @scan_id"""
        rows = self._execute_query(sql, [_param("scan_id", "STRING", scan_id.strip())])
        if not rows:
            return None

        raw_json = _get_val(rows[0], "bundle_json", 0)
        return VisibilityScanBundle.model_validate_json(raw_json)

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
        """List bundles matching filters, sorted chronologically with tie-breaker."""
        if limit is not None and limit < 1:
            raise InvalidRepositoryFilterError(f"limit must be >= 1, got {limit}")

        eff_start, eff_end = self._validate_effective_bounds(start_time, end_time)

        # 1. Query scan_ids from partitioned visibility_scans
        conditions = [
            "started_at >= @start_time",
            "started_at <= @end_time",
        ]
        params: list[Any] = [
            _param("start_time", "TIMESTAMP", eff_start),
            _param("end_time", "TIMESTAMP", eff_end),
        ]

        if project_id is not None:
            conditions.append("project_id = @project_id")
            params.append(_param("project_id", "STRING", project_id))

        if prompt_id is not None:
            conditions.append("prompt_id = @prompt_id")
            params.append(_param("prompt_id", "STRING", prompt_id))

        if batch_id is not None:
            conditions.append("batch_id = @batch_id")
            params.append(_param("batch_id", "STRING", batch_id))

        if brand_id is not None:
            conditions.append(
                f"""scan_id IN (
  SELECT DISTINCT scan_id FROM `{self.project_id}.{self.dataset_id}.{TABLE_BRAND_OBSERVATIONS}`
  WHERE started_at >= @start_time AND started_at <= @end_time
    AND brand_id = @brand_id
)"""
            )
            params.append(_param("brand_id", "STRING", brand_id))

        where_clause = " AND ".join(conditions)
        sql = f"""SELECT scan_id
FROM `{self.project_id}.{self.dataset_id}.{TABLE_VISIBILITY_SCANS}`
WHERE {where_clause}
ORDER BY started_at ASC, scan_id ASC"""

        if limit is not None:
            sql += " LIMIT @limit"
            params.append(_param("limit", "INT64", limit))

        scan_rows = self._execute_query(sql, params)
        if not scan_rows:
            return []

        ordered_scan_ids = [_get_val(r, "scan_id", 0) for r in scan_rows]

        # 2. Batch fetch bundles from bundle_payloads via UNNEST
        payload_sql = f"""SELECT scan_id, bundle_json
FROM `{self.project_id}.{self.dataset_id}.{TABLE_BUNDLE_PAYLOADS}`
WHERE scan_id IN UNNEST(@scan_ids)"""
        payload_params = [_array_param("scan_ids", "STRING", ordered_scan_ids)]
        payload_rows = self._execute_query(payload_sql, payload_params)

        payload_map: dict[str, str] = {}
        for r in payload_rows:
            sid = _get_val(r, "scan_id", 0)
            b_json = _get_val(r, "bundle_json", 1)
            payload_map[sid] = b_json

        return [
            VisibilityScanBundle.model_validate_json(payload_map[sid])
            for sid in ordered_scan_ids
            if sid in payload_map
        ]

    def get_competitor_comparison(
        self,
        brand_ids: Sequence[str],
        *,
        project_id: str | None = None,
        prompt_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[VisibilityMetrics]:
        """Compute comparative visibility metrics for multiple brands in one set-based query."""
        if not brand_ids:
            return []

        clean_brand_ids: list[str] = []
        for bid in brand_ids:
            if not bid or not bid.strip():
                raise ValueError("brand_id in brand_ids cannot be blank")
            clean_brand_ids.append(bid.strip())

        eff_start, eff_end = self._validate_effective_bounds(start_time, end_time)

        sql = f"""WITH requested_brands AS (
  SELECT brand_id, brand_order
  FROM UNNEST(@brand_ids) WITH OFFSET AS brand_order
),
tracked_brand_scans AS (
  SELECT DISTINCT rb.brand_id, bo.scan_id
  FROM `{self.project_id}.{self.dataset_id}.{TABLE_BRAND_OBSERVATIONS}` bo
  JOIN requested_brands rb ON bo.brand_id = rb.brand_id
  WHERE bo.started_at >= @start_time AND bo.started_at <= @end_time
    AND (@project_id IS NULL OR bo.project_id = @project_id)
    AND (@prompt_id IS NULL OR bo.prompt_id = @prompt_id)
),
brand_scan_stats AS (
  SELECT
    tbs.brand_id,
    COUNT(DISTINCT tbs.scan_id) AS total_scans,
    COUNTIF(bo.mentioned = TRUE) AS mentioned_scans,
    COUNTIF(bo.recommended = TRUE) AS recommended_scans,
    COUNTIF(bo.cited = TRUE) AS cited_scans,
    AVG(CASE WHEN bo.recommended = TRUE THEN bo.recommendation_position END) AS avg_rec_pos,
    COALESCE(SUM(bo.mention_count), 0) AS selected_mentions
  FROM tracked_brand_scans tbs
  JOIN `{self.project_id}.{self.dataset_id}.{TABLE_BRAND_OBSERVATIONS}` bo
    ON tbs.scan_id = bo.scan_id AND tbs.brand_id = bo.brand_id
  WHERE bo.started_at >= @start_time AND bo.started_at <= @end_time
  GROUP BY tbs.brand_id
),
market_stats_per_brand AS (
  SELECT
    tbs.brand_id,
    COALESCE(SUM(all_bo.mention_count), 0) AS total_market_mentions
  FROM tracked_brand_scans tbs
  JOIN `{self.project_id}.{self.dataset_id}.{TABLE_BRAND_OBSERVATIONS}` all_bo
    ON tbs.scan_id = all_bo.scan_id
  WHERE all_bo.started_at >= @start_time AND all_bo.started_at <= @end_time
  GROUP BY tbs.brand_id
),
fanout_stats_per_brand AS (
  SELECT
    tbs.brand_id,
    COUNT(*) AS total_fanouts,
    COUNTIF(fo.brand_found = TRUE) AS found_fanouts
  FROM tracked_brand_scans tbs
  JOIN `{self.project_id}.{self.dataset_id}.{TABLE_FANOUT_OBSERVATIONS}` fo
    ON tbs.scan_id = fo.scan_id AND tbs.brand_id = fo.brand_id
  WHERE fo.started_at >= @start_time AND fo.started_at <= @end_time
  GROUP BY tbs.brand_id
)
SELECT
  rb.brand_id,
  COALESCE(s.total_scans, 0) AS total_scans,
  CASE WHEN s.total_scans > 0
    THEN s.mentioned_scans / s.total_scans
    ELSE 0.0 END AS mention_rate,
  CASE WHEN s.total_scans > 0
    THEN s.recommended_scans / s.total_scans
    ELSE 0.0 END AS recommendation_rate,
  CASE WHEN s.total_scans > 0
    THEN s.cited_scans / s.total_scans
    ELSE 0.0 END AS citation_rate,
  s.avg_rec_pos AS average_recommendation_position,
  CASE WHEN m.total_market_mentions > 0
    THEN s.selected_mentions / m.total_market_mentions
    ELSE 0.0 END AS share_of_voice,
  CASE WHEN f.total_fanouts > 0
    THEN f.found_fanouts / f.total_fanouts
    ELSE 0.0 END AS fanout_coverage
FROM requested_brands rb
LEFT JOIN brand_scan_stats s ON rb.brand_id = s.brand_id
LEFT JOIN market_stats_per_brand m ON rb.brand_id = m.brand_id
LEFT JOIN fanout_stats_per_brand f ON rb.brand_id = f.brand_id
ORDER BY rb.brand_order ASC"""

        params = [
            _array_param("brand_ids", "STRING", clean_brand_ids),
            _param("start_time", "TIMESTAMP", eff_start),
            _param("end_time", "TIMESTAMP", eff_end),
            _param("project_id", "STRING", project_id),
            _param("prompt_id", "STRING", prompt_id),
        ]

        rows = self._execute_query(sql, params)
        results: list[VisibilityMetrics] = []
        for r in rows:
            bid = _get_val(r, "brand_id", 0)
            tscans = int(_get_val(r, "total_scans", 1) or 0)
            mrate = float(_get_val(r, "mention_rate", 2) or 0.0)
            rrate = float(_get_val(r, "recommendation_rate", 3) or 0.0)
            crate = float(_get_val(r, "citation_rate", 4) or 0.0)
            raw_pos = _get_val(r, "average_recommendation_position", 5)
            avg_pos = float(raw_pos) if raw_pos is not None else None
            sov = float(_get_val(r, "share_of_voice", 6) or 0.0)
            fcov = float(_get_val(r, "fanout_coverage", 7) or 0.0)

            results.append(
                VisibilityMetrics(
                    brand_id=bid,
                    total_scans=tscans,
                    mention_rate=mrate,
                    recommendation_rate=rrate,
                    citation_rate=crate,
                    average_recommendation_position=avg_pos,
                    share_of_voice=sov,
                    fanout_coverage=fcov,
                )
            )
        return results

    def get_metrics(
        self,
        brand_id: str,
        *,
        project_id: str | None = None,
        prompt_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> VisibilityMetrics:
        """Calculate historical visibility metrics for a brand across filtered scans."""
        if not brand_id or not brand_id.strip():
            raise ValueError("brand_id cannot be blank")

        results = self.get_competitor_comparison(
            [brand_id.strip()],
            project_id=project_id,
            prompt_id=prompt_id,
            start_time=start_time,
            end_time=end_time,
        )
        return results[0]

    def get_trend(
        self,
        brand_id: str,
        *,
        project_id: str | None = None,
        prompt_id: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[VisibilityTrendPoint]:
        """Retrieve chronological visibility trend points for a brand across filtered scans."""
        if not brand_id or not brand_id.strip():
            raise ValueError("brand_id cannot be blank")

        eff_start, eff_end = self._validate_effective_bounds(start_time, end_time)

        sql = f"""SELECT
  scan_id,
  started_at,
  mentioned,
  recommended,
  recommendation_position,
  cited,
  mention_count
FROM `{self.project_id}.{self.dataset_id}.{TABLE_BRAND_OBSERVATIONS}`
WHERE started_at >= @start_time AND started_at <= @end_time
  AND brand_id = @brand_id
  AND (@project_id IS NULL OR project_id = @project_id)
  AND (@prompt_id IS NULL OR prompt_id = @prompt_id)
ORDER BY started_at ASC, scan_id ASC"""

        params = [
            _param("brand_id", "STRING", brand_id.strip()),
            _param("start_time", "TIMESTAMP", eff_start),
            _param("end_time", "TIMESTAMP", eff_end),
            _param("project_id", "STRING", project_id),
            _param("prompt_id", "STRING", prompt_id),
        ]

        rows = self._execute_query(sql, params)
        points: list[VisibilityTrendPoint] = []
        for r in rows:
            sid = _get_val(r, "scan_id", 0)
            st = _get_val(r, "started_at", 1)
            m = bool(_get_val(r, "mentioned", 2))
            rec = bool(_get_val(r, "recommended", 3))
            rec_pos_val = _get_val(r, "recommendation_position", 4)
            rec_pos = int(rec_pos_val) if rec_pos_val is not None else None
            c = bool(_get_val(r, "cited", 5))
            cnt = int(_get_val(r, "mention_count", 6) or 0)

            points.append(
                VisibilityTrendPoint(
                    scan_id=sid,
                    started_at=st,
                    mentioned=m,
                    recommended=rec,
                    recommendation_position=rec_pos,
                    cited=c,
                    mention_count=cnt,
                )
            )
        return points
