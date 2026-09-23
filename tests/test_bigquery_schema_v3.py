"""Unit tests for BigQuery schema, identifier safety, and serialization (V3)."""

from datetime import datetime, timezone

import pytest

from ai_search_journey.visibility.bigquery_schema import (
    ALL_TABLES,
    LOCK_KEY_BUNDLE_WRITE,
    TABLE_BRAND_OBSERVATIONS,
    TABLE_BUNDLE_PAYLOADS,
    TABLE_CITATIONS,
    TABLE_FANOUT_OBSERVATIONS,
    TABLE_REPOSITORY_LOCKS,
    TABLE_VISIBILITY_SCANS,
    InvalidIdentifierError,
    calculate_bundle_sha256,
    get_repository_locks_ddl,
    get_repository_locks_seed_dml,
    get_schema_ddl_statements,
    get_schema_seed_statements,
    serialize_bundle_canonically,
    validate_dataset_id,
    validate_location,
    validate_project_id,
)
from ai_search_journey.visibility.models import (
    BrandObservation,
    BrandRole,
    ScanStatus,
    VisibilityScan,
    VisibilityScanBundle,
)
from scripts.setup_bigquery_v3 import setup_bigquery_schema

# ======================================================================
# Helpers
# ======================================================================


def _make_test_bundle(
    scan_id: str = "scan_001", brand_name: str = "Artisan Cafe"
) -> VisibilityScanBundle:
    t = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    scan = VisibilityScan(
        scan_id=scan_id,
        batch_id="batch_001",
        project_id="proj_001",
        brand_id="brand_target",
        brand_name_snapshot=brand_name,
        brand_domain_snapshot="artisancafe.com",
        prompt_id="prompt_001",
        prompt_text_snapshot="best artisan coffee in Austin",
        model_name="gemini-2.5-flash",
        started_at=t,
        completed_at=t,
        status=ScanStatus.COMPLETED,
    )
    obs = BrandObservation(
        scan_id=scan_id,
        brand_id="brand_target",
        role=BrandRole.TARGET,
        mentioned=True,
        mention_count=2,
        first_mention_position=10,
        retrieved=True,
        best_retrieval_position=1,
        recommended=True,
        recommendation_position=1,
        cited=True,
        citation_urls=["https://artisancafe.com"],
        citation_domains=["artisancafe.com"],
    )
    return VisibilityScanBundle(scan=scan, brand_observations=[obs])


# ======================================================================
# Schema Tests (1-9)
# ======================================================================


def test_required_tables_exist_in_ddl() -> None:
    """1. Verify all required table names exist in generated DDL statements."""
    statements = get_schema_ddl_statements("my-project", "my_dataset")
    assert len(statements) == 6

    combined_ddl = "\n".join(statements)
    for table_name in ALL_TABLES:
        assert f"my_dataset.{table_name}" in combined_ddl


def test_correct_fields_exist() -> None:
    """2. Verify required fields exist in respective table definitions."""
    statements = get_schema_ddl_statements("my-project", "my_dataset")
    ddl_by_table = {ALL_TABLES[i]: statements[i] for i in range(len(ALL_TABLES))}

    # repository_locks fields
    rl = ddl_by_table[TABLE_REPOSITORY_LOCKS]
    assert "lock_key STRING NOT NULL" in rl
    assert "lock_version INT64 NOT NULL" in rl

    # bundle_payloads fields
    bp = ddl_by_table[TABLE_BUNDLE_PAYLOADS]
    assert "scan_id STRING NOT NULL" in bp
    assert "payload_sha256 STRING NOT NULL" in bp
    assert "bundle_json STRING NOT NULL" in bp
    assert "created_at TIMESTAMP NOT NULL" in bp

    # visibility_scans fields
    vs = ddl_by_table[TABLE_VISIBILITY_SCANS]
    assert "scan_id STRING NOT NULL" in vs
    assert "batch_id STRING NOT NULL" in vs
    assert "project_id STRING NOT NULL" in vs
    assert "brand_id STRING NOT NULL" in vs
    assert "started_at TIMESTAMP NOT NULL" in vs
    assert "completed_at TIMESTAMP NOT NULL" in vs
    assert "status STRING NOT NULL" in vs

    # brand_observations fields
    bo = ddl_by_table[TABLE_BRAND_OBSERVATIONS]
    assert "scan_id STRING NOT NULL" in bo
    assert "role STRING NOT NULL" in bo
    assert "mentioned BOOL NOT NULL" in bo
    assert "mention_count INT64 NOT NULL" in bo
    assert "citation_urls ARRAY<STRING>" in bo
    assert "citation_domains ARRAY<STRING>" in bo

    # fanout_observations fields
    fo = ddl_by_table[TABLE_FANOUT_OBSERVATIONS]
    assert "task_id STRING NOT NULL" in fo
    assert "tool STRING NOT NULL" in fo
    assert "brand_found BOOL NOT NULL" in fo

    # citations fields
    cit = ddl_by_table[TABLE_CITATIONS]
    assert "url STRING NOT NULL" in cit
    assert "domain STRING NOT NULL" in cit
    assert "matched_brand_ids ARRAY<STRING>" in cit


