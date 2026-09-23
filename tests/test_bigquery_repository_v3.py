"""Unit tests for BigQueryVisibilityRepository (V3 Milestone 4)."""

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import pytest

from ai_search_journey.visibility.bigquery_repository import (
    BigQueryDependencyError,
    BigQueryVisibilityRepository,
    BigQueryWriteError,
)
from ai_search_journey.visibility.bigquery_schema import (
    InvalidIdentifierError,
    calculate_bundle_sha256,
    serialize_bundle_canonically,
)
from ai_search_journey.visibility.models import (
    BrandObservation,
    BrandRole,
    ScanStatus,
    VisibilityScan,
    VisibilityScanBundle,
)
from ai_search_journey.visibility.repository import (
    DuplicateScanError,
    InvalidRepositoryFilterError,
    VisibilityRepository,
)

# ======================================================================
# Fake / Mock Client Implementation
# ======================================================================


class FakeQueryJob:
    """Mock query job returned by FakeBigQueryClient."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def result(self) -> list[Any]:
        return self._rows

    def __iter__(self) -> Any:
        return iter(self._rows)


class FakeBigQueryClient:
    """In-memory mock BigQuery client capturing queries and parameters without network calls."""

    def __init__(self) -> None:
        self.executed_queries: list[tuple[str, list[Any]]] = []
        self.query_handler: Callable[[str, list[Any]], list[Any]] | None = None

    def query(self, sql: str, job_config: Any = None) -> FakeQueryJob:
        params = getattr(job_config, "query_parameters", []) if job_config else []
        self.executed_queries.append((sql, params))
        if self.query_handler:
            rows = self.query_handler(sql, params)
        else:
            rows = []
        return FakeQueryJob(rows)


def _make_test_bundle(
    scan_id: str = "scan_001",
    brand_id: str = "brand_target",
    brand_name: str = "Target Cafe",
    started_at: datetime | None = None,
    status: ScanStatus = ScanStatus.COMPLETED,
) -> VisibilityScanBundle:
    t = started_at or datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    scan = VisibilityScan(
        scan_id=scan_id,
        batch_id="batch_001",
        project_id="proj_001",
        brand_id=brand_id,
        brand_name_snapshot=brand_name,
        brand_domain_snapshot="targetcafe.com",
        prompt_id="prompt_001",
        prompt_text_snapshot="best artisan coffee",
        model_name="gemini-2.5-flash",
        started_at=t,
        completed_at=t,
        status=status,
    )
    obs = BrandObservation(
        scan_id=scan_id,
        brand_id=brand_id,
        role=BrandRole.TARGET,
        mentioned=True,
        mention_count=2,
        first_mention_position=10,
        retrieved=True,
        best_retrieval_position=1,
        recommended=True,
        recommendation_position=1,
        cited=True,
        citation_urls=["https://targetcafe.com"],
        citation_domains=["targetcafe.com"],
    )
    return VisibilityScanBundle(scan=scan, brand_observations=[obs])


# ======================================================================
# Repository Tests (Requirements 14-36)
# ======================================================================


def test_lazy_dependency_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    """14. Instantiating without client and without SDK raises BigQueryDependencyError."""
    monkeypatch.setattr(
        "ai_search_journey.visibility.bigquery_repository._get_bigquery_module",
        lambda: None
    )
    with pytest.raises(BigQueryDependencyError, match=r'pip install -e "\.\[bigquery\]"'):
        BigQueryVisibilityRepository(project_id="my-project")


def test_constructor_validates_identifiers() -> None:
    """15. Constructor validates project, dataset, and location tokens."""
    client = FakeBigQueryClient()

    with pytest.raises(InvalidIdentifierError):
        BigQueryVisibilityRepository(project_id="proj; DROP TABLE x;", client=client)

    with pytest.raises(InvalidIdentifierError):
        BigQueryVisibilityRepository(
            project_id="valid-project", dataset_id="bad-dataset-with-hyphen", client=client
        )

    with pytest.raises(InvalidIdentifierError):
        BigQueryVisibilityRepository(
            project_id="valid-project", location="US `injection`", client=client
        )


def test_protocol_conformance() -> None:
    """16. BigQueryVisibilityRepository satisfies VisibilityRepository Protocol."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)
    assert isinstance(repo, VisibilityRepository)


