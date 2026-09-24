#!/usr/bin/env bash
# Deploy ShopEasy to Cloud Run, backed by Firestore in Datastore mode (NDB).
#
# One script, no Terraform. Every step is idempotent, so the first run
# provisions everything and later runs just ship a new revision.
#
# Usage:
#   ./scripts/deploy.sh                    provision (first time) + build + deploy
#   ./scripts/deploy.sh ship               build + deploy only (infra must exist; used by CI)
#   ./scripts/deploy.sh seed-admin EMAIL   create/promote an admin user in production
#   ./scripts/deploy.sh logs               show recent service logs
#   ./scripts/deploy.sh url                print the service URL
#
# Settings (env vars or a gitignored .env.deploy file next to this repo root):
#   PROJECT_ID  default e-com-509609
#   ACCOUNT     default akgileshgoswami@gmail.com (must appear in `gcloud auth list`)
#   REGION      default us-central1 (Cloud Run, Firestore and the upload bucket)
#   DB_LOCATION Firestore location, defaults to REGION; fixed once created
#   SERVICE     default ecom-web
#   BASE_URL    public URL used in emails/sitemap; defaults to the run.app URL
#
# Optional app secrets — stored in Secret Manager when set; re-run to rotate:
#   RAZORPAY_KEY_ID RAZORPAY_KEY_SECRET RAZORPAY_WEBHOOK_SECRET
#   GOOGLE_OAUTH_CLIENT_ID GOOGLE_OAUTH_CLIENT_SECRET MAIL_PASSWORD
# Email is enabled when MAIL_SERVER is set (plus MAIL_USERNAME, MAIL_DEFAULT_SENDER).
# SECRET_KEY is generated once automatically and never changes afterwards.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [ -f .env.deploy ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env.deploy
  set +a
fi

PROJECT_ID="${PROJECT_ID:-e-com-509609}"
ACCOUNT="${ACCOUNT:-akgileshgoswami@gmail.com}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-ecom-web}"

RUNTIME_SA="ecom-web@${PROJECT_ID}.iam.gserviceaccount.com"
BUILD_SA="ecom-builder@${PROJECT_ID}.iam.gserviceaccount.com"
BUCKET="${PROJECT_ID}-ecom-uploads"

# App env var -> Secret Manager secret name.
OPTIONAL_SECRETS=(
  RAZORPAY_KEY_ID RAZORPAY_KEY_SECRET RAZORPAY_WEBHOOK_SECRET
  GOOGLE_OAUTH_CLIENT_ID GOOGLE_OAUTH_CLIENT_SECRET MAIL_PASSWORD
)
secret_name() { echo "ecom-$(echo "$1" | tr '[:upper:]_' '[:lower:]-')"; }

# Pin account + project on every call so the global gcloud config is untouched.
gc() { gcloud --account="${ACCOUNT}" --project="${PROJECT_ID}" --quiet "$@"; }
log() { printf '\n==> %s\n' "$*"; }
die() { printf '\n!! %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------

preflight() {
  command -v gcloud >/dev/null || die "gcloud CLI not found. Install: https://cloud.google.com/sdk/docs/install"
  gcloud auth list --format='value(account)' | grep -qx "${ACCOUNT}" \
    || die "${ACCOUNT} is not logged in. Run: gcloud auth login ${ACCOUNT}"

  local billing
  billing="$(gc billing projects describe "${PROJECT_ID}" --format='value(billingEnabled)' 2>/dev/null || true)"
  case "${billing}" in
    True) ;;
    False) die "Billing is not enabled on ${PROJECT_ID} (Cloud Run needs it).
   Link a billing account: https://console.cloud.google.com/billing/linkedaccount?project=${PROJECT_ID}" ;;
    *) echo "(could not read billing status for ${PROJECT_ID}; continuing)" ;;
  esac
}

enable_apis() {
  log "Enabling APIs (no-op if already enabled)"
  gc services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    firestore.googleapis.com \
    datastore.googleapis.com \
    secretmanager.googleapis.com \
    storage.googleapis.com \
    iam.googleapis.com
}

