"""BigQuery table schemas, identifier safety, and canonical serialization (V3 Milestone 4)."""

from __future__ import annotations

import hashlib
import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_search_journey.visibility.models import VisibilityScanBundle

# ======================================================================
# Fixed Internal Table Name Constants
# ======================================================================

TABLE_REPOSITORY_LOCKS = "repository_locks"
TABLE_BUNDLE_PAYLOADS = "bundle_payloads"
TABLE_VISIBILITY_SCANS = "visibility_scans"
TABLE_BRAND_OBSERVATIONS = "brand_observations"
TABLE_FANOUT_OBSERVATIONS = "fanout_observations"
TABLE_CITATIONS = "citations"

LOCK_KEY_BUNDLE_WRITE = "visibility_bundle_write"

ALL_TABLES: tuple[str, ...] = (
    TABLE_REPOSITORY_LOCKS,
    TABLE_BUNDLE_PAYLOADS,
    TABLE_VISIBILITY_SCANS,
    TABLE_BRAND_OBSERVATIONS,
    TABLE_FANOUT_OBSERVATIONS,
    TABLE_CITATIONS,
)

# ======================================================================
# Identifier Safety and Validation
# ======================================================================

_PROJECT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][-a-zA-Z0-9]{0,62}$")
_DATASET_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_]{1,1024}$")
_LOCATION_PATTERN = re.compile(r"^[a-zA-Z0-9][-a-zA-Z0-9_]{0,62}$")


class InvalidIdentifierError(ValueError):
    """Raised when a Google Cloud or BigQuery identifier fails safety validation."""


def validate_project_id(project_id: str) -> str:
    """Validate Google Cloud project ID.

    Permits letters, numbers, and hyphens.
    Rejects spaces, dots, backticks, semicolons, hyphens at ends, and SQL fragments.
    """
    if not isinstance(project_id, str) or not project_id.strip():
        raise InvalidIdentifierError("project_id cannot be empty or blank")

    p = project_id.strip()
    if p.endswith("-") or not _PROJECT_ID_PATTERN.fullmatch(p):
        raise InvalidIdentifierError(
            f"Invalid project_id '{project_id}'. Must contain only letters, numbers, "
            f"and hyphens, cannot end with a hyphen, and cannot contain dots, backticks, or SQL."
        )
    return p


def validate_dataset_id(dataset_id: str) -> str:
    """Validate BigQuery dataset ID.

    Permits letters, numbers, and underscores only.
    Rejects hyphens, spaces, dots, backticks, semicolons, and SQL fragments.
    """
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        raise InvalidIdentifierError("dataset_id cannot be empty or blank")

    d = dataset_id.strip()
    if not _DATASET_ID_PATTERN.fullmatch(d):
        raise InvalidIdentifierError(
            f"Invalid dataset_id '{dataset_id}'. Must contain only letters, numbers, "
            f"and underscores. Hyphens, dots, spaces, backticks, and SQL fragments are forbidden."
        )
    return d


def validate_location(location: str) -> str:
    """Validate BigQuery dataset location token.

    Permits letters, numbers, hyphens, and underscores.
    Rejects whitespace, backticks, semicolons, and SQL fragments.
    """
    if not isinstance(location, str) or not location.strip():
        raise InvalidIdentifierError("location cannot be empty or blank")

    loc = location.strip()
    if not _LOCATION_PATTERN.fullmatch(loc):
        raise InvalidIdentifierError(
            f"Invalid location '{location}'. Must be a valid BigQuery location token."
        )
    return loc


# ======================================================================
# Canonical Serialization and Hashing
# ======================================================================


