# ShopEasy — Production Flask E-Commerce Platform

A complete, production-oriented e-commerce web application: Flask backend on Firestore in Datastore mode (via `google-cloud-ndb`), server-rendered Bootstrap 5 frontend, Razorpay payments (Standard Checkout + webhooks), Cash on Delivery, an admin panel, and a one-command Google Cloud Run deployment (`scripts/deploy.sh`).

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
  ├── Firestore in Datastore mode (google-cloud-ndb)
  ├── Cloud Storage (product/category images)
  ├── Secret Manager (Flask secret key, Razorpay/OAuth/mail secrets)
  └── Razorpay API (Orders API, signature verification, webhooks)
```

Application layers:

- **Routes (blueprints)** — thin controllers: `app/auth`, `app/shop`, `app/cart`, `app/checkout`, `app/payments`, `app/admin`.
- **Services** — all business logic: `AuthenticationService`, `ProductService`, `CategoryService`, `CartService`, `CheckoutService`, `OrderService`, `InventoryService`, `RazorpayService`, `CouponService`, `EmailService`, `StorageService`.
- **Models** — NDB models in `app/models/` (integer ids, money stored as exact integer paise via `DecimalProperty`). Queries use only equality filters and sort/filter/paginate in Python, so **no composite indexes (`index.yaml`) are needed**. Stock-changing operations (checkout, cancellations) run in NDB transactions.
- **Storage abstraction** — `LocalStorageService` (dev) / `GCSStorageService` (prod), selected by `GCS_ENABLED`.

## 3. Features

- Public catalog browsing (no login required): categories, subcategories, products, search, filters, sorting, pagination.
- Auth required for cart/checkout, with "add to cart" intent preserved through login/register.
- Database-backed cart with server-side price/stock recalculation on every view and at checkout — frontend prices/stock are never trusted.
- Checkout with COD or Razorpay, saved/new addresses, coupons.
- Razorpay Orders API integration, server-side signature verification, idempotent webhook processing, and stock reserve/release across the payment lifecycle.
- Full order lifecycle with status history (`pending_payment → placed → confirmed → processing → packed → shipped → out_for_delivery → delivered`, plus `cancelled/failed/returned/refunded`), with optional tracking number/link and estimated delivery date.
- Forgot-password / reset-password flow: single-use, hashed, 30-minute reset links; per-IP and per-account rate limits; "password changed" confirmation; all other sessions signed out on a password change.
- Transactional emails (HTML + plain text, store branding): order confirmation, owner new-order alert, order status updates (incl. cancelled/delivered), payment received, welcome, password reset/changed — idempotent and retryable via an email outbox (see [Email notifications](#15-email-notifications)).
- Admin panel: dashboard stats, categories/subcategories/products CRUD with image upload, inventory management, order management + status transitions, payments view, user management, coupons, settings overview.
- Security: CSRF protection, bcrypt-style password hashing (Werkzeug), login throttling/lockout, secure cookies, security headers/CSP, IDOR-safe order/cart access, admin RBAC, upload validation (MIME + extension + re-encode via Pillow).
- SEO: slugs, meta tags, OpenGraph, JSON-LD product data, `robots.txt`, `sitemap.xml`.
- Structured logging, centralized error pages (404/403/429/500), `/health` endpoint.

## 4. Requirements

- Python 3.12+
- Datastore emulator for local dev/tests: `gcloud components install beta cloud-datastore-emulator` (needs Java), or just use Docker Compose
- Docker + Docker Compose (recommended for local dev)
- A Razorpay account (test mode is fine) for payment testing
- For deployment: a GCP project with billing enabled and the `gcloud` CLI

## 5. Local setup (without Docker)

```bash
git clone <this-repo> && cd e-com
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env       # points the app at the emulator on localhost:8081

# In another terminal:
gcloud beta emulators datastore start --consistency=1.0 --project=e-com-local

export FLASK_APP=wsgi.py
flask seed-admin --email admin@example.com --password "ChangeMe123!"
flask seed-data            # optional: sample categories/subcategories/products

