#!/usr/bin/env bash
# Build, push, migrate, and deploy the app to Cloud Run.
#
# Usage:
#   ./scripts/deploy.sh <PROJECT_ID> <REGION> <ARTIFACT_REPO_NAME> <CLOUD_RUN_SERVICE_NAME>
#
# Reads Cloud SQL / bucket / secret names from `terraform output`, so run
# scripts/setup_gcp.sh (or `terraform apply`) first.

set -euo pipefail

PROJECT_ID="${1:?Usage: $0 <PROJECT_ID> <REGION> <ARTIFACT_REPO_NAME> <CLOUD_RUN_SERVICE_NAME>}"
REGION="${2:?Usage: $0 <PROJECT_ID> <REGION> <ARTIFACT_REPO_NAME> <CLOUD_RUN_SERVICE_NAME>}"
REPO_NAME="${3:?Usage: $0 <PROJECT_ID> <REGION> <ARTIFACT_REPO_NAME> <CLOUD_RUN_SERVICE_NAME>}"
SERVICE_NAME="${4:?Usage: $0 <PROJECT_ID> <REGION> <ARTIFACT_REPO_NAME> <CLOUD_RUN_SERVICE_NAME>}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TERRAFORM_DIR="${ROOT_DIR}/terraform"

TAG="$(git -C "${ROOT_DIR}" rev-parse --short HEAD 2>/dev/null || date +%Y%m%d%H%M%S)"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/ecom-web:${TAG}"

echo "==> Reading infrastructure details from terraform output"
cd "${TERRAFORM_DIR}"
CONNECTION_NAME="$(terraform output -raw cloud_sql_connection_name)"
BUCKET_NAME="$(terraform output -raw gcs_bucket_name)"
SERVICE_ACCOUNT="$(terraform output -raw cloud_run_service_account_email)"
cd "${ROOT_DIR}"

SECRETS="SECRET_KEY=ecom-flask-secret-key:latest,DB_PASSWORD=ecom-db-password:latest,RAZORPAY_KEY_ID=ecom-razorpay-key-id:latest,RAZORPAY_KEY_SECRET=ecom-razorpay-key-secret:latest,RAZORPAY_WEBHOOK_SECRET=ecom-razorpay-webhook-secret:latest"

echo "==> Building image ${IMAGE}"
gcloud builds submit --tag "${IMAGE}" --project "${PROJECT_ID}" .

echo "==> Running database migrations as a one-off Cloud Run Job"
gcloud run jobs deploy ecom-migrate \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --service-account="${SERVICE_ACCOUNT}" \
  --set-cloudsql-instances="${CONNECTION_NAME}" \
  --set-env-vars="FLASK_APP=wsgi.py,FLASK_ENV=production,INSTANCE_CONNECTION_NAME=${CONNECTION_NAME},DB_NAME=ecom_db,DB_USER=ecom_user,GCS_BUCKET_NAME=${BUCKET_NAME},GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
  --set-secrets="${SECRETS}" \
  --command="flask" \
  --args="db,upgrade" \
  --max-retries=0 \
  --task-timeout=300

gcloud run jobs execute ecom-migrate --region="${REGION}" --project="${PROJECT_ID}" --wait

echo "==> Deploying image to Cloud Run service ${SERVICE_NAME}"
gcloud run deploy "${SERVICE_NAME}" \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --platform=managed \
  --quiet

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --project="${PROJECT_ID}" --format='value(status.url)')"

echo "==> Health check: ${SERVICE_URL}/health"
if curl -fsS "${SERVICE_URL}/health" >/dev/null; then
  echo "Deployment healthy: ${SERVICE_URL}"
else
  echo "!! Health check failed. Check Cloud Run logs:"
  echo "   gcloud run services logs read ${SERVICE_NAME} --region=${REGION} --project=${PROJECT_ID}"
  exit 1
fi