def test_repository_locks_seed_dml() -> None:
    """2b. Verify repository_locks DDL and idempotent seed DML."""
    lock_ddl = get_repository_locks_ddl("my-project", "my_dataset")
    assert "CREATE TABLE IF NOT EXISTS `my-project.my_dataset.repository_locks`" in lock_ddl

    seed_dml = get_repository_locks_seed_dml("my-project", "my_dataset")
    assert "MERGE INTO `my-project.my_dataset.repository_locks`" in seed_dml
    assert LOCK_KEY_BUNDLE_WRITE in seed_dml
    assert "0 AS lock_version" in seed_dml

    seed_stmts = get_schema_seed_statements("my-project", "my_dataset")
    assert len(seed_stmts) == 1
    assert seed_stmts[0] == seed_dml


def test_fact_tables_are_partitioned() -> None:
    """3. Fact tables are partitioned by DATE(started_at) while control tables are unpartitioned."""
    statements = get_schema_ddl_statements("my-project", "my_dataset")
    ddl_by_table = {ALL_TABLES[i]: statements[i] for i in range(len(ALL_TABLES))}

    assert "PARTITION BY" not in ddl_by_table[TABLE_REPOSITORY_LOCKS]
    assert "PARTITION BY" not in ddl_by_table[TABLE_BUNDLE_PAYLOADS]

    for table in [
        TABLE_VISIBILITY_SCANS,
        TABLE_BRAND_OBSERVATIONS,
        TABLE_FANOUT_OBSERVATIONS,
        TABLE_CITATIONS,
    ]:
        assert "PARTITION BY DATE(started_at)" in ddl_by_table[table]


def test_required_clustering_is_present() -> None:
    """4. Clustering is configured correctly for all tables."""
    statements = get_schema_ddl_statements("my-project", "my_dataset")
    ddl_by_table = {ALL_TABLES[i]: statements[i] for i in range(len(ALL_TABLES))}

    vs_cluster = "CLUSTER BY project_id, brand_id, prompt_id, batch_id"
    bo_cluster = "CLUSTER BY brand_id, project_id, role, prompt_id"
    fo_cluster = "CLUSTER BY brand_id, project_id, tool, prompt_id"
    cit_cluster = "CLUSTER BY domain, project_id, source_type, prompt_id"

    assert "CLUSTER BY scan_id" in ddl_by_table[TABLE_BUNDLE_PAYLOADS]
    assert vs_cluster in ddl_by_table[TABLE_VISIBILITY_SCANS]
    assert bo_cluster in ddl_by_table[TABLE_BRAND_OBSERVATIONS]
    assert fo_cluster in ddl_by_table[TABLE_FANOUT_OBSERVATIONS]
    assert cit_cluster in ddl_by_table[TABLE_CITATIONS]


def test_require_partition_filter_is_true() -> None:
    """5. require_partition_filter is set to true on all partitioned fact tables."""
    statements = get_schema_ddl_statements("my-project", "my_dataset")
    ddl_by_table = {ALL_TABLES[i]: statements[i] for i in range(len(ALL_TABLES))}

    for table in [
        TABLE_VISIBILITY_SCANS,
        TABLE_BRAND_OBSERVATIONS,
        TABLE_FANOUT_OBSERVATIONS,
        TABLE_CITATIONS,
    ]:
        assert "require_partition_filter = true" in ddl_by_table[table]


