"""SQLite persistent implementation of VisibilityRepository and VisibilityAnalyticsRepository."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

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
from ai_search_journey.visibility.repository import (
    DuplicateScanError,
    InvalidRepositoryFilterError,
    VisibilityRepository,
)
from ai_search_journey.visibility.v4_analytics import (
    AvailableHistoryRequest,
    AvailableHistoryResult,
    BrandTrendRequest,
    BrandTrendResult,
    CitationAnalysisRequest,
    CitationAnalysisResult,
    CitationDataPoint,
    CompetitorComparisonRequest,
    CompetitorComparisonResult,
    FanoutGapDataPoint,
    FanoutGapRequest,
    FanoutGapResult,
    ScanMetadata,
    TrendDataPoint,
    VisibilityAnalyticsRepository,
    VisibilitySummaryRequest,
    VisibilitySummaryResult,
)

SCHEMA_VERSION = 1

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS visibility_scans (
    scan_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    brand_id TEXT NOT NULL,
    brand_name_snapshot TEXT NOT NULL,
    brand_domain_snapshot TEXT,
    prompt_id TEXT NOT NULL,
    prompt_text_snapshot TEXT NOT NULL,
    model_name TEXT NOT NULL,
    location_snapshot TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    duration_seconds REAL,
    error_code TEXT,
    error_message TEXT,
    bundle_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scans_started_at ON visibility_scans(started_at);
CREATE INDEX IF NOT EXISTS idx_scans_brand_id ON visibility_scans(brand_id);
CREATE INDEX IF NOT EXISTS idx_scans_project_id ON visibility_scans(project_id);

CREATE TABLE IF NOT EXISTS brand_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL,
    brand_id TEXT NOT NULL,
    role TEXT NOT NULL,
    mentioned INTEGER NOT NULL,
    mention_count INTEGER NOT NULL,
    first_mention_position INTEGER,
    retrieved INTEGER NOT NULL,
    best_retrieval_position INTEGER,
    recommended INTEGER NOT NULL,
    recommendation_position INTEGER,
    cited INTEGER NOT NULL,
    citation_urls_json TEXT,
    citation_domains_json TEXT,
    started_at TEXT NOT NULL,
    FOREIGN KEY(scan_id) REFERENCES visibility_scans(scan_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_brand_obs_scan_brand ON brand_observations(scan_id, brand_id);
CREATE INDEX IF NOT EXISTS idx_brand_obs_brand_time ON brand_observations(brand_id, started_at);

CREATE TABLE IF NOT EXISTS fanout_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    query_text TEXT NOT NULL,
    tool TEXT NOT NULL,
    brand_id TEXT NOT NULL,
    brand_found INTEGER NOT NULL,
    position_in_task INTEGER,
    started_at TEXT NOT NULL,
    FOREIGN KEY(scan_id) REFERENCES visibility_scans(scan_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_fanout_obs_brand_time ON fanout_observations(brand_id, started_at);

CREATE TABLE IF NOT EXISTS citations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id TEXT NOT NULL,
    url TEXT NOT NULL,
    domain TEXT NOT NULL,
    source_type TEXT NOT NULL,
    matched_brand_ids_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    FOREIGN KEY(scan_id) REFERENCES visibility_scans(scan_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_citations_started_at ON citations(started_at);
CREATE INDEX IF NOT EXISTS idx_citations_domain ON citations(domain);
"""