ensure_database() {
  local db_type
  db_type="$(gc firestore databases describe --database='(default)' --format='value(type)' 2>/dev/null || true)"
  case "${db_type}" in
    DATASTORE_MODE) ;;
    "")
      log "Creating Firestore database in Datastore mode (${REGION})"
      gc firestore databases create --database='(default)' --location="${DB_LOCATION:-${REGION}}" --type=datastore-mode
      ;;
    *)
      die "The (default) Firestore database is ${db_type}; NDB needs Datastore mode.
   An empty database can be switched in the console: Firestore > (default) > Switch to Datastore mode."
      ;;
  esac
}

ensure_service_account() {
  local email="$1" name="${1%%@*}" display="$2"
  gc iam service-accounts describe "${email}" >/dev/null 2>&1 \
    || gc iam service-accounts create "${name}" --display-name="${display}"
}

grant_project_role() {
  gc projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:$1" --role="$2" --condition=None >/dev/null
}

ensure_identities() {
  log "Service accounts and roles"
  ensure_service_account "${RUNTIME_SA}" "ShopEasy Cloud Run runtime"
  ensure_service_account "${BUILD_SA}" "ShopEasy Cloud Build"
  # New service accounts can take a few seconds to become visible to IAM.
  for _ in 1 2 3 4 5; do
    grant_project_role "${RUNTIME_SA}" roles/datastore.user 2>/dev/null && break
    sleep 5
  done
  grant_project_role "${BUILD_SA}" roles/run.builder
}

ensure_bucket() {
  # Cloud Run's filesystem is wiped on every restart, so uploaded product
  # images/logos/banners must live in GCS.
  if ! gc storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1; then
    log "Creating upload bucket gs://${BUCKET}"
    gc storage buckets create "gs://${BUCKET}" --location="${REGION}" --uniform-bucket-level-access
  fi
  # Product images are served straight from storage.googleapis.com.
  gc storage buckets add-iam-policy-binding "gs://${BUCKET}" \
    --member=allUsers --role=roles/storage.objectViewer >/dev/null
  gc storage buckets add-iam-policy-binding "gs://${BUCKET}" \
    --member="serviceAccount:${RUNTIME_SA}" --role=roles/storage.objectAdmin >/dev/null
}

secret_exists() { gc secrets describe "$1" >/dev/null 2>&1; }

# put_secret NAME VALUE — create the secret, or add a version if the value
# changed, and let the runtime service account read it.
put_secret() {
  local name="$1" value="$2"
  if ! secret_exists "${name}"; then
    printf '%s' "${value}" | gc secrets create "${name}" --replication-policy=automatic --data-file=- >/dev/null
  elif [ "$(gc secrets versions access latest --secret="${name}" 2>/dev/null || true)" != "${value}" ]; then
    printf '%s' "${value}" | gc secrets versions add "${name}" --data-file=- >/dev/null
  fi
  gc secrets add-iam-policy-binding "${name}" \
    --member="serviceAccount:${RUNTIME_SA}" --role=roles/secretmanager.secretAccessor >/dev/null
}

ensure_secrets() {
  log "Secrets"
  # Generated once; rotating it would log every user out.
  secret_exists ecom-secret-key \
    || put_secret ecom-secret-key "$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

  local var
  for var in "${OPTIONAL_SECRETS[@]}"; do
    if [ -n "${!var:-}" ]; then
      put_secret "$(secret_name "${var}")" "${!var}"
    fi
  done
}

# --set-secrets value: SECRET_KEY plus whichever optional secrets exist.
secrets_flag() {
  local flag="SECRET_KEY=ecom-secret-key:latest" var name
  for var in "${OPTIONAL_SECRETS[@]}"; do
    name="$(secret_name "${var}")"
    if secret_exists "${name}"; then
      flag="${flag},${var}=${name}:latest"
    fi
  done
  echo "${flag}"
}

service_url() {
  # Cloud Run's deterministic URL: https://SERVICE-PROJECT_NUMBER.REGION.run.app
  local number
  number="$(gc projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
  echo "https://${SERVICE}-${number}.${REGION}.run.app"
}