def test_no_destructive_drop_or_replace() -> None:
    """6. DDL statements use CREATE TABLE IF NOT EXISTS without DROP or CREATE OR REPLACE."""
    statements = get_schema_ddl_statements("my-project", "my_dataset")
    for stmt in statements:
        assert "DROP" not in stmt.upper()
        assert "CREATE OR REPLACE" not in stmt.upper()
        assert stmt.startswith("CREATE TABLE IF NOT EXISTS")


def test_identifier_validation_accepts_valid_ids() -> None:
    """7. Valid project, dataset, and location tokens are accepted."""
    assert validate_project_id("my-gcp-project-123") == "my-gcp-project-123"
    assert validate_project_id("test-proj") == "test-proj"
    assert validate_project_id("p12345") == "p12345"

    assert validate_dataset_id("ai_search_journey_v3") == "ai_search_journey_v3"
    assert validate_dataset_id("dataset123") == "dataset123"

    assert validate_location("US") == "US"
    assert validate_location("EU") == "EU"
    assert validate_location("us-central1") == "us-central1"


def test_identifier_validation_rejects_injection_strings() -> None:
    """8. Identifier validation strictly rejects injection attempts, backticks, and spaces."""
    # Project ID injection / invalid characters
    with pytest.raises(InvalidIdentifierError):
        validate_project_id("proj`id")
    with pytest.raises(InvalidIdentifierError):
        validate_project_id("proj id")
    with pytest.raises(InvalidIdentifierError):
        validate_project_id("proj; DROP TABLE x;")
    with pytest.raises(InvalidIdentifierError):
        validate_project_id("project.with.dots")
    with pytest.raises(InvalidIdentifierError):
        validate_project_id("-starts-with-hyphen")
    with pytest.raises(InvalidIdentifierError):
        validate_project_id("ends-with-hyphen-")

    # Dataset ID injection / invalid characters
    with pytest.raises(InvalidIdentifierError):
        validate_dataset_id("data-set")  # hyphens forbidden in dataset id
    with pytest.raises(InvalidIdentifierError):
        validate_dataset_id("ds; DROP TABLE x;")
    with pytest.raises(InvalidIdentifierError):
        validate_dataset_id("ds`name")
    with pytest.raises(InvalidIdentifierError):
        validate_dataset_id("ds.name")
    with pytest.raises(InvalidIdentifierError):
        validate_dataset_id("ds name")

    # Location injection / invalid characters
    with pytest.raises(InvalidIdentifierError):
        validate_location("US; DROP TABLE x;")
    with pytest.raises(InvalidIdentifierError):
        validate_location("US `loc`")
    with pytest.raises(InvalidIdentifierError):
        validate_location("US region")


def test_setup_dry_run_makes_no_api_calls(capsys: pytest.CaptureFixture[str]) -> None:
    """9. Setup dry-run prints DDL and executes zero BigQuery API calls without credentials."""
    ret = setup_bigquery_schema("test-proj", "test_ds", location="US", dry_run=True, apply=False)
    assert ret == 0

    captured = capsys.readouterr()
    assert "=== BigQuery Schema Setup (DRY RUN) ===" in captured.out
    assert "test-proj.test_ds.repository_locks" in captured.out
    assert "test-proj.test_ds.bundle_payloads" in captured.out
    assert "test-proj.test_ds.visibility_scans" in captured.out
    assert "Generated Seed DML Statements:" in captured.out
    assert "--apply was not provided" in captured.out


# ======================================================================
# Serialization & Hashing Tests (10-13)
# ======================================================================


def test_canonical_serialization_is_deterministic() -> None:
    """10. Canonical serialization produces identical JSON across calls."""
    bundle = _make_test_bundle()
    s1 = serialize_bundle_canonically(bundle)
    s2 = serialize_bundle_canonically(bundle)
    assert s1 == s2
    assert '"scan_id":"scan_001"' in s1
    # Check compact whitespace (no space after colon/comma)
    assert '": "' not in s1
    assert '", "' not in s1


def test_hash_is_deterministic() -> None:
    """11. SHA-256 hash is completely deterministic for the same bundle."""
    bundle = _make_test_bundle()
    h1 = calculate_bundle_sha256(bundle)
    h2 = calculate_bundle_sha256(bundle)
    assert h1 == h2
    assert len(h1) == 64