def test_exact_duplicate_save_is_a_no_op() -> None:
    """17. Exact duplicate save commits cleanly without fact changes."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)
    bundle = _make_test_bundle("scan_100")
    expected_hash = calculate_bundle_sha256(bundle)

    repo.save_bundle(bundle)
    assert len(client.executed_queries) == 1
    sql, params = client.executed_queries[0]

    # Verify script handles existing matching hash as idempotent commit
    assert "IF existing_hash = @payload_sha256 THEN\n    COMMIT TRANSACTION;" in sql
    param_map = {p.name: getattr(p, "value", getattr(p, "values", None)) for p in params}
    assert param_map["scan_id"] == "scan_100"
    assert param_map["payload_sha256"] == expected_hash


def test_conflicting_duplicate_raises_duplicate_scan_error() -> None:
    """18. Conflicting duplicate save aborts transaction and raises DuplicateScanError."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)
    bundle = _make_test_bundle("scan_100")

    def _handler(sql: str, params: list[Any]) -> list[Any]:
        raise Exception(
            "DUPLICATE_SCAN_ERROR: Conflicting scan bundle already exists for scan_id: scan_100"
        )

    client.query_handler = _handler

    with pytest.raises(DuplicateScanError, match="Conflicting scan bundle already exists"):
        repo.save_bundle(bundle)

    assert len(client.executed_queries) == 1


def test_save_emits_one_transactional_script_with_lock_gate() -> None:
    """19. Save emits ONE transactional script with BEGIN/COMMIT and lock gate."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)
    bundle = _make_test_bundle("scan_200")

    repo.save_bundle(bundle)

    # Exactly one transactional query job emitted
    assert len(client.executed_queries) == 1
    sql, params = client.executed_queries[0]

    # BEGIN and COMMIT TRANSACTION present
    assert "BEGIN TRANSACTION;" in sql
    assert "COMMIT TRANSACTION;" in sql

    # Serialization gate UPDATE on repository_locks appears before marker SELECT and fact writes
    lock_update = "UPDATE `my-project.ai_search_journey_v3.repository_locks`"
    scans_insert = "INSERT INTO `my-project.ai_search_journey_v3.visibility_scans`"
    payload_insert = "INSERT INTO `my-project.ai_search_journey_v3.bundle_payloads`"

    idx_begin = sql.index("BEGIN TRANSACTION;")
    idx_lock = sql.index(lock_update)
    idx_marker_read = sql.index("SELECT payload_sha256")
    idx_fact_write = sql.index(scans_insert)
    idx_marker_write = sql.index(payload_insert)
    idx_commit = sql.rindex("COMMIT TRANSACTION;")

    assert idx_begin < idx_lock < idx_marker_read < idx_fact_write < idx_marker_write < idx_commit

    # Serialization lock row presence check is enforced
    assert "IF @@row_count = 0 THEN" in sql
    assert "Repository lock row missing. Run setup_bigquery_v3.py --apply" in sql

    # Orphan cleanup in partition is included
    assert "DELETE FROM `my-project.ai_search_journey_v3.visibility_scans`" in sql
    assert "DATE(started_at) = DATE(@started_at)" in sql


def test_transaction_rollback_on_sdk_error_wraps_cause() -> None:
    """20. Transaction error during save raises BigQueryWriteError and wraps __cause__."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)
    bundle = _make_test_bundle("scan_err")

    def _handler(sql: str, params: list[Any]) -> list[Any]:
        raise RuntimeError("BigQuery transaction rolled back due to internal backend error")

    client.query_handler = _handler

    with pytest.raises(
        BigQueryWriteError, match="Failed to save bundle 'scan_err' to BigQuery"
    ) as exc_info:
        repo.save_bundle(bundle)

    assert isinstance(exc_info.value.__cause__, RuntimeError)