flask run                  # http://localhost:5000
```

> **Why is `setuptools<81` pinned in `requirements.txt`?** The `razorpay` SDK still imports `pkg_resources`, which recent `setuptools` releases (≥ 81) no longer ship. Without this pin, a fresh install can break `import razorpay` entirely.

## 6. Environment variables

See [`.env.example`](.env.example) for the full, categorized list (`APP`, `DATABASE`, `RAZORPAY`, `GOOGLE`, `EMAIL`, `SECURITY`). Key ones:

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask session/CSRF signing key. **Required in production.** |
| `DATASTORE_EMULATOR_HOST` / `DATASTORE_PROJECT_ID` | Local only: point NDB at the Datastore emulator. Unset on Cloud Run. |
| `GOOGLE_CLOUD_PROJECT` | GCP project whose Datastore is used in production (set by `scripts/deploy.sh`). |
| `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` | From the Razorpay dashboard. Secret never reaches the browser. |
| `RAZORPAY_WEBHOOK_SECRET` | Used to verify `X-Razorpay-Signature` on incoming webhooks. |
| `GCS_ENABLED` | `true` to use Google Cloud Storage for uploads; `false` uses local `app/static/uploads`. |
| `BASE_URL` | Public URL of the site (e.g. `https://yourdomain.com`). Every email link — reset links, "View order", admin links — is built from it. |
| `MAIL_SERVER` / `MAIL_PORT` / `MAIL_USE_TLS` / `MAIL_USE_SSL` | SMTP server. `587` + `MAIL_USE_TLS=true` (STARTTLS) or `465` + `MAIL_USE_SSL=true`. Certificates are always verified. |
| `MAIL_USERNAME` / `MAIL_PASSWORD` / `MAIL_DEFAULT_SENDER` | SMTP login and the From address. Keep `MAIL_PASSWORD` in Secret Manager in production. |
| `MAIL_ENABLED` | Defaults to `true` when `MAIL_SERVER` is set. `false` logs emails instead of sending — no SMTP needed for local dev. |
| `OWNER_EMAIL` | Who receives new-order alerts. Several addresses: separate with `;`. |
| `PASSWORD_RESET_TOKEN_EXPIRY_MINUTES` | Reset-link lifetime (default `30`). `PASSWORD_RESET_MAX_PER_HOUR` caps reset emails per account (default `3`). |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | Enables the "Continue with Google" button on login/register. Leave both blank to hide it. |

`ProductionConfig` fails fast at startup if `SECRET_KEY` is missing.

### "Sign in with Google" setup