def test_unicode_is_stable() -> None:
    """12. Unicode characters are preserved in UTF-8 without artificial ASCII escaping."""
    bundle = _make_test_bundle(brand_name="Café & Roastery ☕ 素晴らしい")
    canonical = serialize_bundle_canonically(bundle)
    assert "Café & Roastery ☕ 素晴らしい" in canonical
    assert "\\u" not in canonical  # ensure_ascii=False verified

    h1 = calculate_bundle_sha256(bundle)
    h2 = calculate_bundle_sha256(bundle)
    assert h1 == h2


def test_changed_payload_changes_hash() -> None:
    """13. Changing any attribute in the bundle produces a different SHA-256 hash."""
    b1 = _make_test_bundle(brand_name="Alpha")
    b2 = _make_test_bundle(brand_name="Beta")

    assert calculate_bundle_sha256(b1) != calculate_bundle_sha256(b2)


# ======================================================================
# Bootstrap Script Integration & Argument Validation Tests (14-17)
# ======================================================================


def test_bootstrap_script_help_flag() -> None:
    """14. Verify scripts/bootstrap_bigquery_v3.sh displays usage on --help."""
    import subprocess

    result = subprocess.run(
        ["./scripts/bootstrap_bigquery_v3.sh", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Usage: ./scripts/bootstrap_bigquery_v3.sh" in result.stdout
    assert "--project PROJECT_ID" in result.stdout
    assert "--dataset DATASET_ID" in result.stdout
    assert "--location LOCATION" in result.stdout
    assert "--apply" in result.stdout


def test_bootstrap_script_derives_project_or_accepts_override() -> None:
    """15. Verify bootstrap_bigquery_v3.sh prints resolved project and accepts overrides."""
    import subprocess

    # With explicit project override
    r1 = subprocess.run(
        [
            "./scripts/bootstrap_bigquery_v3.sh",
            "--project",
            "override-proj-123",
            "--dataset",
            "custom_ds",
            "--location",
            "EU",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r1.returncode == 0
    assert "Resolved Project:  override-proj-123 (explicit argument (--project))" in r1.stdout
    assert "Dataset ID:        custom_ds" in r1.stdout
    assert "Dataset Location:  EU" in r1.stdout

    # With default arguments (auto-derives from active gcloud config or env)
    r2 = subprocess.run(
        ["./scripts/bootstrap_bigquery_v3.sh"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r2.returncode == 0
    assert "Resolved Project:" in r2.stdout
    assert "Dataset ID:        ai_search_journey_v3" in r2.stdout
    assert "Dataset Location:  US" in r2.stdout
    assert "DRY RUN (Preview Only)" in r2.stdout


def test_bootstrap_script_rejects_empty_flag_values() -> None:
    """16. Verify scripts/bootstrap_bigquery_v3.sh rejects flags without explicit values."""
    import subprocess

    r = subprocess.run(
        [
            "./scripts/bootstrap_bigquery_v3.sh",
            "--project",
            "--dataset",
            "test_ds",
            "--location",
            "US",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode != 0
    assert "--project requires a non-empty PROJECT_ID" in r.stderr


def test_bootstrap_script_dry_run_execution() -> None:
    """17. Verify bootstrap_bigquery_v3.sh performs a safe dry run when --apply is omitted."""
    import subprocess

    result = subprocess.run(
        [
            "./scripts/bootstrap_bigquery_v3.sh",
            "--project",
            "my-dryrun-proj",
            "--dataset",
            "my_v3_ds",
            "--location",
            "US",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "[DRY RUN] Planned Actions:" in result.stdout
    assert "my-dryrun-proj.my_v3_ds.visibility_scans" in result.stdout
    assert "my-dryrun-proj.my_v3_ds.brand_observations" in result.stdout
    assert "my-dryrun-proj.my_v3_ds.fanout_observations" in result.stdout
    assert "my-dryrun-proj.my_v3_ds.citations" in result.stdout
    assert "my-dryrun-proj.my_v3_ds.bundle_payloads" in result.stdout
    assert "my-dryrun-proj.my_v3_ds.repository_locks" in result.stdout
    assert "--apply was not provided" in result.stdout
    assert "To execute these changes against BigQuery, re-run with --apply" in result.stdout