def serialize_bundle_canonically(bundle: VisibilityScanBundle) -> str:
    """Produce deterministic, key-sorted, compact UTF-8 JSON representation."""
    dumped = bundle.model_dump(mode="json", exclude_none=False, by_alias=True)
    return json.dumps(dumped, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def calculate_bundle_sha256(bundle: VisibilityScanBundle) -> str:
    """Calculate SHA-256 hex digest of canonical bundle JSON without network access."""
    canonical_json = serialize_bundle_canonically(bundle)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


# ======================================================================
# DDL Generation
# ======================================================================


def get_repository_locks_ddl(project_id: str, dataset_id: str) -> str:
    """Return DDL for unpartitioned repository_locks serialization control table."""
    proj = validate_project_id(project_id)
    ds = validate_dataset_id(dataset_id)
    return f"""CREATE TABLE IF NOT EXISTS `{proj}.{ds}.{TABLE_REPOSITORY_LOCKS}` (
  lock_key STRING NOT NULL,
  lock_version INT64 NOT NULL
);"""


def get_repository_locks_seed_dml(project_id: str, dataset_id: str) -> str:
    """Return idempotent seed DML for repository_locks table."""
    proj = validate_project_id(project_id)
    ds = validate_dataset_id(dataset_id)
    return f"""MERGE INTO `{proj}.{ds}.{TABLE_REPOSITORY_LOCKS}` AS target
USING (SELECT '{LOCK_KEY_BUNDLE_WRITE}' AS lock_key, 0 AS lock_version) AS source
ON target.lock_key = source.lock_key
WHEN NOT MATCHED THEN
  INSERT (lock_key, lock_version) VALUES (source.lock_key, source.lock_version);"""


def get_bundle_payloads_ddl(project_id: str, dataset_id: str) -> str:
    """Return DDL for unpartitioned control/payload table."""
    proj = validate_project_id(project_id)
    ds = validate_dataset_id(dataset_id)
    return f"""CREATE TABLE IF NOT EXISTS `{proj}.{ds}.{TABLE_BUNDLE_PAYLOADS}` (
  scan_id STRING NOT NULL,
  payload_sha256 STRING NOT NULL,
  bundle_json STRING NOT NULL,
  created_at TIMESTAMP NOT NULL
)
CLUSTER BY scan_id;"""


def get_visibility_scans_ddl(project_id: str, dataset_id: str) -> str:
    """Return DDL for partitioned visibility_scans fact table."""
    proj = validate_project_id(project_id)
    ds = validate_dataset_id(dataset_id)
    return f"""CREATE TABLE IF NOT EXISTS `{proj}.{ds}.{TABLE_VISIBILITY_SCANS}` (
  scan_id STRING NOT NULL,
  batch_id STRING NOT NULL,
  project_id STRING NOT NULL,
  brand_id STRING NOT NULL,
  brand_name_snapshot STRING NOT NULL,
  brand_domain_snapshot STRING,
  prompt_id STRING NOT NULL,
  prompt_text_snapshot STRING NOT NULL,
  model_name STRING NOT NULL,
  location_snapshot STRING,
  started_at TIMESTAMP NOT NULL,
  completed_at TIMESTAMP NOT NULL,
  status STRING NOT NULL,
  duration_seconds FLOAT64,
  error_code STRING,
  error_message STRING
)
PARTITION BY DATE(started_at)
CLUSTER BY project_id, brand_id, prompt_id, batch_id
OPTIONS (
  require_partition_filter = true
);"""


def get_brand_observations_ddl(project_id: str, dataset_id: str) -> str:
    """Return DDL for partitioned brand_observations fact table."""
    proj = validate_project_id(project_id)
    ds = validate_dataset_id(dataset_id)
    return f"""CREATE TABLE IF NOT EXISTS `{proj}.{ds}.{TABLE_BRAND_OBSERVATIONS}` (
  scan_id STRING NOT NULL,
  project_id STRING NOT NULL,
  prompt_id STRING NOT NULL,
  started_at TIMESTAMP NOT NULL,
  brand_id STRING NOT NULL,
  role STRING NOT NULL,
  mentioned BOOL NOT NULL,
  mention_count INT64 NOT NULL,
  first_mention_position INT64,
  retrieved BOOL NOT NULL,
  best_retrieval_position INT64,
  recommended BOOL NOT NULL,
  recommendation_position INT64,
  cited BOOL NOT NULL,
  citation_urls ARRAY<STRING>,
  citation_domains ARRAY<STRING>
)
PARTITION BY DATE(started_at)
CLUSTER BY brand_id, project_id, role, prompt_id
OPTIONS (
  require_partition_filter = true
);"""


def get_fanout_observations_ddl(project_id: str, dataset_id: str) -> str:
    """Return DDL for partitioned fanout_observations fact table."""
    proj = validate_project_id(project_id)
    ds = validate_dataset_id(dataset_id)
    return f"""CREATE TABLE IF NOT EXISTS `{proj}.{ds}.{TABLE_FANOUT_OBSERVATIONS}` (
  scan_id STRING NOT NULL,
  project_id STRING NOT NULL,
  prompt_id STRING NOT NULL,
  started_at TIMESTAMP NOT NULL,
  task_id STRING NOT NULL,
  query_text STRING NOT NULL,
  tool STRING NOT NULL,
  brand_id STRING NOT NULL,
  brand_found BOOL NOT NULL,
  position_in_task INT64
)
PARTITION BY DATE(started_at)
CLUSTER BY brand_id, project_id, tool, prompt_id
OPTIONS (
  require_partition_filter = true
);"""


def get_citations_ddl(project_id: str, dataset_id: str) -> str:
    """Return DDL for partitioned citations fact table."""
    proj = validate_project_id(project_id)
    ds = validate_dataset_id(dataset_id)
    return f"""CREATE TABLE IF NOT EXISTS `{proj}.{ds}.{TABLE_CITATIONS}` (
  scan_id STRING NOT NULL,
  project_id STRING NOT NULL,
  prompt_id STRING NOT NULL,
  started_at TIMESTAMP NOT NULL,
  url STRING NOT NULL,
  domain STRING NOT NULL,
  source_type STRING NOT NULL,
  matched_brand_ids ARRAY<STRING>
)
PARTITION BY DATE(started_at)
CLUSTER BY domain, project_id, source_type, prompt_id
OPTIONS (
  require_partition_filter = true
);"""


def get_schema_ddl_statements(project_id: str, dataset_id: str) -> list[str]:
    """Return ordered list of DDL creation statements for all BigQuery visibility tables."""
    return [
        get_repository_locks_ddl(project_id, dataset_id),
        get_bundle_payloads_ddl(project_id, dataset_id),
        get_visibility_scans_ddl(project_id, dataset_id),
        get_brand_observations_ddl(project_id, dataset_id),
        get_fanout_observations_ddl(project_id, dataset_id),
        get_citations_ddl(project_id, dataset_id),
    ]


def get_schema_seed_statements(project_id: str, dataset_id: str) -> list[str]:
    """Return ordered list of idempotent DML seed statements for control tables."""
    return [
        get_repository_locks_seed_dml(project_id, dataset_id),
    ]