1. [Google Cloud Console → APIs & Services → Credentials](https://console.cloud.google.com/apis/credentials) → **Create Credentials → OAuth client ID** → type **Web application**.
2. Authorized redirect URIs:
   - `http://localhost:5000/login/google/callback` (local, `flask run`)
   - `http://localhost:8000/login/google/callback` (local, `docker compose` / `projectrun.sh`)
   - `https://<your-domain>/login/google/callback` (production)
3. Copy the Client ID/Secret into `.env` as `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` (or, for Cloud Run, set them in `.env.deploy` and re-run `./scripts/deploy.sh`).
4. Restart the app. The button appears automatically on `/login` and `/register` once both values are set — no code changes needed.

New Google sign-ins are created as regular `customer` accounts and matched to an existing account by email **only if** Google reports that email as verified (prevents account takeover via an unverified address). They get an unusable random password under the hood, so the normal "forgot password" flow still works if the user later wants a password login too.

## 7. Database

Firestore in Datastore mode is schemaless — there are no migrations. Adding a property to a model is backwards compatible (old entities read the default); renaming/removing one needs a small backfill script. The production database is created by `scripts/deploy.sh` on first run.

The email/password-reset features added these, none of which need a migration or backfill:

| Kind / property | Notes |
|---|---|
| `PasswordResetToken` (new kind) | Entity id = SHA-256 of the emailed token (the token itself is never stored); `user_id`, `expires_at`, `used_at`, `superseded`. Rows older than a day are deleted on the account's next reset request. |
| `EmailOutbox` (new kind) | Entity id = idempotency key such as `order_confirmation:<order id>`; `kind`, `status` (`sending`/`sent`/`failed`), `payload` (ids only), `attempts`, `last_error`, timestamps. |
| `User.session_version`, `User.password_changed_at` | Bumped/set on password change; existing users default to `0`/empty and keep their sessions. |
| `Order.tracking_number`, `Order.tracking_url`, `Order.estimated_delivery_date` | Optional, set by an admin when shipping. |
| `OrderStatus.OUT_FOR_DELIVERY` | New status between `shipped` and `delivered`; existing values unchanged. |

Every new query is a single-property equality filter, which Datastore's built-in indexes serve — no `index.yaml` changes.

## 8. Running tests

```bash
gcloud beta emulators datastore start --no-store-on-disk --consistency=1.0   # separate terminal
pytest -q
# or, with nothing installed locally:
make test        # runs its own throwaway emulator container
```

Tests run against the Datastore emulator (the suite **resets all emulator data** before each test, so never point it at an emulator holding data you care about) and mock the Razorpay SDK calls — no real GCP project, Razorpay credentials or network access needed.

## 9. Docker setup (recommended local workflow)

```bash
cp .env.example .env   # optional, docker-compose.yml has sane defaults for local use
docker compose build
docker compose up -d datastore   # Datastore emulator, data persisted in a volume
docker compose up -d web

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

Webhook processing is idempotent: each event is deduplicated by `X-Razorpay-Event-Id` (falling back to a body hash) as the `WebhookEvent` entity id, so retries never double-process a payment.

## 11. Deploy to Google Cloud Run

> Only needed for the cloud deployment. Nothing here is required to run the app locally.

```bash
gcloud auth login akgileshgoswami@gmail.com   # once
./scripts/deploy.sh
```

Defaults: project `e-com-509609`, region `us-central1`, service `ecom-web` — override with env vars or a gitignored `.env.deploy` file (see the header of `scripts/deploy.sh`). Every step is idempotent. The first run:

- checks you're logged in and **billing is enabled** (Cloud Run requires it)
- enables Cloud Run, Cloud Build, Artifact Registry, Firestore/Datastore, Secret Manager, Storage APIs
- creates the `(default)` Firestore database in **Datastore mode**
- creates two service accounts: `ecom-web` (runtime: `datastore.user`, read access to its secrets, write access to the upload bucket) and `ecom-builder` (`run.builder`, used by Cloud Build)
- creates a public-read GCS bucket `<project>-ecom-uploads` for product images/logos/banners (Cloud Run's disk is wiped on restart)
- generates `SECRET_KEY` once into Secret Manager; stores Razorpay / Google OAuth / mail secrets too if you set them in `.env.deploy`
- builds the Dockerfile with `gcloud run deploy --source` and deploys: 512Mi, 1 CPU, scale 0–2 instances, public
- curls `/health`

Later runs just ship a new revision. `./scripts/deploy.sh ship` skips provisioning (used by GitHub Actions).

### Seed an admin user in production

```bash
./scripts/deploy.sh seed-admin admin@yourdomain.com
```

Prompts for the password, hands it to a one-off Cloud Run Job through a temporary Secret Manager secret (deleted afterwards), and runs `flask seed-admin` with the deployed image.

### Custom domain + HTTPS

```bash
gcloud run domain-mappings create --service=<SERVICE_NAME> --domain=shop.yourdomain.com --region=<REGION>
```

Cloud Run provisions and renews the TLS certificate automatically once your DNS `CNAME`/`A` records point at the given target. Re-run `BASE_URL=https://shop.yourdomain.com ./scripts/deploy.sh` and your Razorpay webhook URL to the new domain afterward.

## 12. Costs & scaling notes

- With scale-to-zero and Firestore's free tier, an idle/low-traffic shop costs close to nothing; there's no always-on database instance.
- Catalog listing, search and admin lists load the relevant entities and filter/sort in Python. That's fine up to a few thousand products/orders; beyond that, add composite indexes (`index.yaml`, `gcloud datastore indexes create`) and push filters/sorts into queries.

## 13. Production checklist

- [ ] `SECRET_KEY` set from Secret Manager, not a default/dev value
- [ ] Razorpay **live** keys + **live** webhook secret set (test keys will silently fail live payments)
- [ ] Razorpay webhook URL registered and reachable over HTTPS
- [ ] `GCS_ENABLED=true` with the correct bucket name
- [ ] `SESSION_COOKIE_SECURE=true` (automatic under `ProductionConfig`)
- [ ] `./scripts/deploy.sh seed-admin` run once to create a real admin account; demo `flask seed-data` **not** run in production
- [ ] Custom domain mapped, DNS propagated, TLS certificate issued
- [ ] `/health` returns 200 after deploy
- [ ] `BASE_URL` is the public https URL (custom domain once mapped) — email links use it
- [ ] SMTP configured (`MAIL_SERVER`, `MAIL_USERNAME`, `MAIL_DEFAULT_SENDER`, `MAIL_PASSWORD` in Secret Manager), sender domain has SPF/DKIM, and `flask send-test-email` succeeds
- [ ] `OWNER_EMAIL` set; no `Email configuration:` errors in the startup logs

## 14. Troubleshooting

- **`ModuleNotFoundError: No module named 'pkg_resources'` when importing `razorpay`** — your `setuptools` is ≥ 81. `pip install "setuptools<81"` (already pinned in `requirements.txt`; only bites you if you install packages outside of it).
- **`Datastore emulator not reachable`** when running tests — start the emulator first (section 8) or use `make test`.
- **`DefaultCredentialsError` locally** — `DATASTORE_EMULATOR_HOST`/`DATASTORE_PROJECT_ID` aren't set, so NDB is looking for real GCP credentials; copy them from `.env.example`.
- **`docker compose up` can't bind port 5000** — that's macOS's AirPlay Receiver. This repo maps the app to host port **8000** instead; if you changed it back to 5000, either rename the port or disable AirPlay Receiver in System Settings → General → AirDrop & Handoff.
- **Webhook signature verification fails** — confirm `RAZORPAY_WEBHOOK_SECRET` matches exactly what's shown in the Razorpay dashboard for that specific webhook endpoint (each webhook URL can have its own secret).
- **Orders stuck in `pending_payment`** — this is expected if a customer closes the Razorpay modal without completing payment; stock reserved for that order is released automatically when `/payment/razorpay/failed` fires (modal dismissed) or a `payment.failed` webhook arrives. Customers can also cancel a `pending_payment` order themselves from the order detail page.

- **Emails aren't arriving** — see [Troubleshooting email delivery](#troubleshooting-email-delivery).

## 15. Email notifications

### What is sent, and when

| Email | Template (`app/templates/emails/`) | Sent when |
|---|---|---|
| Reset your password | `forgot_password` | A registered, active account requests a reset (the page answers identically for unknown emails). |
| Email verification code | `verify_email` | Email/password sign-up, or a login attempt (correct password) on an account that isn't verified yet. |
| Password changed | `password_changed` | After a reset or a change from the profile page. |
| Order confirmed | `order_confirmation` | COD: right after the order commits. Razorpay: only after the payment is verified server-side (checkout signature check or signed webhook) — never on the client's word, and never for failed/unverified payments. |
| New order received (owner) | `owner_new_order` | Same moment as the confirmation, independently of it, to `OWNER_EMAIL`. Includes a link to the admin order page (admin login required). |
| Order status update | `order_status_updated`, `order_cancelled`, `order_delivered` | After an admin (or the customer, for cancellations) changes the status and the transaction commits. Not sent when the status doesn't change or for other edits. Tracking/ETA included when set. |
| Payment received | `payment_confirmation` | Admin marks a COD order's cash as collected. |
| Welcome | `registration` | Email sign-up. |

Every email has an HTML part (shared `base_email.html` layout + `_components.html` macros, inline CSS, mobile-friendly, store name/logo/theme colour and support contacts from the admin settings) and a plain-text part (`.txt`).

### Email verification on sign-up

New email/password accounts start unverified and can't log in until the customer enters the 6-digit code emailed to them at `/verify-email`; then they're logged in, their pending add-to-cart/wishlist action is replayed and the welcome email goes out.

- Code: random 6 digits, valid `EMAIL_OTP_EXPIRY_MINUTES` (10), stored only as an HMAC (keyed with `SECRET_KEY`) in the `EmailVerificationCode` kind (one row per user, replaced on resend, deleted on success).
- Limits: `EMAIL_OTP_MAX_ATTEMPTS` (5) wrong codes kill the code; "Resend" waits `EMAIL_OTP_RESEND_SECONDS` (60) and allows `EMAIL_OTP_MAX_PER_HOUR` (5) sends per account; per-IP limits on verify/resend.
- Logging in with the right password on an unverified account sends a fresh code and opens the verify page instead of logging in.
- Signing up again with an email that was never verified replaces that pending sign-up (nobody proved they own it). A Google sign-in or a completed password reset on it marks the email verified — and a Google sign-in discards the pending account's password.
- Accounts created before this feature, admins from `flask seed-admin`, and Google sign-ins count as verified. Admin → Users shows an "Email unverified" badge for pending ones.
- Set `EMAIL_VERIFICATION_REQUIRED=false` to switch it off. Note: with `MAIL_ENABLED=false` no code can arrive, so either configure SMTP (or Mailpit) locally or switch verification off.

### Editing email wording (admin panel)

**Admin → Store design → Email templates** (`/admin/emails`) lists every email. For each one an admin can edit the subject, heading, main message, button label and an optional extra note, using placeholders such as `{customer_name}`, `{order_number}`, `{order_total}` (the page lists the ones each email supports; unknown ones are rejected). The page shows a live preview with sample data, a plain-text view, **Preview changes** (without saving), **Send test to me**, and **Reset to default**.

Only the wording is editable. Layout, order tables, links, the reset link and its expiry/security notices stay in the code templates, so an edit can't break an email or remove required information. Admin text is plain text (HTML is escaped, `{{ … }}` isn't evaluated). Edits are stored as `SiteContent` rows `email.<template>.<field>` and apply to the next email sent; fields left at the default aren't stored.

