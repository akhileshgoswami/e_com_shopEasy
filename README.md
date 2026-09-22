# ShopEasy — Production Flask E-Commerce Platform

A complete, production-oriented e-commerce web application: Flask + PostgreSQL backend, server-rendered Bootstrap 5 frontend, Razorpay payments (Standard Checkout + webhooks), Cash on Delivery, an admin panel, and a full Google Cloud Run / Cloud SQL / Cloud Storage deployment via Terraform.

---

## 1. Project overview

Customers browse categories → subcategories → products, search/filter, add to cart (login required), check out with COD or Razorpay, and track orders. Admins manage the full catalog, inventory, orders, payments, users, and coupons from a dedicated `/admin` panel.

## 2. Architecture

```
Browser
  │
  ▼
Cloud Run (Gunicorn + Flask)
  │
  ├── Cloud SQL (PostgreSQL, via Cloud SQL Auth Proxy / unix socket)
  ├── Cloud Storage (product/category images)
  ├── Secret Manager (DB password, Flask secret key, Razorpay keys)
  └── Razorpay API (Orders API, signature verification, webhooks)
```

Application layers:

- **Routes (blueprints)** — thin controllers: `app/auth`, `app/shop`, `app/cart`, `app/checkout`, `app/payments`, `app/admin`.
- **Services** — all business logic: `AuthenticationService`, `ProductService`, `CategoryService`, `CartService`, `CheckoutService`, `OrderService`, `InventoryService`, `RazorpayService`, `CouponService`, `EmailService`, `StorageService`.
- **Models** — SQLAlchemy models in `app/models/`.
- **Storage abstraction** — `LocalStorageService` (dev) / `GCSStorageService` (prod), selected by `GCS_ENABLED`.

## 3. Features

- Public catalog browsing (no login required): categories, subcategories, products, search, filters, sorting, pagination.
- Auth required for cart/checkout, with "add to cart" intent preserved through login/register.
- Database-backed cart with server-side price/stock recalculation on every view and at checkout — frontend prices/stock are never trusted.
- Checkout with COD or Razorpay, saved/new addresses, coupons.
- Razorpay Orders API integration, server-side signature verification, idempotent webhook processing, and stock reserve/release across the payment lifecycle.
- Full order lifecycle with status history (`pending_payment → placed → confirmed → processing → packed → shipped → delivered`, plus `cancelled/failed/returned/refunded`).
- Admin panel: dashboard stats, categories/subcategories/products CRUD with image upload, inventory management, order management + status transitions, payments view, user management, coupons, settings overview.
- Security: CSRF protection, bcrypt-style password hashing (Werkzeug), login throttling/lockout, secure cookies, security headers/CSP, IDOR-safe order/cart access, admin RBAC, upload validation (MIME + extension + re-encode via Pillow).
- SEO: slugs, meta tags, OpenGraph, JSON-LD product data, `robots.txt`, `sitemap.xml`.
- Structured logging, centralized error pages (404/403/429/500), `/health` endpoint.

## 4. Requirements

- Python 3.12+
- PostgreSQL 14+ (production/Docker) — SQLite is only used as a local dev/test convenience
- Docker + Docker Compose (recommended for local dev)
- A Razorpay account (test mode is fine) for payment testing
- For deployment: a GCP project, `gcloud` CLI, Terraform ≥ 1.5

## 5. Local setup (without Docker)

```bash
git clone <this-repo> && cd e-com
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env: at minimum set SECRET_KEY. DATABASE_URL defaults to SQLite if unset.

export FLASK_APP=wsgi.py
flask db upgrade          # applies migrations (creates dev.db if using SQLite)
flask seed-admin --email admin@example.com --password "ChangeMe123!"
flask seed-data            # optional: sample categories/subcategories/products

flask run                  # http://localhost:5000
```

> **Note on psycopg2 + very new Python versions:** `psycopg2-binary` does not always ship wheels for brand-new CPython releases. If `pip install` fails building `psycopg2-binary` locally, either use Python 3.12/3.13, install PostgreSQL headers (`brew install libpq`, then `export PATH="$(brew --prefix libpq)/bin:$PATH"` before `pip install`), or just use SQLite for local development — production always runs inside the Docker image on `python:3.12-slim`, where this is a non-issue.