def test_missing_lock_row_fails_with_setup_instructions() -> None:
    """20b. Missing lock row raises BigQueryWriteError with setup instructions."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)
    bundle = _make_test_bundle("scan_no_lock")

    def _handler(sql: str, params: list[Any]) -> list[Any]:
        raise Exception(
            "Repository lock row missing. Run setup_bigquery_v3.py --apply to "
            "initialize repository_locks."
        )

    client.query_handler = _handler

    with pytest.raises(BigQueryWriteError, match="setup_bigquery_v3.py --apply"):
        repo.save_bundle(bundle)


def test_get_bundle_returns_parsed_bundle() -> None:
    """21. get_bundle returns validated VisibilityScanBundle model instance."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)
    original_bundle = _make_test_bundle("scan_abc")
    raw_json = serialize_bundle_canonically(original_bundle)

    client.query_handler = lambda sql, params: [{"bundle_json": raw_json}]

    result = repo.get_bundle("scan_abc")
    assert result is not None
    assert result.scan.scan_id == "scan_abc"
    assert result.scan.brand_name_snapshot == "Target Cafe"


def test_get_bundle_missing_returns_none() -> None:
    """22. get_bundle returns None when scan_id is not in bundle_payloads."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)

    client.query_handler = lambda sql, params: []

    assert repo.get_bundle("scan_nonexistent") is None


def test_get_bundle_uses_parameterized_scan_id() -> None:
    """23. get_bundle uses @scan_id query parameter and rejects blank scan_id."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)

    with pytest.raises(ValueError, match="scan_id cannot be blank"):
        repo.get_bundle("")

    with pytest.raises(ValueError, match="scan_id cannot be blank"):
        repo.get_bundle("   ")

    repo.get_bundle("scan_target")
    sql, params = client.executed_queries[-1]
    assert "WHERE scan_id = @scan_id" in sql
    assert any(p.name == "scan_id" and p.value == "scan_target" for p in params)


def test_list_query_always_has_partition_bounds() -> None:
    """24. list_bundles queries include started_at partition filters."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)

    repo.list_bundles()
    sql, params = client.executed_queries[0]
    assert "started_at >= @start_time" in sql
    assert "started_at <= @end_time" in sql


def test_default_30_day_bound() -> None:
    """25. When dates are omitted, default_history_days (30 days) is applied via injected clock."""
    client = FakeBigQueryClient()
    fixed_now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    repo = BigQueryVisibilityRepository(
        project_id="my-project", client=client, clock=lambda: fixed_now
    )

    repo.list_bundles()
    sql, params = client.executed_queries[0]
    start_param = next(p for p in params if p.name == "start_time")
    end_param = next(p for p in params if p.name == "end_time")

    assert end_param.value == fixed_now
    assert start_param.value == fixed_now - timedelta(days=30)


def test_inclusive_explicit_bounds() -> None:
    """26. Explicit inclusive time bounds are respected and validated."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)

    t1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 10, 10, 0, 0, tzinfo=timezone.utc)

    repo.list_bundles(start_time=t1, end_time=t2)
    sql, params = client.executed_queries[0]
    start_param = next(p for p in params if p.name == "start_time")
    end_param = next(p for p in params if p.name == "end_time")

    assert start_param.value == t1
    assert end_param.value == t2

    # Naive rejection
    with pytest.raises(InvalidRepositoryFilterError, match="timezone-aware"):
        repo.list_bundles(start_time=datetime(2026, 1, 1, 10, 0, 0))

    # start > end rejection
    with pytest.raises(InvalidRepositoryFilterError, match="cannot be later than end_time"):
        repo.list_bundles(start_time=t2, end_time=t1)