### How delivery works

- `app/services/email_service.py` renders and sends everything; routes and services just call `EmailService.send_…()`. It never raises: an SMTP outage can't roll back an order or a payment.
- Order/account notifications are first claimed in the `EmailOutbox` under an idempotency key (one per order, per status transition, …), so retried requests, double-clicked admin forms and the Razorpay webhook racing the browser callback never send twice.
- A failed send stays in the outbox as `failed`. Retry with `flask send-pending-emails` (safe to run any time; up to 5 attempts per email). Password-reset emails are deliberately not stored — the user just requests a new link.
- Sending is synchronous (no task queue exists in this project). To move it to a background worker later, enqueue the outbox key and call `EmailService.send_outbox_row()` from the worker.
- Logs contain the email kind and a masked recipient (`c***@example.com`) only — never bodies, reset links or credentials.

### SMTP configuration

**Gmail / Google Workspace**

1. Turn on 2-Step Verification for the sending account.
2. Create an App Password: <https://myaccount.google.com/apppasswords>.
3. Configure:
   ```env
   MAIL_SERVER=smtp.gmail.com
   MAIL_PORT=587
   MAIL_USE_TLS=true
   MAIL_USE_SSL=false
   MAIL_USERNAME=you@gmail.com
   MAIL_PASSWORD=<16-character app password>
   MAIL_DEFAULT_SENDER=you@gmail.com
   ```
   Gmail caps sending at roughly 500 emails/day (2,000 on Workspace).