> **Why is `setuptools<81` pinned in `requirements.txt`?** The `razorpay` SDK still imports `pkg_resources`, which recent `setuptools` releases (≥ 81) no longer ship. Without this pin, a fresh install can break `import razorpay` entirely.

## 6. Environment variables

See [`.env.example`](.env.example) for the full, categorized list (`APP`, `DATABASE`, `RAZORPAY`, `GOOGLE`, `EMAIL`, `SECURITY`). Key ones:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask session/CSRF signing key. **Required in production.** |
| `DATABASE_URL` | SQLAlchemy connection string. Must be PostgreSQL in production. |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | From the Razorpay dashboard. Secret never reaches the browser. |
| `RAZORPAY_WEBHOOK_SECRET` | Used to verify `X-Razorpay-Signature` on incoming webhooks. |
| `GCS_ENABLED` | `true` to use Google Cloud Storage for uploads; `false` uses local `app/static/uploads`. |
| `MAIL_ENABLED` | `false` (default) logs emails instead of sending — no SMTP needed for local dev. |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | Enables the "Continue with Google" button on login/register. Leave both blank to hide it. |

`ProductionConfig` fails fast at startup if `SECRET_KEY` or `DATABASE_URL` is missing, or if `DATABASE_URL` points at SQLite.

### "Sign in with Google" setup

1. [Google Cloud Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials) → **Create Credentials → OAuth client ID** → type **Web application**.
2. Authorized redirect URIs:
   - `http://localhost:5000/login/google/callback` (local, `flask run`)
   - `http://localhost:8000/login/google/callback` (local, `docker compose` / `projectrun.sh`)
   - `https://<your-domain>/login/google/callback` (production)
3. Copy the Client ID/Secret into `.env` as `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` (or, for Cloud Run, into `terraform.tfvars` as `google_oauth_client_id` / `google_oauth_client_secret`).
4. Restart the app. The button appears automatically on `/login` and `/register` once both values are set — no code changes needed.

New Google sign-ins are created as regular `customer` accounts and matched to an existing account by email **only if** Google reports that email as verified (prevents account takeover via an unverified address). They get an unusable random password under the hood, so the normal "forgot password" flow still works if the user later wants a password login too.

## 7. Database setup & migrations

Schema is managed exclusively with Flask-Migrate/Alembic — **never** `db.create_all()` in production.

```bash
flask db init        # only once, already committed to this repo under migrations/
flask db migrate -m "Describe your change"
flask db upgrade      # applies pending migrations
```

The initial migration (`migrations/versions/..._initial_schema.py`) was generated and applied against a real PostgreSQL 16 instance (via `docker compose`), not SQLite, so it's safe for production.

## 8. Running tests

```bash
source .venv/bin/activate
pip install -r requirements.txt
pytest -q                              # 48 tests: auth, RBAC, catalog CRUD, cart,
                                        # checkout/inventory transactions, Razorpay
                                        # order/verify/webhook (mocked), image validation
pytest -q --cov=app --cov-report=term-missing
```

Tests run against an in-memory SQLite database (`TestingConfig`) and mock the Razorpay SDK calls — no real Razorpay credentials or network access needed to run the suite.

## 9. Docker setup (recommended local workflow)

```bash
cp .env.example .env   # optional, docker-compose.yml has sane defaults for local use
docker compose build
docker compose up -d db
docker compose up -d web    # runs `flask db upgrade` automatically on container start, then gunicorn

curl http://localhost:8000/health
```

The app is served at **http://localhost:8000** (not 5000 — macOS reserves 5000 for AirPlay Receiver by default, which silently breaks `docker run -p 5000:...` on many Macs).

Seed data / admin user (one-off container run against the compose network):

```bash
docker compose run --rm web flask seed-admin --email admin@example.com --password "ChangeMe123!"
docker compose run --rm web flask seed-data
```

Then visit `http://localhost:8000/admin/login`.

## 10. Razorpay setup (test mode)

