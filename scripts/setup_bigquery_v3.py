"""BigQuery schema setup script for AI Visibility (V3 Milestone 4).

Explicit command-line execution only. Never runs on import.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Sequence

from ai_search_journey.config import settings
from ai_search_journey.visibility.bigquery_repository import (
    BigQueryDependencyError,
    _get_bigquery_module,
)
from ai_search_journey.visibility.bigquery_schema import (
    ALL_TABLES,
    TABLE_REPOSITORY_LOCKS,
    get_schema_ddl_statements,
    get_schema_seed_statements,
    validate_dataset_id,
    validate_location,
    validate_project_id,
)


def setup_bigquery_schema(
    project_id: str,
    dataset_id: str = "ai_search_journey_v3",
    location: str = "US",
    *,
    dry_run: bool = False,
    apply: bool = False,
) -> int:
    """Validate identifiers, print or apply BigQuery schema DDL statements."""
    proj = validate_project_id(project_id)
    ds = validate_dataset_id(dataset_id)
    loc = validate_location(location)

    ddl_statements = get_schema_ddl_statements(proj, ds)
    seed_statements = get_schema_seed_statements(proj, ds)

    if not apply or dry_run:
        print("=== BigQuery Schema Setup (DRY RUN) ===")
        print(f"Project  : {proj}")
        print(f"Dataset  : {ds}")
        print(f"Location : {loc}")
        print(f"Tables   : {', '.join(ALL_TABLES)}\n")
        print("Generated DDL Statements:")
        for idx, stmt in enumerate(ddl_statements, 1):
            print(f"\n--- Statement {idx} ---")
            print(stmt)
        print("\nGenerated Seed DML Statements:")
        for idx, stmt in enumerate(seed_statements, 1):
            print(f"\n--- Seed Statement {idx} ---")
            print(stmt)
        if not apply:
            print("\n[INFO] Real changes refused because --apply was not provided.")
        return 0

    # Real execution requires --apply
    bq = _get_bigquery_module()
    if bq is None:
        raise BigQueryDependencyError(
            "google-cloud-bigquery is required to run setup_bigquery_v3.py --apply. "
            'Install with: pip install -e ".[bigquery]"'
        )

    print("=== Applying BigQuery Schema Setup ===")
    print(f"Project  : {proj}")
    print(f"Dataset  : {ds}")
    print(f"Location : {loc}")

    client = bq.Client(project=proj, location=loc)

    # 1. Create dataset if absent
    dataset_ref = bq.DatasetReference(proj, ds)
    dataset = bq.Dataset(dataset_ref)
    dataset.location = loc
    client.create_dataset(dataset, exists_ok=True)
    print(f"[OK] Dataset `{proj}.{ds}` ensured in location {loc}.")

    # 2. Apply all DDL statements
    for table_name, ddl in zip(ALL_TABLES, ddl_statements, strict=True):
        print(f"[APPLYING] Table `{proj}.{ds}.{table_name}`...")
        query_job = client.query(ddl)
        query_job.result()
        print(f"[OK] Table `{proj}.{ds}.{table_name}` ready.")

    # 3. Apply seed DML statements
    for seed_dml in seed_statements:
        print("[APPLYING] Seeding control tables...")
        seed_job = client.query(seed_dml)
        seed_job.result()
        print(f"[OK] Seed row ensured in `{proj}.{ds}.{TABLE_REPOSITORY_LOCKS}`.")

    print(
        f"\n[SUCCESS] All {len(ALL_TABLES)} tables and seeds successfully "
        f"configured in `{proj}.{ds}`."
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Initialize or preview BigQuery schema for AI Visibility V3."
    )
    default_proj = (
        settings.bigquery_project
        or os.environ.get("BIGQUERY_PROJECT")
        or os.environ.get("GOOGLE_CLOUD_PROJECT")
    )
    parser.add_argument(
        "--project",
        default=default_proj,
        help="Google Cloud project ID (default: from settings/environment)",
    )
    parser.add_argument(
        "--dataset",
        default=settings.bigquery_dataset,
        help="BigQuery dataset ID (default: %(default)s)",
    )
    parser.add_argument(
        "--location",
        default=settings.bigquery_location,
        help="BigQuery dataset location (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview DDL statements without making API calls",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Explicit confirmation required to execute real changes against BigQuery",
    )

    args = parser.parse_args(argv)

    if not args.project:
        parser.error(
            "--project is required (or set BIGQUERY_PROJECT / "
            "GOOGLE_CLOUD_PROJECT environment variable)"
        )

    try:
        return setup_bigquery_schema(
            project_id=args.project,
            dataset_id=args.dataset,
            location=args.location,
            dry_run=args.dry_run,
            apply=args.apply,
        )
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
