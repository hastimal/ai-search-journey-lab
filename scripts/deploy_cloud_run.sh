#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Deploy AI Search Journey Lab to Google Cloud Run
# Builds multi-arch / linux/amd64 Docker image, pushes to Artifact Registry,
# deploys to Cloud Run with Secret Manager mounting, and verifies health.
# ==============================================================================

PROJECT_ID="${PROJECT_ID:-ai-search-journey-lab}"
REGION="${REGION:-us-central1}"
REPOSITORY="${REPOSITORY:-ai-search-journey}"
SERVICE="${SERVICE:-ai-search-journey-lab}"
IMAGE_NAME="${IMAGE_NAME:-ai-search-journey-lab}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-ai-search-journey-runner}"

BIGQUERY_PROJECT="${BIGQUERY_PROJECT:-ai-search-journey-lab}"
BIGQUERY_DATASET="${BIGQUERY_DATASET:-ai_search_journey_v3}"
BIGQUERY_LOCATION="${BIGQUERY_LOCATION:-US}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-3.6-flash}"

# 1. Verify required CLI tools
command -v gcloud >/dev/null 2>&1 || { echo "❌ ERROR: gcloud CLI is required but not installed."; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "❌ ERROR: docker is required but not installed."; exit 1; }

# 2. Determine unique image tag
if git rev-parse --short HEAD >/dev/null 2>&1; then
  GIT_SHA="$(git rev-parse --short HEAD)"
  IMAGE_TAG="${GIT_SHA}"
else
  IMAGE_TAG="$(date +%Y%m%d%H%M%S)"
fi

IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:${IMAGE_TAG}"
LATEST_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:latest"
SA_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "======================================================================"
echo "🚀 Deploying AI Search Journey Lab to Google Cloud Run"
echo "Project:          ${PROJECT_ID}"
echo "Region:           ${REGION}"
echo "Service:          ${SERVICE}"
echo "Image URI:        ${IMAGE_URI}"
echo "Service Account:  ${SA_EMAIL}"
echo "======================================================================"

# 3. Configure Docker auth for Artifact Registry
echo "🔑 Ensuring Docker authentication is configured..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# 4. Build and Push linux/amd64 image using Docker Buildx
echo "🐳 Building and pushing container image for linux/amd64..."
docker buildx build \
  --platform linux/amd64 \
  -t "${IMAGE_URI}" \
  -t "${LATEST_URI}" \
  --push \
  .

# 5. Deploy to Google Cloud Run
echo "☁️ Deploying service '${SERVICE}' to Cloud Run..."
gcloud run deploy "${SERVICE}" \
  --image="${IMAGE_URI}" \
  --platform=managed \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --port=8080 \
  --memory=2Gi \
  --cpu=2 \
  --timeout=300 \
  --service-account="${SA_EMAIL}" \
  --set-env-vars="BIGQUERY_PROJECT=${BIGQUERY_PROJECT},BIGQUERY_DATASET=${BIGQUERY_DATASET},BIGQUERY_LOCATION=${BIGQUERY_LOCATION},GEMINI_MODEL=${GEMINI_MODEL}" \
  --set-secrets="GEMINI_API_KEY=gemini-api-key:latest,GOOGLE_MAPS_API_KEY=google-maps-api-key:latest" \
  --allow-unauthenticated \
  --quiet

# 6. Retrieve deployed revision and service URL
REVISION="$(gcloud run services describe "${SERVICE}" --region="${REGION}" --project="${PROJECT_ID}" --format='value(status.latestReadyRevisionName)')"
SERVICE_URL="$(gcloud run services describe "${SERVICE}" --region="${REGION}" --project="${PROJECT_ID}" --format='value(status.url)')"

echo ""
echo "======================================================================"
echo "🎉 Deployment Successful!"
echo "Service Name:     ${SERVICE}"
echo "Latest Revision:  ${REVISION}"
echo "Service URL:      ${SERVICE_URL}"
echo "======================================================================"

# 7. Run health check against deployed service
echo "🩺 Verifying service health at ${SERVICE_URL}/_stcore/health..."
HEALTH_RESPONSE="$(curl -fsS --max-time 15 "${SERVICE_URL}/_stcore/health" || true)"

if [[ "${HEALTH_RESPONSE}" == "ok" ]]; then
  echo "✓ Service Health Check PASSED: status is OK"
else
  echo "❌ Service Health Check FAILED! Response: '${HEALTH_RESPONSE}'"
  exit 1
fi

echo ""
echo "🔗 Open the app: ${SERVICE_URL}"
echo ""