1. Create a free account at Razorpay, switch to **Test Mode**.
2. Dashboard → **Settings → API Keys** → generate a test Key ID/Secret. Put them in `.env` as `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET`.
3. Checkout flow: `POST /payment/razorpay/create-order` creates a Razorpay Order server-side from the **server-computed** order total (never the browser), then the Razorpay Checkout modal opens client-side with that `order_id`.
4. On completion, the browser posts the Razorpay response to `POST /payment/razorpay/verify`, which re-verifies the HMAC signature server-side using the secret (never exposed to the browser) before marking the order paid.
5. Use Razorpay's documented test card/UPI credentials to simulate success and failure.

### Webhook setup

1. Dashboard → **Settings → Webhooks** → **Add New Webhook**.
2. URL: `https://<your-domain-or-cloud-run-url>/webhooks/razorpay`
3. Active events: at minimum `payment.captured` and `payment.failed` (add `order.paid` if desired).
4. Copy the **Webhook Secret** into `RAZORPAY_WEBHOOK_SECRET`.
5. For local testing, use the Razorpay CLI or `ngrok`/`cloudflared` to tunnel `http://localhost:8000/webhooks/razorpay` to a public HTTPS URL and register that as the webhook endpoint.

Webhook processing is idempotent: each event is deduplicated by `X-Razorpay-Event-Id` (falling back to a body hash) in the `webhook_events` table, so retries never double-process a payment.

## 11–15. GCP / Terraform / Cloud Run / Cloud SQL / Cloud Storage / Secret Manager

> These sections describe the **cloud deployment path**. If you only need local testing, you can stop at section 10 — nothing below is required to run the app locally.

### One-time setup

```bash
gcloud auth login
gcloud auth application-default login
cd terraform
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars: project_id, bucket_name (must be globally unique), region, etc.
```

### Provision infrastructure

```bash
./scripts/setup_gcp.sh <PROJECT_ID> <REGION>
```

This enables the required APIs and runs `terraform init/plan/apply`, provisioning:

