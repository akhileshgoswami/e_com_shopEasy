import os
from datetime import timedelta


def _bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")
    PORT = int(os.environ.get("PORT", 5000))
    FLASK_ENV = os.environ.get("FLASK_ENV", "development")

    WTF_CSRF_ENABLED = _bool(os.environ.get("WTF_CSRF_ENABLED"), True)

    # Unique name so other apps on localhost (cookies ignore the port) can't
    # overwrite our session mid-login — that surfaces as OAuth "mismatching_state".
    SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "shopeasy_session")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool(os.environ.get("SESSION_COOKIE_SECURE"), False)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = _bool(os.environ.get("SESSION_COOKIE_SECURE"), False)
    # Logins survive closing the browser and stay valid for this long after
    # the last visit (every request pushes the expiry forward). "Remember me"
    # keeps people signed in far longer via REMEMBER_COOKIE_DURATION.
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=int(os.environ.get("SESSION_LIFETIME_MINUTES", 480)))
    SESSION_REFRESH_EACH_REQUEST = True
    REMEMBER_COOKIE_DURATION = timedelta(days=int(os.environ.get("REMEMBER_COOKIE_DAYS", 14)))
    # CSRF tokens live as long as the session instead of a fixed hour, so a
    # form left open doesn't fail with "CSRF token has expired".
    WTF_CSRF_TIME_LIMIT = None
    # Behind Cloud Run / a load balancer, trust one hop of X-Forwarded-* so
    # url_for(_external=True) builds https:// URLs (Google OAuth redirect_uri
    # must match exactly what's registered in Google Cloud Console).
    TRUST_PROXY_HEADERS = _bool(os.environ.get("TRUST_PROXY_HEADERS"), False)

    RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID")
    RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")
    RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    RAZORPAY_CURRENCY = os.environ.get("RAZORPAY_CURRENCY", "INR")

    # DATASTORE_PROJECT_ID is what the Datastore emulator uses locally; on
    # Cloud Run GOOGLE_CLOUD_PROJECT is set by the deploy script.
    GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("DATASTORE_PROJECT_ID")
    GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")
    GCS_ENABLED = _bool(os.environ.get("GCS_ENABLED"), False)

    GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")

    MAIL_SERVER = os.environ.get("MAIL_SERVER")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    # STARTTLS on 587 (MAIL_USE_TLS) or implicit TLS on 465 (MAIL_USE_SSL) —
    # never both. Certificates are always verified.
    MAIL_USE_TLS = _bool(os.environ.get("MAIL_USE_TLS"), True)
    MAIL_USE_SSL = _bool(os.environ.get("MAIL_USE_SSL"), False)
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "no-reply@example.com")
    # Sending is on whenever an SMTP server is configured, unless explicitly
    # switched off; with it off, emails are only logged.
    MAIL_ENABLED = _bool(os.environ.get("MAIL_ENABLED"), bool(os.environ.get("MAIL_SERVER")))
    MAIL_TIMEOUT_SECONDS = int(os.environ.get("MAIL_TIMEOUT_SECONDS", 15))
    # New-order notifications; several addresses may be separated by "," or ";".
    OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "")

    PASSWORD_RESET_TOKEN_EXPIRY_MINUTES = int(os.environ.get("PASSWORD_RESET_TOKEN_EXPIRY_MINUTES", 30))
    # Per-account cap on reset emails, enforced in the database so it holds
    # across every Cloud Run instance (the IP limiter is per-instance).
    PASSWORD_RESET_MAX_PER_HOUR = int(os.environ.get("PASSWORD_RESET_MAX_PER_HOUR", 3))

    # New email/password sign-ups must enter a code emailed to them before
    # they can log in. Existing accounts and Google sign-ins are unaffected.
    EMAIL_VERIFICATION_REQUIRED = _bool(os.environ.get("EMAIL_VERIFICATION_REQUIRED"), True)
    EMAIL_OTP_EXPIRY_MINUTES = int(os.environ.get("EMAIL_OTP_EXPIRY_MINUTES", 10))
    EMAIL_OTP_MAX_ATTEMPTS = int(os.environ.get("EMAIL_OTP_MAX_ATTEMPTS", 5))
    EMAIL_OTP_RESEND_SECONDS = int(os.environ.get("EMAIL_OTP_RESEND_SECONDS", 60))
    EMAIL_OTP_MAX_PER_HOUR = int(os.environ.get("EMAIL_OTP_MAX_PER_HOUR", 5))

    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True

    UPLOAD_LOCAL_DIR = os.environ.get(
        "UPLOAD_LOCAL_DIR",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "static", "uploads"),
    )
    UPLOAD_MAX_SIZE_BYTES = int(os.environ.get("UPLOAD_MAX_SIZE_BYTES", 5 * 1024 * 1024))
    ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
    ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

    MAX_CONTENT_LENGTH = 10 * 1024 * 1024

    ITEMS_PER_PAGE = int(os.environ.get("ITEMS_PER_PAGE", 12))
    ADMIN_ITEMS_PER_PAGE = int(os.environ.get("ADMIN_ITEMS_PER_PAGE", 20))

    DEFAULT_SHIPPING_CHARGE = float(os.environ.get("DEFAULT_SHIPPING_CHARGE", 49.0))
    FREE_SHIPPING_THRESHOLD = float(os.environ.get("FREE_SHIPPING_THRESHOLD", 999.0))
    TAX_RATE_PERCENT = float(os.environ.get("TAX_RATE_PERCENT", 0.0))

    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

    @staticmethod
    def init_app(app):
        pass


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    if not BaseConfig.SECRET_KEY:
        SECRET_KEY = "dev-secret-key-not-for-production"


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = True
    WTF_CSRF_ENABLED = False
    GOOGLE_CLOUD_PROJECT = os.environ.get("DATASTORE_PROJECT_ID", "e-com-test")
    SECRET_KEY = "test-secret-key"
    RATELIMIT_ENABLED = False
    MAIL_ENABLED = False
    # Flask-Mail never opens an SMTP connection in tests; messages are only
    # recorded (mail.record_messages()).
    MAIL_SUPPRESS_SEND = True
    OWNER_EMAIL = "owner@example.com"
    BASE_URL = "https://shop.example.com"
    RAZORPAY_KEY_ID = "rzp_test_key_id"
    RAZORPAY_KEY_SECRET = "rzp_test_key_secret"
    RAZORPAY_WEBHOOK_SECRET = "test_webhook_secret"
    # Ignore any real OAuth app in the developer's .env; tests opt in explicitly.
    GOOGLE_OAUTH_CLIENT_ID = None
    GOOGLE_OAUTH_CLIENT_SECRET = None
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False


class ProductionConfig(BaseConfig):
    TRUST_PROXY_HEADERS = _bool(os.environ.get("TRUST_PROXY_HEADERS"), True)
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True

    @staticmethod
    def init_app(app):
        BaseConfig.init_app(app)
        required = ["SECRET_KEY"]
        missing = [name for name in required if not app.config.get(name)]
        if missing:
            raise RuntimeError(
                f"Missing required production configuration: {', '.join(missing)}"
            )
        if not app.config.get("RAZORPAY_KEY_ID") or not app.config.get("RAZORPAY_KEY_SECRET"):
            app.logger.warning("Razorpay keys are not configured; online payments will fail.")


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config(name=None):
    name = name or os.environ.get("FLASK_ENV", "development")
    return config_by_name.get(name, DevelopmentConfig)