def test_all_values_use_parameters() -> None:
    """27. All query filter values use BigQuery parameters, avoiding interpolation."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)

    repo.list_bundles(
        project_id="proj_x",
        prompt_id="prompt_y",
        batch_id="batch_z",
        brand_id="brand_w",
        limit=5,
    )

    sql, params = client.executed_queries[0]
    param_names = {p.name for p in params}
    assert "project_id" in param_names
    assert "prompt_id" in param_names
    assert "batch_id" in param_names
    assert "brand_id" in param_names
    assert "limit" in param_names

    assert "proj_x" not in sql
    assert "prompt_y" not in sql
    assert "batch_z" not in sql
    assert "brand_w" not in sql


def test_batch_fetch_avoids_n_plus_one_queries() -> None:
    """28. list_bundles fetches all matching bundle payloads in one single UNNEST query."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)

    b1 = _make_test_bundle("s1")
    b2 = _make_test_bundle("s2")
    b3 = _make_test_bundle("s3")

    def handler(sql: str, params: list[Any]) -> list[Any]:
        if "visibility_scans" in sql:
            return [{"scan_id": "s1"}, {"scan_id": "s2"}, {"scan_id": "s3"}]
        if "bundle_payloads" in sql:
            return [
                {"scan_id": "s1", "bundle_json": serialize_bundle_canonically(b1)},
                {"scan_id": "s2", "bundle_json": serialize_bundle_canonically(b2)},
                {"scan_id": "s3", "bundle_json": serialize_bundle_canonically(b3)},
            ]
        return []

    client.query_handler = handler

    results = repo.list_bundles()
    assert len(results) == 3
    # Exactly 2 queries: 1 to visibility_scans, 1 batch query to bundle_payloads
    assert len(client.executed_queries) == 2
    assert "WHERE scan_id IN UNNEST(@scan_ids)" in client.executed_queries[1][0]


def test_deterministic_listing_order() -> None:
    """29. list_bundles ensures ordering by started_at ASC, scan_id ASC."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)

    b1 = _make_test_bundle("scan_1")
    b2 = _make_test_bundle("scan_2")

    def handler(sql: str, params: list[Any]) -> list[Any]:
        if "visibility_scans" in sql:
            return [{"scan_id": "scan_1"}, {"scan_id": "scan_2"}]
        if "bundle_payloads" in sql:
            # Payloads returned in reverse order to test client-side order preservation
            return [
                {"scan_id": "scan_2", "bundle_json": serialize_bundle_canonically(b2)},
                {"scan_id": "scan_1", "bundle_json": serialize_bundle_canonically(b1)},
            ]
        return []

    client.query_handler = handler

    results = repo.list_bundles()
    assert [b.scan.scan_id for b in results] == ["scan_1", "scan_2"]


def test_metrics_sql_matches_in_memory_formulas() -> None:
    """30. Analytical SQL matches in-memory formulas and parses correctly."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)

    client.query_handler = lambda sql, params: [
        {
            "brand_id": "brand_target",
            "total_scans": 10,
            "mention_rate": 0.8,
            "recommendation_rate": 0.6,
            "citation_rate": 0.4,
            "average_recommendation_position": 2.5,
            "share_of_voice": 0.35,
            "fanout_coverage": 0.75,
        }
    ]

    m = repo.get_metrics("brand_target")
    assert m.brand_id == "brand_target"
    assert m.total_scans == 10
    assert m.mention_rate == 0.8
    assert m.recommendation_rate == 0.6
    assert m.citation_rate == 0.4
    assert m.average_recommendation_position == 2.5
    assert m.share_of_voice == 0.35
    assert m.fanout_coverage == 0.75


