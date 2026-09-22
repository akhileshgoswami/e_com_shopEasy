import os


def _bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _build_database_url():
    """Build DATABASE_URL, preferring a Cloud SQL unix socket connection
    on Cloud Run (when INSTANCE_CONNECTION_NAME is set) over a plain URL."""
    instance_connection_name = os.environ.get("INSTANCE_CONNECTION_NAME")
    if instance_connection_name:
        db_user = os.environ["DB_USER"]
        db_password = os.environ["DB_PASSWORD"]
        db_name = os.environ["DB_NAME"]
        socket_path = f"/cloudsql/{instance_connection_name}"
        return (
            f"postgresql+psycopg2://{db_user}:{db_password}@/{db_name}"
            f"?host={socket_path}"
        )
    return os.environ.get("DATABASE_URL")


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000")
    PORT = int(os.environ.get("PORT", 5000))
    FLASK_ENV = os.environ.get("FLASK_ENV", "development")

    SQLALCHEMY_DATABASE_URI = _build_database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_size": int(os.environ.get("DB_POOL_SIZE", 5)),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", 2)),
        "pool_recycle": int(os.environ.get("DB_POOL_RECYCLE", 1800)),
        "pool_timeout": int(os.environ.get("DB_POOL_TIMEOUT", 30)),
    }

    WTF_CSRF_ENABLED = _bool(os.environ.get("WTF_CSRF_ENABLED"), True)

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool(os.environ.get("SESSION_COOKIE_SECURE"), False)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = _bool(os.environ.get("SESSION_COOKIE_SECURE"), False)
    REMEMBER_COOKIE_DURATION_DAYS = 14

    RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID")
    RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET")
    RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET")
    RAZORPAY_CURRENCY = os.environ.get("RAZORPAY_CURRENCY", "INR")

    GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT")
    GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")
    GCS_ENABLED = _bool(os.environ.get("GCS_ENABLED"), False)

    GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")

    MAIL_SERVER = os.environ.get("MAIL_SERVER")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = _bool(os.environ.get("MAIL_USE_TLS"), True)
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "no-reply@example.com")
    MAIL_ENABLED = _bool(os.environ.get("MAIL_ENABLED"), False)

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
    if not BaseConfig.SQLALCHEMY_DATABASE_URI:
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dev.db"
        )
    if not BaseConfig.SECRET_KEY:
        SECRET_KEY = "dev-secret-key-not-for-production"


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    SQLALCHEMY_ENGINE_OPTIONS = {}
    SECRET_KEY = "test-secret-key"
    RATELIMIT_ENABLED = False
    MAIL_ENABLED = False
    RAZORPAY_KEY_ID = "rzp_test_key_id"
    RAZORPAY_KEY_SECRET = "rzp_test_key_secret"
    RAZORPAY_WEBHOOK_SECRET = "test_webhook_secret"
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True

    @staticmethod
    def init_app(app):
        BaseConfig.init_app(app)
        required = ["SECRET_KEY", "SQLALCHEMY_DATABASE_URI"]
        missing = [name for name in required if not app.config.get(name)]
        if missing:
            raise RuntimeError(
                f"Missing required production configuration: {', '.join(missing)}"
            )
        if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
            raise RuntimeError("SQLite is not allowed in production. Use PostgreSQL.")
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
