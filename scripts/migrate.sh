#!/usr/bin/env bash
# Run `flask db upgrade` against Cloud SQL as a standalone Cloud Run Job.
# Useful for re-running migrations without a full deploy (e.g. after a
# hotfix migration was added to an already-deployed image).
#
# Usage:
#   ./scripts/migrate.sh <PROJECT_ID> <REGION> <CLOUD_SQL_CONNECTION_NAME> [IMAGE]
#
# If IMAGE is omitted, it defaults to the image currently deployed on the
# Cloud Run service named in terraform output (cloud_run_service_name).

set -euo pipefail

PROJECT_ID="${1:?Usage: $0 <PROJECT_ID> <REGION> <CLOUD_SQL_CONNECTION_NAME> [IMAGE]}"
REGION="${2:?Usage: $0 <PROJECT_ID> <REGION> <CLOUD_SQL_CONNECTION_NAME> [IMAGE]}"
CONNECTION_NAME="${3:?Usage: $0 <PROJECT_ID> <REGION> <CLOUD_SQL_CONNECTION_NAME> [IMAGE]}"
IMAGE="${4:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="${SCRIPT_DIR}/../terraform"

cd "${TERRAFORM_DIR}"
BUCKET_NAME="$(terraform output -raw gcs_bucket_name)"
SERVICE_ACCOUNT="$(terraform output -raw cloud_run_service_account_email)"
SERVICE_NAME="$(terraform output -raw cloud_run_service_name)"

if [ -z "${IMAGE}" ]; then
  IMAGE="$(gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --project="${PROJECT_ID}" --format='value(spec.template.spec.containers[0].image)')"
fi

SECRETS="SECRET_KEY=ecom-flask-secret-key:latest,DB_PASSWORD=ecom-db-password:latest,RAZORPAY_KEY_ID=ecom-razorpay-key-id:latest,RAZORPAY_KEY_SECRET=ecom-razorpay-key-secret:latest,RAZORPAY_WEBHOOK_SECRET=ecom-razorpay-webhook-secret:latest"

echo "==> Running flask db upgrade using image: ${IMAGE}"
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

echo "==> Migration complete."