def test_share_of_voice_denominator_uses_same_selected_scans() -> None:
    """31. Share of voice CTE joins brand_observations across the exact tracked_brand_scans."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)

    client.query_handler = lambda sql, params: [
        {
            "brand_id": "brand_target",
            "total_scans": 1,
            "mention_rate": 1.0,
            "recommendation_rate": 1.0,
            "citation_rate": 0.0,
            "average_recommendation_position": None,
            "share_of_voice": 0.5,
            "fanout_coverage": 0.0,
        }
    ]

    repo.get_metrics("brand_target")
    sql = client.executed_queries[0][0]
    assert "market_stats_per_brand AS" in sql
    assert "FROM tracked_brand_scans tbs" in sql
    assert "tbs.scan_id = all_bo.scan_id" in sql


def test_competitor_comparison_uses_one_set_based_query() -> None:
    """32. Competitor comparison queries all brands in a single set-based SQL statement."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)

    brand_ids = ["brand_c", "brand_a", "brand_b"]
    client.query_handler = lambda sql, params: [
        {"brand_id": bid, "total_scans": 0, "mention_rate": 0.0, "recommendation_rate": 0.0,
         "citation_rate": 0.0, "average_recommendation_position": None, "share_of_voice": 0.0,
         "fanout_coverage": 0.0}
        for bid in brand_ids
    ]

    results = repo.get_competitor_comparison(brand_ids)
    assert len(results) == 3
    # Exactly 1 query executed
    assert len(client.executed_queries) == 1
    sql, params = client.executed_queries[0]
    assert "UNNEST(@brand_ids) WITH OFFSET AS brand_order" in sql


def test_competitor_output_preserves_input_order() -> None:
    """33. Competitor comparison preserves supplied brand_ids order."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)

    supplied = ["brand_z", "brand_y", "brand_x"]
    client.query_handler = lambda sql, params: [
        {"brand_id": bid, "total_scans": 1, "mention_rate": 1.0, "recommendation_rate": 1.0,
         "citation_rate": 0.0, "average_recommendation_position": None, "share_of_voice": 0.2,
         "fanout_coverage": 0.5}
        for bid in supplied
    ]

    results = repo.get_competitor_comparison(supplied)
    assert [m.brand_id for m in results] == supplied


def test_trend_ordering() -> None:
    """34. get_trend returns VisibilityTrendPoint objects ordered chronologically."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)

    t1 = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 1, 2, 10, 0, 0, tzinfo=timezone.utc)

    client.query_handler = lambda sql, params: [
        {"scan_id": "s1", "started_at": t1, "mentioned": True, "recommended": False,
         "recommendation_position": None, "cited": False, "mention_count": 2},
        {"scan_id": "s2", "started_at": t2, "mentioned": True, "recommended": True,
         "recommendation_position": 1, "cited": True, "mention_count": 5},
    ]

    trend = repo.get_trend("brand_target")
    assert len(trend) == 2
    assert trend[0].scan_id == "s1"
    assert trend[0].started_at == t1
    assert trend[1].scan_id == "s2"
    assert trend[1].recommended is True
    assert trend[1].recommendation_position == 1

    sql = client.executed_queries[0][0]
    assert "ORDER BY started_at ASC, scan_id ASC" in sql


def test_bigquery_errors_are_wrapped_with_cause() -> None:
    """35. Underlying BigQuery errors are wrapped in BigQueryWriteError with __cause__."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)
    bundle = _make_test_bundle("scan_err")

    root_exc = ConnectionError("Network failure connecting to BigQuery")

    def failing_handler(sql: str, params: list[Any]) -> list[Any]:
        raise root_exc

    client.query_handler = failing_handler

    with pytest.raises(BigQueryWriteError) as exc_info:
        repo.save_bundle(bundle)

    assert exc_info.value.__cause__ is root_exc


def test_no_network_calls() -> None:
    """36. Repository runs completely with fake client and makes no network socket connections."""
    client = FakeBigQueryClient()
    repo = BigQueryVisibilityRepository(project_id="my-project", client=client)

    assert repo._client is client
    assert len(client.executed_queries) == 0
