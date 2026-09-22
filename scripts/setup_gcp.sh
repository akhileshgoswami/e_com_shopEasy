#!/usr/bin/env bash
# One-time GCP project bootstrap + Terraform provisioning.
#
# Usage:
#   ./scripts/setup_gcp.sh <PROJECT_ID> <REGION>
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (`gcloud auth login`)
#   - terraform >= 1.5 installed
#   - terraform/terraform.tfvars created from terraform.tfvars.example

set -euo pipefail

PROJECT_ID="${1:?Usage: $0 <PROJECT_ID> <REGION>}"
REGION="${2:?Usage: $0 <PROJECT_ID> <REGION>}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TERRAFORM_DIR="${SCRIPT_DIR}/../terraform"

echo "==> Setting active gcloud project to ${PROJECT_ID}"
gcloud config set project "${PROJECT_ID}"

echo "==> Enabling required Google Cloud APIs"
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  storage.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  iam.googleapis.com \
  --project="${PROJECT_ID}"

if [ ! -f "${TERRAFORM_DIR}/terraform.tfvars" ]; then
  echo "!! terraform/terraform.tfvars not found."
  echo "   Copy terraform/terraform.tfvars.example to terraform/terraform.tfvars"
  echo "   and fill in project_id, bucket_name, etc. before continuing."
  exit 1
fi

echo "==> Running terraform init"
cd "${TERRAFORM_DIR}"
terraform init

echo "==> Running terraform plan"
terraform plan -out=tfplan

read -r -p "Apply this plan? [y/N] " CONFIRM
if [[ "${CONFIRM}" =~ ^[Yy]$ ]]; then
  terraform apply tfplan
  echo "==> Provisioning complete. Outputs:"
  terraform output
else
  echo "Aborted. No infrastructure changes were made."
fi

rm -f tfplan

echo ""
echo "Next steps:"
echo "  1. Build & push the app image, then deploy it to Cloud Run:"
echo "     ./scripts/deploy.sh ${PROJECT_ID} ${REGION} <artifact_repo_name> <cloud_run_service_name>"
echo "  2. Run database migrations against Cloud SQL:"
echo "     ./scripts/migrate.sh ${PROJECT_ID} ${REGION} <cloud_sql_connection_name>"
