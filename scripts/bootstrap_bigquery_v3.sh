#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# BigQuery Bootstrap Workflow for AI Visibility (V3)
#
# Idempotent and safe:
# - Derives default GCP project from `gcloud config get-value project`
# - Prints resolved project clearly before any action
# - Accepts optional --project override
# - Requires --dataset and --location (or defaults from config)
# - Dry-run by default unless --apply is passed
# - On --apply: enables API, verifies ADC & library, sets up tables, verifies
# - Prints the exact non-secret .env configuration block
# ==============================================================================

PROJECT_ID=""
DATASET_ID="ai_search_journey_v3"
LOCATION="US"
APPLY=false

usage() {
  cat <<EOF
Usage: $0 [--project PROJECT_ID] [--dataset DATASET_ID] [--location LOCATION] [--apply]

Arguments:
  --project PROJECT_ID   Google Cloud Project ID (optional; defaults to active gcloud project)
  --dataset DATASET_ID   BigQuery Dataset ID (default: ai_search_journey_v3)
  --location LOCATION    BigQuery Dataset Location (default: US)
  --apply                Execute real cloud mutations (enables API, creates dataset/tables)
  -h, --help             Show this help message

Without --apply, this script performs a dry-run and prints planned actions only.
EOF
}

# 1. Parse Command Line Arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      if [[ -z "${2:-}" || "${2:-}" == --* ]]; then
        echo "❌ ERROR: --project requires a non-empty PROJECT_ID argument." >&2
        exit 1
      fi
      PROJECT_ID="$2"
      shift 2
      ;;
    --dataset)
      if [[ -z "${2:-}" || "${2:-}" == --* ]]; then
        echo "❌ ERROR: --dataset requires a non-empty DATASET_ID argument." >&2
        exit 1
      fi
      DATASET_ID="$2"
      shift 2
      ;;
    --location)
      if [[ -z "${2:-}" || "${2:-}" == --* ]]; then
        echo "❌ ERROR: --location requires a non-empty LOCATION argument." >&2
        exit 1
      fi
      LOCATION="$2"
      shift 2
      ;;
    --apply)
      APPLY=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "❌ ERROR: Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

# 2. Derive Project ID if not explicitly supplied
PROJECT_SOURCE="explicit argument (--project)"
if [[ -z "${PROJECT_ID}" ]]; then
  if command -v gcloud >/dev/null 2>&1; then
    ACTIVE_GCLOUD_PROJ="$(gcloud config get-value project 2>/dev/null || true)"
    if [[ -n "${ACTIVE_GCLOUD_PROJ}" && "${ACTIVE_GCLOUD_PROJ}" != "(unset)" ]]; then
      PROJECT_ID="${ACTIVE_GCLOUD_PROJ}"
      PROJECT_SOURCE="gcloud config get-value project"
    fi
  fi
fi

# If still unset, check environment variables before failing
if [[ -z "${PROJECT_ID}" ]]; then
  if [[ -n "${BIGQUERY_PROJECT:-}" ]]; then
    PROJECT_ID="${BIGQUERY_PROJECT}"
    PROJECT_SOURCE="BIGQUERY_PROJECT environment variable"
  elif [[ -n "${GOOGLE_CLOUD_PROJECT:-}" ]]; then
    PROJECT_ID="${GOOGLE_CLOUD_PROJECT}"
    PROJECT_SOURCE="GOOGLE_CLOUD_PROJECT environment variable"
  fi
fi

if [[ -z "${PROJECT_ID}" ]]; then
  echo "❌ ERROR: Could not resolve a Google Cloud project ID." >&2
  echo "   Please supply --project PROJECT_ID or set active project via: gcloud config set project PROJECT_ID" >&2
  usage >&2
  exit 1
fi

# Locate Python runtime (.venv or current python3)
PYTHON_CMD="python3"
if [[ -f "./.venv/bin/python" ]]; then
  PYTHON_CMD="./.venv/bin/python"
elif [[ -f "../.venv/bin/python" ]]; then
  PYTHON_CMD="../.venv/bin/python"
fi