deploy() {
  local url env_vars
  url="$(service_url)"
  BASE_URL="${BASE_URL:-${url}}"

  env_vars="FLASK_ENV=production"
  env_vars+=",GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
  env_vars+=",BASE_URL=${BASE_URL}"
  env_vars+=",GCS_ENABLED=true,GCS_BUCKET_NAME=${BUCKET}"
  if [ -n "${MAIL_SERVER:-}" ]; then
    env_vars+=",MAIL_ENABLED=true,MAIL_SERVER=${MAIL_SERVER},MAIL_USERNAME=${MAIL_USERNAME:-apikey}"
    env_vars+=",MAIL_DEFAULT_SENDER=${MAIL_DEFAULT_SENDER:-no-reply@example.com}"
  fi

  log "Building from source and deploying ${SERVICE} to ${REGION} (takes a few minutes)"
  gc run deploy "${SERVICE}" \
    --source=. \
    --region="${REGION}" \
    --service-account="${RUNTIME_SA}" \
    --build-service-account="projects/${PROJECT_ID}/serviceAccounts/${BUILD_SA}" \
    --allow-unauthenticated \
    --memory=512Mi \
    --cpu=1 \
    --min-instances=0 \
    --max-instances=2 \
    --set-env-vars="${env_vars}" \
    --set-secrets="$(secrets_flag)"

  log "Health check: ${url}/health"
  if curl -fsS --retry 5 --retry-delay 3 "${url}/health"; then
    printf '\n\nDeployed: %s\n' "${url}"
    printf 'Admin panel: %s/admin/login  (create one with: %s seed-admin you@example.com)\n' "${url}" "$0"
  else
    die "Health check failed. Inspect logs with: $0 logs"
  fi
}

seed_admin() {
  local email="${1:?Usage: $0 seed-admin EMAIL}" password confirm image
  image="$(gc run services describe "${SERVICE}" --region="${REGION}" \
    --format='value(spec.template.spec.containers[0].image)' 2>/dev/null || true)"
  [ -n "${image}" ] || die "Service ${SERVICE} not deployed yet. Run $0 first."

  read -r -s -p "Password for ${email} (min 8 chars): " password; echo
  read -r -s -p "Confirm password: " confirm; echo
  [ "${password}" = "${confirm}" ] || die "Passwords do not match."
  [ "${#password}" -ge 8 ] || die "Password must be at least 8 characters."

  # The password reaches the one-off job through a short-lived secret, so it
  # never shows up in job config or logs.
  put_secret ecom-seed-admin-password "${password}"
  trap 'gc secrets delete ecom-seed-admin-password >/dev/null 2>&1 || true' EXIT

  log "Running seed-admin job with the deployed image"
  gc run jobs deploy ecom-seed-admin \
    --image="${image}" \
    --region="${REGION}" \
    --service-account="${RUNTIME_SA}" \
    --set-env-vars="FLASK_APP=wsgi.py,FLASK_ENV=production,GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
    --set-secrets="SECRET_KEY=ecom-secret-key:latest,SEED_ADMIN_PASSWORD=ecom-seed-admin-password:latest" \
    --command=flask \
    --args="seed-admin,--email,${email}" \
    --max-retries=0 \
    --task-timeout=300
  gc run jobs execute ecom-seed-admin --region="${REGION}" --wait
  printf '\nAdmin ready: %s/admin/login\n' "$(service_url)"
}

# ---------------------------------------------------------------------------

CMD="${1:-deploy}"
case "${CMD}" in
  deploy)
    preflight
    enable_apis
    ensure_database
    ensure_identities
    ensure_bucket
    ensure_secrets
    deploy
    ;;
  ship)
    preflight
    deploy
    ;;
  seed-admin)
    preflight
    seed_admin "${2:-}"
    ;;
  logs)
    gc run services logs read "${SERVICE}" --region="${REGION}" --limit=100
    ;;
  url)
    service_url
    ;;
  *)
    die "Unknown command '${CMD}'. See the usage notes at the top of $0."
    ;;
esac