def _iso_to_datetime(val: str) -> datetime:
    val = val.replace("Z", "+00:00")
    dt = datetime.fromisoformat(val)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class SQLiteVisibilityRepository(VisibilityRepository, VisibilityAnalyticsRepository):
    """Unified SQLite persistent repository supporting both V3 scanning and V4/MCP analytics."""

    def __init__(self, db_path: str | Path = ".data/visibility_history.db") -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            isolation_level=None,  # Autocommit mode, manual transactions via BEGIN
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self) -> None:
        conn = self._get_connection()
        try:
            with conn:
                conn.executescript(CREATE_TABLES_SQL)
                cur = conn.execute("SELECT version FROM schema_version LIMIT 1")
                row = cur.fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
                    )
        finally:
            conn.close()

    # ==================================================================
    # VisibilityRepository (V3 Write & Query) Implementation
    # ==================================================================

    def save_bundle(self, bundle: VisibilityScanBundle) -> None:
        """Persist a completed scan bundle idempotently."""
        scan_id = bundle.scan.scan_id
        if not scan_id or not scan_id.strip():
            raise ValueError("scan_id cannot be blank")

        if bundle.scan.status != ScanStatus.COMPLETED:
            raise ValueError(
                f"Only COMPLETED scans can be saved, got {bundle.scan.status.value}"
            )

        bundle_dump = bundle.model_dump(mode="json")
        bundle_json_str = json.dumps(bundle_dump, sort_keys=True)

        conn = self._get_connection()
        try:
            with conn:
                cur = conn.execute(
                    "SELECT bundle_json FROM visibility_scans WHERE scan_id = ?",
                    (scan_id,),
                )
                existing_row = cur.fetchone()
                if existing_row is not None:
                    existing_json = existing_row["bundle_json"]
                    try:
                        existing_dump = json.loads(existing_json)
                    except Exception:
                        existing_dump = None

                    if existing_dump == bundle_dump:
                        return
                    raise DuplicateScanError(
                        f"Conflicting scan bundle already exists for scan_id '{scan_id}'"
                    )

                scan = bundle.scan
                started_at_str = scan.started_at.isoformat()
                completed_at_str = scan.completed_at.isoformat() if scan.completed_at else None

                conn.execute(
                    """
                    INSERT INTO visibility_scans (
                        scan_id, batch_id, project_id, brand_id, brand_name_snapshot,
                        brand_domain_snapshot, prompt_id, prompt_text_snapshot, model_name,
                        location_snapshot, started_at, completed_at, status, duration_seconds,
                        error_code, error_message, bundle_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        scan.scan_id,
                        scan.batch_id,
                        scan.project_id,
                        scan.brand_id,
                        scan.brand_name_snapshot,
                        scan.brand_domain_snapshot,
                        scan.prompt_id,
                        scan.prompt_text_snapshot,
                        scan.model_name,
                        scan.location_snapshot,
                        started_at_str,
                        completed_at_str,
                        scan.status.value,
                        scan.duration_seconds,
                        scan.error_code,
                        scan.error_message,
                        bundle_json_str,
                    ),
                )

                for bo in bundle.brand_observations:
                    conn.execute(
                        """
                        INSERT INTO brand_observations (
                            scan_id, brand_id, role, mentioned, mention_count,
                            first_mention_position, retrieved, best_retrieval_position,
                            recommended, recommendation_position, cited, citation_urls_json,
                            citation_domains_json, started_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            bo.scan_id,
                            bo.brand_id,
                            bo.role.value,
                            1 if bo.mentioned else 0,
                            bo.mention_count,
                            bo.first_mention_position,
                            1 if bo.retrieved else 0,
                            bo.best_retrieval_position,
                            1 if bo.recommended else 0,
                            bo.recommendation_position,
                            1 if bo.cited else 0,
                            json.dumps(bo.citation_urls),
                            json.dumps(bo.citation_domains),
                            started_at_str,
                        ),
                    )

                for fo in bundle.fanout_observations:
                    conn.execute(
                        """
                        INSERT INTO fanout_observations (
                            scan_id, task_id, query_text, tool, brand_id,
                            brand_found, position_in_task, started_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            fo.scan_id,
                            fo.task_id,
                            fo.query_text,
                            fo.tool,
                            fo.brand_id,
                            1 if fo.brand_found else 0,
                            fo.position_in_task,
                            started_at_str,
                        ),
                    )

                for co in bundle.citations:
                    conn.execute(
                        """
                        INSERT INTO citations (
                            scan_id, url, domain, source_type, matched_brand_ids_json, started_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            co.scan_id,
                            co.url,
                            co.domain,
                            co.source_type,
                            json.dumps(co.matched_brand_ids),
                            started_at_str,
                        ),
                    )
        finally:
            conn.close()

    def get_bundle(self, scan_id: str) -> VisibilityScanBundle | None:
        """Retrieve defensive copy of a scan bundle by scan_id."""
        if not scan_id:
            return None
        conn = self._get_connection()
        try:
            cur = conn.execute(
                "SELECT bundle_json FROM visibility_scans WHERE scan_id = ?",
                (scan_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            data = json.loads(row["bundle_json"])
            return VisibilityScanBundle.model_validate(data)
        finally:
            conn.close()

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

        if limit is not None and limit < 1:
            raise InvalidRepositoryFilterError(f"limit must be >= 1, got {limit}")

        clauses: list[str] = []
        params: list[Any] = []

        if project_id is not None:
            clauses.append("s.project_id = ?")
            params.append(project_id)
        if prompt_id is not None:
            clauses.append("s.prompt_id = ?")
            params.append(prompt_id)
        if batch_id is not None:
            clauses.append("s.batch_id = ?")
            params.append(batch_id)
        if start_time is not None:
            clauses.append("s.started_at >= ?")
            params.append(start_time.isoformat())
        if end_time is not None:
            clauses.append("s.started_at <= ?")
            params.append(end_time.isoformat())

        if brand_id is not None:
            clauses.append(
                """
                EXISTS (
                    SELECT 1 FROM brand_observations bo
                    WHERE bo.scan_id = s.scan_id AND bo.brand_id = ?
                )
                """
            )
            params.append(brand_id)

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_clause = f"LIMIT {int(limit)}" if limit is not None else ""

        sql = f"""
        SELECT s.bundle_json
        FROM visibility_scans s
        {where_clause}
        ORDER BY s.started_at ASC, s.scan_id ASC
        {limit_clause}
        """

        conn = self._get_connection()
        try:
            cur = conn.execute(sql, params)
            rows = cur.fetchall()
            bundles: list[VisibilityScanBundle] = []
            for r in rows:
                data = json.loads(r["bundle_json"])
                bundles.append(VisibilityScanBundle.model_validate(data))
            return bundles
        finally:
            conn.close()

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

    # ==================================================================
    # VisibilityAnalyticsRepository (V4 & MCP) Implementation
    # ==================================================================

    def get_available_history(self, request: AvailableHistoryRequest) -> AvailableHistoryResult:
        """Discovers available historical scan metadata, bounds, total scans, and recent scans."""
        conn = self._get_connection()
        try:
            # Summary query
            summary_sql = """
            SELECT
                MIN(started_at) AS earliest_started_at,
                MAX(started_at) AS latest_started_at,
                COUNT(DISTINCT scan_id) AS total_scans
            FROM brand_observations
            WHERE datetime(started_at) >= datetime('now', '-' || ? || ' days')
            """
            cur = conn.execute(summary_sql, (request.lookback_days,))
            summary_row = cur.fetchone()

            distinct_brands_sql = """
            SELECT DISTINCT brand_id
            FROM brand_observations
            WHERE datetime(started_at) >= datetime('now', '-' || ? || ' days')
            ORDER BY brand_id ASC
            """
            cur_brands = conn.execute(distinct_brands_sql, (request.lookback_days,))
            distinct_brand_ids = [r["brand_id"] for r in cur_brands.fetchall()]

            recent_sql = """
            SELECT
                scan_id,
                started_at,
                brand_id,
                brand_name_snapshot,
                prompt_text_snapshot
            FROM visibility_scans
            WHERE datetime(started_at) >= datetime('now', '-' || ? || ' days')
            ORDER BY started_at DESC
            LIMIT 10
            """
            cur_recent = conn.execute(recent_sql, (request.lookback_days,))
            recent_scans = [
                ScanMetadata(
                    scan_id=row["scan_id"],
                    started_at=row["started_at"],
                    brand_id=row["brand_id"],
                    brand_name_snapshot=row["brand_name_snapshot"],
                    prompt_text_snapshot=row["prompt_text_snapshot"],
                )
                for row in cur_recent.fetchall()
            ]

            total_scans = int(summary_row["total_scans"] or 0) if summary_row else 0
            earliest_started_at = summary_row["earliest_started_at"] if summary_row else None
            latest_started_at = summary_row["latest_started_at"] if summary_row else None

            return AvailableHistoryResult(
                earliest_started_at=earliest_started_at,
                latest_started_at=latest_started_at,
                total_scans=total_scans,
                distinct_brand_ids=distinct_brand_ids,
                recent_scans=recent_scans,
            )
        finally:
            conn.close()

    def get_visibility_summary(self, request: VisibilitySummaryRequest) -> VisibilitySummaryResult:
        """Aggregates overall brand visibility for a date range."""
        conn = self._get_connection()
        try:
            sql = """
            SELECT
                COUNT(DISTINCT scan_id) AS total_scans,
                SUM(CASE WHEN mentioned = 1 THEN 1 ELSE 0 END) AS mentioned_scans,
                SUM(CASE WHEN recommended = 1 THEN 1 ELSE 0 END) AS recommended_scans,
                SUM(CASE WHEN cited = 1 THEN 1 ELSE 0 END) AS cited_scans
            FROM brand_observations
            WHERE started_at >= ? AND started_at <= ?
                AND brand_id = ?
            """
            cur = conn.execute(
                sql,
                (
                    request.start_date.isoformat(),
                    request.end_date.isoformat(),
                    request.brand_id,
                ),
            )
            row = cur.fetchone()
            if not row or not row["total_scans"]:
                return VisibilitySummaryResult(
                    brand_id=request.brand_id,
                    total_scans=0,
                    mention_rate=0.0,
                    recommendation_rate=0.0,
                    citation_rate=0.0,
                )

            t = int(row["total_scans"] or 0)
            if t == 0:
                return VisibilitySummaryResult(
                    brand_id=request.brand_id,
                    total_scans=0,
                    mention_rate=0.0,
                    recommendation_rate=0.0,
                    citation_rate=0.0,
                )

            m = int(row["mentioned_scans"] or 0)
            r = int(row["recommended_scans"] or 0)
            c = int(row["cited_scans"] or 0)

            return VisibilitySummaryResult(
                brand_id=request.brand_id,
                total_scans=t,
                mention_rate=m / t,
                recommendation_rate=r / t,
                citation_rate=c / t,
            )
        finally:
            conn.close()

    def get_brand_trend(self, request: BrandTrendRequest) -> BrandTrendResult:
        """Returns chronological data points showing how a brand's metrics changed over time."""
        conn = self._get_connection()
        try:
            sql = """
            SELECT
                strftime('%Y-%m-%d', started_at) as date_str,
                COUNT(DISTINCT scan_id) AS total_scans,
                SUM(CASE WHEN mentioned = 1 THEN 1 ELSE 0 END) AS mentioned_scans,
                SUM(CASE WHEN recommended = 1 THEN 1 ELSE 0 END) AS recommended_scans
            FROM brand_observations
            WHERE started_at >= ? AND started_at <= ?
                AND brand_id = ?
            GROUP BY date_str
            ORDER BY date_str ASC
            """
            cur = conn.execute(
                sql,
                (
                    request.start_date.isoformat(),
                    request.end_date.isoformat(),
                    request.brand_id,
                ),
            )
            rows = cur.fetchall()
            trends: list[TrendDataPoint] = []
            for row in rows:
                d = row["date_str"]
                t = int(row["total_scans"] or 0)
                m = int(row["mentioned_scans"] or 0)
                r = int(row["recommended_scans"] or 0)
                if t > 0:
                    trends.append(
                        TrendDataPoint(
                            date=d,
                            mention_rate=m / t,
                            recommendation_rate=r / t,
                        )
                    )
            return BrandTrendResult(brand_id=request.brand_id, trends=trends)
        finally:
            conn.close()

    def compare_brands(self, request: CompetitorComparisonRequest) -> CompetitorComparisonResult:
        """Calculates comparative visibility metrics for multiple brands."""
        conn = self._get_connection()
        try:
            placeholders = ",".join("?" for _ in request.brand_ids)
            sql = f"""
            SELECT
                brand_id,
                COUNT(DISTINCT scan_id) AS total_scans,
                SUM(CASE WHEN mentioned = 1 THEN 1 ELSE 0 END) AS mentioned_scans,
                SUM(CASE WHEN recommended = 1 THEN 1 ELSE 0 END) AS recommended_scans,
                SUM(CASE WHEN cited = 1 THEN 1 ELSE 0 END) AS cited_scans
            FROM brand_observations
            WHERE started_at >= ? AND started_at <= ?
                AND brand_id IN ({placeholders})
            GROUP BY brand_id
            """
            params = [
                request.start_date.isoformat(),
                request.end_date.isoformat(),
                *request.brand_ids,
            ]
            cur = conn.execute(sql, params)
            rows = cur.fetchall()

            brand_map = {b: (0, 0, 0, 0) for b in request.brand_ids}
            for row in rows:
                b = row["brand_id"]
                t = int(row["total_scans"] or 0)
                m = int(row["mentioned_scans"] or 0)
                r = int(row["recommended_scans"] or 0)
                c = int(row["cited_scans"] or 0)
                brand_map[b] = (t, m, r, c)

            metrics: list[VisibilitySummaryResult] = []
            for b in request.brand_ids:
                t, m, r, c = brand_map[b]
                if t == 0:
                    metrics.append(
                        VisibilitySummaryResult(
                            brand_id=b,
                            total_scans=0,
                            mention_rate=0.0,
                            recommendation_rate=0.0,
                            citation_rate=0.0,
                        )
                    )
                else:
                    metrics.append(
                        VisibilitySummaryResult(
                            brand_id=b,
                            total_scans=t,
                            mention_rate=m / t,
                            recommendation_rate=r / t,
                            citation_rate=c / t,
                        )
                    )

            return CompetitorComparisonResult(metrics=metrics)
        finally:
            conn.close()

    def analyze_citations(self, request: CitationAnalysisRequest) -> CitationAnalysisResult:
        """Analyzes top citation domains and source types for a brand."""
        conn = self._get_connection()
        try:
            # We filter citations by checking if brand_id is in matched_brand_ids_json
            sql = """
            SELECT
                domain,
                source_type,
                matched_brand_ids_json
            FROM citations
            WHERE started_at >= ? AND started_at <= ?
            """
            cur = conn.execute(
                sql,
                (
                    request.start_date.isoformat(),
                    request.end_date.isoformat(),
                ),
            )
            rows = cur.fetchall()

            # Group and count in Python for clean JSON parsing
            counts: dict[tuple[str, str], int] = {}
            for row in rows:
                matched_ids: list[str] = json.loads(row["matched_brand_ids_json"])
                if request.brand_id in matched_ids:
                    key = (row["domain"], row["source_type"])
                    counts[key] = counts.get(key, 0) + 1

            sorted_items = sorted(counts.items(), key=lambda item: item[1], reverse=True)
            top_items = sorted_items[: request.limit]

            citations = [
                CitationDataPoint(
                    domain=key[0],
                    source_type=key[1],
                    count=cnt,
                )
                for key, cnt in top_items
            ]

            return CitationAnalysisResult(brand_id=request.brand_id, top_citations=citations)
        finally:
            conn.close()

    def find_fanout_gaps(self, request: FanoutGapRequest) -> FanoutGapResult:
        """Discovers search fan-out queries where the brand was missing."""
        conn = self._get_connection()
        try:
            sql = """
            SELECT
                query_text,
                tool,
                COUNT(*) as miss_count
            FROM fanout_observations
            WHERE started_at >= ? AND started_at <= ?
                AND brand_id = ?
                AND brand_found = 0
            GROUP BY query_text, tool
            ORDER BY miss_count DESC
            LIMIT ?
            """
            cur = conn.execute(
                sql,
                (
                    request.start_date.isoformat(),
                    request.end_date.isoformat(),
                    request.brand_id,
                    request.limit,
                ),
            )
            rows = cur.fetchall()
            gaps = [
                FanoutGapDataPoint(
                    query_text=row["query_text"],
                    tool=row["tool"],
                    miss_count=int(row["miss_count"]),
                )
                for row in rows
            ]
            return FanoutGapResult(brand_id=request.brand_id, gaps=gaps)
        finally:
            conn.close()