echo "======================================================================"
echo "📊 AI Search Journey Lab — BigQuery Bootstrap (V3)"
echo "Resolved Project:  ${PROJECT_ID} (${PROJECT_SOURCE})"
echo "Dataset ID:        ${DATASET_ID}"
echo "Dataset Location:  ${LOCATION}"
echo "Execution Mode:    $([[ "${APPLY}" == "true" ]] && echo "APPLY (Real Execution)" || echo "DRY RUN (Preview Only)")"
echo "======================================================================"

# ==============================================================================
# DRY RUN MODE (Default when --apply is omitted)
# ==============================================================================
if [[ "${APPLY}" != "true" ]]; then
  echo ""
  echo "🔍 [DRY RUN] Planned Actions:"
  echo "  1. Verify gcloud authentication status for project '${PROJECT_ID}'."
  echo "  2. Enable BigQuery API ('bigquery.googleapis.com') on project '${PROJECT_ID}'."
  echo "  3. Verify Application Default Credentials (ADC) availability."
  echo "  4. Verify Python 'google-cloud-bigquery' package in runtime environment."
  echo "  5. Execute schema DDL & seed locks for '${PROJECT_ID}.${DATASET_ID}' (${LOCATION})."
  echo "  6. Verify tables exist:"
  echo "       - ${PROJECT_ID}.${DATASET_ID}.visibility_scans"
  echo "       - ${PROJECT_ID}.${DATASET_ID}.brand_observations"
  echo "       - ${PROJECT_ID}.${DATASET_ID}.fanout_observations"
  echo "       - ${PROJECT_ID}.${DATASET_ID}.citations"
  echo "       - ${PROJECT_ID}.${DATASET_ID}.bundle_payloads"
  echo "       - ${PROJECT_ID}.${DATASET_ID}.repository_locks"
  echo "  7. Output non-secret .env configuration block for Streamlit app."
  echo ""
  echo "Previewing BigQuery schema statements (dry run):"
  BIGQUERY_PROJECT="${PROJECT_ID}" \
  BIGQUERY_DATASET="${DATASET_ID}" \
  BIGQUERY_LOCATION="${LOCATION}" \
  ${PYTHON_CMD} scripts/setup_bigquery_v3.py \
    --project="${PROJECT_ID}" \
    --dataset="${DATASET_ID}" \
    --location="${LOCATION}" \
    --dry-run
  echo ""
  echo "ℹ️  To execute these changes against BigQuery, re-run with --apply:"
  echo "   $0 --project ${PROJECT_ID} --dataset ${DATASET_ID} --location ${LOCATION} --apply"
  echo "   (or simply: $0 --apply)"
  exit 0
fi

# ==============================================================================
# APPLY MODE
# ==============================================================================

# 1. Verify gcloud CLI and authentication
echo "🔍 1. Verifying gcloud CLI and authentication..."
if ! command -v gcloud >/dev/null 2>&1; then
  echo "❌ ERROR: 'gcloud' CLI is required but not installed or not in PATH." >&2
  echo "   Please install the Google Cloud SDK: https://cloud.google.com/sdk/docs/install" >&2
  exit 1
fi

AUTH_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null || true)"
if [[ -z "${AUTH_ACCOUNT}" ]]; then
  echo "❌ ERROR: No active authenticated account found in gcloud." >&2
  echo "   Please log in with: gcloud auth login" >&2
  exit 1
fi
echo "✓ gcloud authenticated as: ${AUTH_ACCOUNT}"
echo "✓ Target project confirmed: ${PROJECT_ID}"

# 2. Enable BigQuery API
echo "📦 2. Enabling BigQuery API (bigquery.googleapis.com) on project '${PROJECT_ID}'..."
if ! gcloud services enable bigquery.googleapis.com --project="${PROJECT_ID}"; then
  echo "❌ ERROR: Failed to enable 'bigquery.googleapis.com' for project '${PROJECT_ID}'." >&2
  echo "   Please verify that:" >&2
  echo "   - Project '${PROJECT_ID}' exists and billing is enabled." >&2
  echo "   - Account '${AUTH_ACCOUNT}' has 'Service Usage Admin' or 'Owner/Editor' role on project '${PROJECT_ID}'." >&2
  exit 1
fi
echo "✓ BigQuery API enabled on project '${PROJECT_ID}'."