- Artifact Registry Docker repository
- Cloud SQL PostgreSQL 16 instance + database + user (random password, stored in Secret Manager)
- Cloud Storage bucket for product/category images (public read via IAM, not per-object ACLs — uniform bucket-level access)
- Secret Manager secrets: DB password, Flask `SECRET_KEY`, Razorpay Key ID/Secret/Webhook Secret
- A dedicated Cloud Run service account with least-privilege IAM (`cloudsql.client`, `storage.objectAdmin` scoped to the one bucket, `secretmanager.secretAccessor` scoped to the app's own secrets)
- A Cloud Run v2 service wired to Cloud SQL via the Auth Proxy volume mount and to all the above secrets — first created with a placeholder image

### Build, migrate, deploy

```bash
./scripts/deploy.sh <PROJECT_ID> <REGION> <ARTIFACT_REPO_NAME> <CLOUD_RUN_SERVICE_NAME>
```

This builds the image with Cloud Build, runs `flask db upgrade` as a **one-off Cloud Run Job** (never automatically inside the always-on web service, and never `db.create_all()`), deploys the new image to the Cloud Run service, and curls `/health`.

To re-run migrations only (e.g. after a hotfix without a full redeploy):

```bash
./scripts/migrate.sh <PROJECT_ID> <REGION> <CLOUD_SQL_CONNECTION_NAME>
```

### Seed an admin user in production

```bash
gcloud run jobs deploy ecom-seed-admin \
  --image=<the deployed image> --region=<REGION> --project=<PROJECT_ID> \
  --set-cloudsql-instances=<CONNECTION_NAME> \
  --set-secrets="SECRET_KEY=ecom-flask-secret-key:latest,DB_PASSWORD=ecom-db-password:latest" \
  --set-env-vars="FLASK_APP=wsgi.py,INSTANCE_CONNECTION_NAME=<CONNECTION_NAME>,DB_NAME=ecom_db,DB_USER=ecom_user" \
  --command="flask" --args="seed-admin,--email,admin@yourdomain.com" \
  --update-env-vars="SEED_ADMIN_PASSWORD=<a strong password>"
gcloud run jobs execute ecom-seed-admin --region=<REGION> --wait
```

(Never hardcode the password in source; pass it as a one-off env var on the job invocation, or store it as a Secret Manager secret referenced with `--set-secrets`.)

### Custom domain + HTTPS

```bash
gcloud run domain-mappings create --service=<SERVICE_NAME> --domain=shop.yourdomain.com --region=<REGION>
```

Cloud Run provisions and renews the TLS certificate automatically once your DNS `CNAME`/`A` records point at the given target. Update `BASE_URL` (Cloud Run env var / Terraform `base_url`) and your Razorpay webhook URL to the new domain afterward.

## 16. Connection pooling (Cloud Run + Cloud SQL)

Cloud Run can run many concurrent instances, each holding its own connection pool — configured conservatively in `app/config.py`:

```python
SQLALCHEMY_ENGINE_OPTIONS = {
    "pool_pre_ping": True,   # detect and replace stale connections
    "pool_size": 5,
    "max_overflow": 2,
    "pool_recycle": 1800,
    "pool_timeout": 30,
}
```

Tune `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_RECYCLE` / `DB_POOL_TIMEOUT` via env vars, and keep `pool_size × max Cloud Run instances` comfortably under your Cloud SQL tier's `max_connections`.

## 17. Production checklist

- [ ] `SECRET_KEY` set from Secret Manager, not a default/dev value
- [ ] `DATABASE_URL`/`INSTANCE_CONNECTION_NAME` point at Cloud SQL, not SQLite
- [ ] `flask db upgrade` run against production before first traffic (via `scripts/migrate.sh`, not `db.create_all()`)
- [ ] Razorpay **live** keys + **live** webhook secret set (test keys will silently fail live payments)
- [ ] Razorpay webhook URL registered and reachable over HTTPS
- [ ] `GCS_ENABLED=true` with the correct bucket name
- [ ] `SESSION_COOKIE_SECURE=true` (automatic under `ProductionConfig`)
- [ ] `flask seed-admin` run once to create a real admin account; demo `flask seed-data` **not** run in production
- [ ] Custom domain mapped, DNS propagated, TLS certificate issued
- [ ] `/health` returns 200 after deploy

## 18. Troubleshooting

- **`ModuleNotFoundError: No module named 'pkg_resources'` when importing `razorpay`** — your `setuptools` is ≥ 81. `pip install "setuptools<81"` (already pinned in `requirements.txt`; only bites you if you install packages outside of it).
- **`psycopg2-binary` fails to build locally** — see the note in section 5; use Docker or SQLite for local dev instead of fighting a local PostgreSQL toolchain.
- **`docker compose up` can't bind port 5000** — that's macOS's AirPlay Receiver. This repo maps the app to host port **8000** instead; if you changed it back to 5000, either rename the port or disable AirPlay Receiver in System Settings → General → AirDrop & Handoff.
- **Webhook signature verification fails** — confirm `RAZORPAY_WEBHOOK_SECRET` matches exactly what's shown in the Razorpay dashboard for that specific webhook endpoint (each webhook URL can have its own secret).
- **Orders stuck in `pending_payment`** — this is expected if a customer closes the Razorpay modal without completing payment; stock reserved for that order is released automatically when `/payment/razorpay/failed` fires (modal dismissed) or a `payment.failed` webhook arrives. Customers can also cancel a `pending_payment` order themselves from the order detail page.

---

## Local setup — quick reference

```bash
# Docker (recommended)
docker compose build
docker compose up -d db
docker compose up -d web
docker compose run --rm web flask seed-admin --email admin@example.com --password "ChangeMe123!"
docker compose run --rm web flask seed-data

# Tests
pytest -q

# Migrations (local, without Docker)
flask db upgrade
```

## GCP provisioning & deployment — quick reference

```bash
cd terraform && cp terraform.tfvars.example terraform.tfvars   # fill in values
cd ..
./scripts/setup_gcp.sh <PROJECT_ID> <REGION>
./scripts/deploy.sh <PROJECT_ID> <REGION> <ARTIFACT_REPO_NAME> <CLOUD_RUN_SERVICE_NAME>
./scripts/migrate.sh <PROJECT_ID> <REGION> <CLOUD_SQL_CONNECTION_NAME>   # re-run migrations only, if ever needed
```