**SendGrid / Mailgun / Amazon SES / Brevo** — use the provider's SMTP host, port `587` with `MAIL_USE_TLS=true` (or `465` with `MAIL_USE_SSL=true`), and its SMTP credentials (SendGrid: `MAIL_USERNAME=apikey`, `MAIL_PASSWORD=<API key>`). Verify the sender domain with SPF/DKIM so emails don't land in spam.

Settings are validated at startup; problems (missing server/sender, TLS and SSL both on, missing `OWNER_EMAIL`, non-absolute `BASE_URL`) are logged as `Email configuration: …` errors.

### Public base URL and owner email

- `BASE_URL` must be the URL customers use, e.g. `https://shop.yourdomain.com` (no trailing slash needed). Links are never built from the request's Host header, so a forged Host can't poison reset links. `scripts/deploy.sh` defaults it to the `run.app` URL; set `BASE_URL=https://your-domain` in `.env.deploy` once a custom domain is mapped.
- `OWNER_EMAIL=owner@yourdomain.com` (or `a@x.com;b@x.com`). If it's missing, the customer still gets their confirmation and an `OWNER_EMAIL is not configured` error is logged.

### Testing email locally

- Default (`MAIL_ENABLED=false`): nothing is sent; each email is logged as `Email suppressed … kind=… to=…`.
- See real messages without a real mailbox using [Mailpit](https://mailpit.axllent.org/):
  ```bash
  docker run -d --name mailpit -p 8025:8025 -p 1025:1025 axllent/mailpit
  export MAIL_ENABLED=true MAIL_SERVER=localhost MAIL_PORT=1025 MAIL_USE_TLS=false MAIL_USE_SSL=false \
         MAIL_USERNAME= MAIL_PASSWORD= OWNER_EMAIL=owner@example.com
  flask run        # then open http://localhost:8025
  ```
- Check real SMTP settings: `flask send-test-email you@example.com`.
- Automated tests never send email: `TestingConfig` sets `MAIL_SUPPRESS_SEND`, and tests capture messages with the `mail_outbox` fixture (`tests/test_password_reset.py`, `tests/test_order_emails.py`).

### Production (Cloud Run)

Add to `.env.deploy` and re-run `./scripts/deploy.sh`:

```env
BASE_URL=https://shop.yourdomain.com
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=you@gmail.com
MAIL_PASSWORD=<app password>          # stored in Secret Manager as ecom-mail-password
MAIL_DEFAULT_SENDER=you@gmail.com
OWNER_EMAIL=owner@yourdomain.com
```

Nothing is kept on the local filesystem — reset tokens and the outbox live in Firestore. The per-account reset limit is enforced in the database, so it holds across instances; the per-IP limiter uses `RATELIMIT_STORAGE_URI` (default `memory://`, i.e. per instance — point it at Redis/Memorystore for a global limit).

To retry failed emails automatically, run the command as a Cloud Run Job on a schedule (optional; no new infrastructure is created by default):

```bash
IMAGE=$(gcloud run services describe ecom-web --region=us-central1 --format='value(spec.template.spec.containers[0].image)')
gcloud run jobs deploy ecom-send-pending-emails --image="$IMAGE" --region=us-central1 \
  --service-account=ecom-web@<PROJECT_ID>.iam.gserviceaccount.com \
  --set-env-vars="FLASK_APP=wsgi.py,FLASK_ENV=production,GOOGLE_CLOUD_PROJECT=<PROJECT_ID>,BASE_URL=<BASE_URL>,MAIL_SERVER=…,MAIL_USERNAME=…,MAIL_DEFAULT_SENDER=…,OWNER_EMAIL=…" \
  --set-secrets="SECRET_KEY=ecom-secret-key:latest,MAIL_PASSWORD=ecom-mail-password:latest" \
  --command=flask --args=send-pending-emails
# then trigger it every 15 minutes with Cloud Scheduler (console: Cloud Run → Jobs → Triggers)
```

### Troubleshooting email delivery

- **Nothing sent, log says `Email suppressed (MAIL_ENABLED=false)`** — set `MAIL_SERVER` (which enables sending) or `MAIL_ENABLED=true`.
- **`SMTPAuthenticationError`** — wrong credentials; for Gmail you need an App Password, not the account password.
- **`SSLCertVerificationError`** — `MAIL_SERVER` doesn't match the server's certificate (use the provider's real hostname, not an IP). Verification is intentionally never disabled.
- **`SMTPServerDisconnected` / timeouts** — wrong port/TLS pairing: `587` needs `MAIL_USE_TLS=true`, `465` needs `MAIL_USE_SSL=true`. Some networks block outbound 25/465/587.
- **Links in emails point at localhost** — set `BASE_URL` to the public URL.
- **Owner gets nothing** — check `OWNER_EMAIL` and the startup log.
- **An email failed** — it's in the `EmailOutbox` kind with `status=failed` and `last_error`; fix the cause and run `flask send-pending-emails`.
- **Emails in spam** — authenticate the sender domain (SPF, DKIM, DMARC) with your provider and send from that domain.

---

## Local setup — quick reference

```bash
# Docker (recommended)
docker compose build
docker compose up -d datastore
docker compose up -d web
docker compose run --rm web flask seed-admin --email admin@example.com --password "ChangeMe123!"
docker compose run --rm web flask seed-data

# Tests
make test
```

## Cloud Run deployment — quick reference

```bash
./scripts/deploy.sh                         # provision + deploy
./scripts/deploy.sh seed-admin you@example.com
./scripts/deploy.sh logs
```