# 3. Verify Application Default Credentials (ADC)
echo "🔑 3. Checking Application Default Credentials (ADC)..."
ADC_CHECK="$(${PYTHON_CMD} -c "
import google.auth
try:
    credentials, project = google.auth.default()
    print('OK')
except Exception as e:
    print('FAIL: ' + str(e))
" 2>/dev/null || echo "FAIL")"

if [[ "${ADC_CHECK}" != "OK"* ]]; then
  echo "❌ ERROR: Google Cloud Application Default Credentials (ADC) are not configured." >&2
  echo "   Please run the following command to authenticate ADC:" >&2
  echo ""
  echo "       gcloud auth application-default login" >&2
  echo ""
  exit 1
fi
echo "✓ Application Default Credentials (ADC) are available."

# 4. Verify Python google-cloud-bigquery is installed
echo "🐍 4. Verifying Python google-cloud-bigquery library..."
if ! ${PYTHON_CMD} -c "import google.cloud.bigquery" >/dev/null 2>&1; then
  echo "❌ ERROR: Python library 'google-cloud-bigquery' is not installed in the environment." >&2
  echo "   Please install dependencies using pip:" >&2
  echo ""
  echo "       pip install -e \".[bigquery]\"" >&2
  echo "       # or: pip install google-cloud-bigquery" >&2
  echo ""
  exit 1
fi
echo "✓ google-cloud-bigquery library is installed."

# 5. Execute schema setup via scripts/setup_bigquery_v3.py --apply
echo "🚀 5. Creating BigQuery dataset and applying schema DDL/seeds..."
BIGQUERY_PROJECT="${PROJECT_ID}" \
BIGQUERY_DATASET="${DATASET_ID}" \
BIGQUERY_LOCATION="${LOCATION}" \
${PYTHON_CMD} scripts/setup_bigquery_v3.py \
  --project="${PROJECT_ID}" \
  --dataset="${DATASET_ID}" \
  --location="${LOCATION}" \
  --apply

# 6. Verify all expected V3 tables exist
echo "🔎 6. Verifying expected V3 tables exist in '${PROJECT_ID}.${DATASET_ID}'..."
EXPECTED_TABLES=(
  "visibility_scans"
  "brand_observations"
  "fanout_observations"
  "citations"
  "bundle_payloads"
  "repository_locks"
)

VERIFY_SCRIPT="
import sys
from google.cloud import bigquery

client = bigquery.Client(project='${PROJECT_ID}', location='${LOCATION}')
dataset_ref = bigquery.DatasetReference('${PROJECT_ID}', '${DATASET_ID}')
tables = {t.table_id for t in client.list_tables(dataset_ref)}

expected_list = ['${EXPECTED_TABLES[0]}', '${EXPECTED_TABLES[1]}', '${EXPECTED_TABLES[2]}', '${EXPECTED_TABLES[3]}', '${EXPECTED_TABLES[4]}', '${EXPECTED_TABLES[5]}']
missing = [t for t in expected_list if t not in tables]

if missing:
    print('MISSING: ' + ', '.join(missing), file=sys.stderr)
    sys.exit(1)
print('ALL_PRESENT')
"

if ! ${PYTHON_CMD} -c "${VERIFY_SCRIPT}" 2>/dev/null; then
  echo "❌ ERROR: Not all expected V3 tables were found in '${PROJECT_ID}.${DATASET_ID}'." >&2
  exit 1
fi

for tbl in "${EXPECTED_TABLES[@]}"; do
  echo "  ✓ Table '${PROJECT_ID}.${DATASET_ID}.${tbl}' exists"
done

# 7. Output Non-Secret .env Configuration Block
echo ""
echo "======================================================================"
echo "✅ BigQuery Bootstrap Completed Successfully!"
echo "======================================================================"
echo ""
echo "To enable BigQuery persistence in the Streamlit app, add or update the"
echo "following non-secret settings in your local .env file (or deployment env):"
echo ""
echo "# --- AI Visibility (V3) BigQuery Settings ---"
echo "BIGQUERY_PROJECT=\"${PROJECT_ID}\""
echo "BIGQUERY_DATASET=\"${DATASET_ID}\""
echo "BIGQUERY_LOCATION=\"${LOCATION}\""
echo "# --------------------------------------------"
echo ""
echo "Note: The bootstrap script does not overwrite your .env file."
echo ""
