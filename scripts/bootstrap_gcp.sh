#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Bootstrap GCP Environment for AI Search Journey Lab
# One-time setup: APIs, Artifact Registry, Service Account, and Secret Manager
# ==============================================================================

PROJECT_ID="${PROJECT_ID:-ai-search-journey-lab}"
REGION="${REGION:-us-central1}"
REPOSITORY="${REPOSITORY:-ai-search-journey}"
SERVICE_ACCOUNT_NAME="${SERVICE_ACCOUNT_NAME:-ai-search-journey-runner}"

echo "======================================================================"
echo "🚀 Bootstrapping GCP Environment for AI Search Journey Lab"
echo "Project:          ${PROJECT_ID}"
echo "Region:           ${REGION}"
echo "Artifact Repo:    ${REPOSITORY}"
echo "Service Account:  ${SERVICE_ACCOUNT_NAME}"
echo "======================================================================"

# 1. Verify required CLI tools
command -v gcloud >/dev/null 2>&1 || { echo "❌ ERROR: gcloud CLI is required but not installed."; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "❌ ERROR: docker is required but not installed."; exit 1; }

# 2. Set GCP active project
echo "⚙️ Setting active GCP project to '${PROJECT_ID}'..."
gcloud config set project "${PROJECT_ID}" --quiet

# 3. Enable required GCP APIs
echo "📦 Enabling required GCP APIs..."
gcloud services enable \
  artifactregistry.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  places.googleapis.com \
  --project="${PROJECT_ID}"

# 4. Create Artifact Registry Docker repository if missing
echo "🐳 Checking Artifact Registry repository '${REPOSITORY}' in '${REGION}'..."
if ! gcloud artifacts repositories describe "${REPOSITORY}" --location="${REGION}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "Creating Artifact Registry repository '${REPOSITORY}'..."
  gcloud artifacts repositories create "${REPOSITORY}" \
    --repository-format=docker \
    --location="${REGION}" \
    --description="Docker repository for AI Search Journey Lab" \
    --project="${PROJECT_ID}"
else
  echo "✓ Artifact Registry repository '${REPOSITORY}' already exists."
fi

# 5. Configure Docker authentication for Artifact Registry
echo "🔑 Configuring Docker authentication for ${REGION}-docker.pkg.dev..."
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# 6. Create runtime service account if missing
SA_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
echo "👤 Checking runtime service account '${SA_EMAIL}'..."
if ! gcloud iam service-accounts describe "${SA_EMAIL}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  echo "Creating service account '${SERVICE_ACCOUNT_NAME}'..."
  gcloud iam service-accounts create "${SERVICE_ACCOUNT_NAME}" \
    --display-name="AI Search Journey Cloud Run Runner" \
    --project="${PROJECT_ID}"
else
  echo "✓ Service account '${SERVICE_ACCOUNT_NAME}' already exists."
fi

# 7. Create Secret Manager secrets if missing
SECRETS=("gemini-api-key" "google-maps-api-key")

for SECRET_NAME in "${SECRETS[@]}"; do
  echo "🔒 Checking secret '${SECRET_NAME}'..."
  if ! gcloud secrets describe "${SECRET_NAME}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    echo "Creating secret '${SECRET_NAME}' in Secret Manager..."
    gcloud secrets create "${SECRET_NAME}" \
      --replication-policy="automatic" \
      --project="${PROJECT_ID}"
  else
    echo "✓ Secret '${SECRET_NAME}' already exists."
  fi

  # 8. Grant runtime service account accessor permission on the secret
  echo "Granting secretAccessor role to '${SA_EMAIL}' on secret '${SECRET_NAME}'..."
  gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" \
    --project="${PROJECT_ID}" \
    --quiet >/dev/null
done

echo ""
echo "======================================================================"
echo "✅ GCP Bootstrap Completed Successfully!"
echo "======================================================================"
echo ""
echo "👉 NEXT STEPS (if secret values have not been added yet):"
echo ""
echo "1. Add your Gemini API key to Secret Manager:"
echo "   echo -n \"YOUR_GEMINI_API_KEY\" | gcloud secrets versions add gemini-api-key --data-file=- --project=${PROJECT_ID}"
echo ""
echo "2. Add your Google Maps API key to Secret Manager:"
echo "   echo -n \"YOUR_GOOGLE_MAPS_API_KEY\" | gcloud secrets versions add google-maps-api-key --data-file=- --project=${PROJECT_ID}"
echo ""
echo "3. Deploy to Cloud Run:"
echo "   ./scripts/deploy_cloud_run.sh"
echo ""
