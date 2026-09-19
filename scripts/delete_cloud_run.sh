#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Safe Cleanup Script for AI Search Journey Lab on Google Cloud Run
# Deletes Cloud Run service and application images from Artifact Registry.
# Preserves Artifact Registry repo, Secret Manager secrets, and Service Account.
# ==============================================================================

PROJECT_ID="${PROJECT_ID:-ai-search-journey-lab}"
REGION="${REGION:-us-central1}"
REPOSITORY="${REPOSITORY:-ai-search-journey}"
SERVICE="${SERVICE:-ai-search-journey-lab}"
IMAGE_NAME="${IMAGE_NAME:-ai-search-journey-lab}"

AUTO_CONFIRM=false
if [[ "${1:-}" == "--yes" || "${1:-}" == "-y" ]]; then
  AUTO_CONFIRM=true
fi

echo "======================================================================"
echo "⚠️  AI Search Journey Lab — Cloud Run Cleanup"
echo "Project:          ${PROJECT_ID}"
echo "Region:           ${REGION}"
echo "Service:          ${SERVICE}"
echo "Artifact Repo:    ${REPOSITORY}"
echo "Image Name:       ${IMAGE_NAME}"
echo "======================================================================"
echo ""
echo "This will delete:"
echo "  1. Cloud Run service: '${SERVICE}' in '${REGION}'"
echo "  2. Container image tags for: '${IMAGE_NAME}' in repository '${REPOSITORY}'"
echo ""
echo "It will PRESERVE:"
echo "  - Artifact Registry repository '${REPOSITORY}'"
echo "  - Secret Manager secrets & versions"
echo "  - Service Account & IAM permissions"
echo "  - Enabled GCP APIs"
echo ""

# 1. Verify required CLI tools
command -v gcloud >/dev/null 2>&1 || { echo "❌ ERROR: gcloud CLI is required but not installed."; exit 1; }

# 2. Confirmation prompt
if [[ "${AUTO_CONFIRM}" != "true" ]]; then
  read -r -p "Are you sure you want to proceed with cleanup? (y/N): " CONFIRMATION
  if [[ ! "${CONFIRMATION}" =~ ^[Yy]$ ]]; then
    echo "❌ Cleanup aborted by user."
    exit 0
  fi
fi

# 3. Verify GCP Project
echo "⚙️ Setting active GCP project to '${PROJECT_ID}'..."
gcloud config set project "${PROJECT_ID}" --quiet

# 4. Delete Cloud Run Service
echo "☁️ Checking Cloud Run service '${SERVICE}' in '${REGION}'..."
if gcloud run services describe "${SERVICE}" --region="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "Deleting Cloud Run service '${SERVICE}'..."
  gcloud run services delete "${SERVICE}" \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --quiet
  echo "✓ Cloud Run service '${SERVICE}' deleted."
else
  echo "ℹ️ Cloud Run service '${SERVICE}' does not exist (skipping)."
fi

# 5. Delete Container Images from Artifact Registry
IMAGE_PACKAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}"
echo "🐳 Checking container images in '${IMAGE_PACKAGE}'..."

if gcloud artifacts docker images list "${IMAGE_PACKAGE}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  IMAGE_COUNT="$(gcloud artifacts docker images list "${IMAGE_PACKAGE}" --project="${PROJECT_ID}" --format="value(IMAGE)" 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "${IMAGE_COUNT}" -gt 0 ]]; then
    echo "Deleting ${IMAGE_COUNT} container image(s) under '${IMAGE_PACKAGE}'..."
    gcloud artifacts docker images delete "${IMAGE_PACKAGE}" \
      --project="${PROJECT_ID}" \
      --delete-tags \
      --quiet
    echo "✓ Container images under '${IMAGE_PACKAGE}' deleted."
  else
    echo "ℹ️ No images found under '${IMAGE_PACKAGE}' (skipping)."
  fi
else
  echo "ℹ️ No container package found for '${IMAGE_PACKAGE}' (skipping)."
fi

echo ""
echo "======================================================================"
echo "✅ Cleanup complete."
echo ""
echo "Redeploy with:"
echo "./scripts/deploy_cloud_run.sh"
echo "======================================================================"
echo ""
