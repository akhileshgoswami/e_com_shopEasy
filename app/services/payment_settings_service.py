"""Admin-managed payment settings: which methods are offered at checkout and
the Razorpay credentials, so keys can be switched (test -> live, rotation)
from the admin panel without a redeploy.

Values saved here win over the RAZORPAY_* env vars / Secret Manager, which
stay as the fallback. Secrets are encrypted at rest with a key derived from
SECRET_KEY and are never sent back to the browser — the admin form only
shows the last four characters.
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

from app.models import SiteContent
from app.services.site_content_service import _set_values

logger = logging.getLogger("app.payments.settings")

_PREFIX = "payment_"
_FLAGS = ("razorpay_enabled", "cod_enabled")
_SECRETS = ("razorpay_key_secret", "razorpay_webhook_secret")
_CONFIG_FALLBACK = {
    "razorpay_key_id": "RAZORPAY_KEY_ID",
    "razorpay_key_secret": "RAZORPAY_KEY_SECRET",
    "razorpay_webhook_secret": "RAZORPAY_WEBHOOK_SECRET",
}
_LABELS = {
    "razorpay_enabled": "Razorpay enabled",
    "cod_enabled": "Cash on delivery enabled",
    "razorpay_key_id": "Razorpay key id",
    "razorpay_key_secret": "Razorpay key secret (encrypted)",
    "razorpay_webhook_secret": "Razorpay webhook secret (encrypted)",
}
KEYS = tuple(_LABELS)


class PaymentSettingsError(Exception):
    pass


def _fernet():
    digest = hashlib.sha256(f"{current_app.config['SECRET_KEY']}:payment-settings".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt(value):
    return _fernet().encrypt(value.encode()).decode()


def _decrypt(token):
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        # SECRET_KEY changed since the secret was saved: treat as unset so
        # the env fallback applies, and make the admin re-enter it.
        logger.warning("Stored Razorpay secret could not be decrypted; re-enter it in admin settings.")
        return ""


def mask(value):
    if not value:
        return ""
    return "••••" + value[-4:] if len(value) > 4 else "••••"


class PaymentSettingsService:
    @staticmethod
    def get():
        """Effective settings: saved value, else env config, else default."""
        rows = SiteContent.get_many(_PREFIX + key for key in KEYS)
        saved = {key: rows[_PREFIX + key].value for key in KEYS if _PREFIX + key in rows}

        settings = {}
        for key in _FLAGS:
            settings[key] = saved.get(key, "1") == "1"
        for key, config_key in _CONFIG_FALLBACK.items():
            stored = saved.get(key) or ""
            value = _decrypt(stored) if stored and key in _SECRETS else stored
            source = "admin"
            if not value:
                value = current_app.config.get(config_key) or ""
                source = "env" if value else "none"
            settings[key] = value
            settings[f"{key}_source"] = source

        settings["razorpay_configured"] = bool(settings["razorpay_key_id"] and settings["razorpay_key_secret"])
        settings["razorpay_available"] = settings["razorpay_enabled"] and settings["razorpay_configured"]
        key_id = settings["razorpay_key_id"]
        settings["razorpay_mode"] = "live" if key_id.startswith("rzp_live_") else ("test" if key_id.startswith("rzp_test_") else "")
        return settings

    @classmethod
    def enabled_methods(cls, settings=None):
        """Payment method codes customers may choose right now."""
        from app.models import PaymentMethod

        settings = settings or cls.get()
        methods = []
        if settings["cod_enabled"]:
            methods.append(PaymentMethod.COD)
        if settings["razorpay_available"]:
            methods.append(PaymentMethod.RAZORPAY)
        return methods

    @classmethod
    def update(cls, razorpay_enabled, cod_enabled, key_id, key_secret=None, webhook_secret=None, clear_secrets=False):
        """Blank key_secret / webhook_secret keep the saved value. clear_secrets
        removes the admin-saved credentials so the env values apply again.
        Returns (settings, warning_or_None)."""
        key_id = (key_id or "").strip()
        if key_id and not key_id.startswith(("rzp_test_", "rzp_live_")):
            raise PaymentSettingsError("Razorpay Key ID should start with rzp_test_ or rzp_live_.")
        if not razorpay_enabled and not cod_enabled:
            raise PaymentSettingsError("Keep at least one payment method enabled.")

        pending = [
            (_PREFIX + "razorpay_enabled", "1" if razorpay_enabled else "0", _LABELS["razorpay_enabled"]),
            (_PREFIX + "cod_enabled", "1" if cod_enabled else "0", _LABELS["cod_enabled"]),
        ]
        if clear_secrets:
            for key in _CONFIG_FALLBACK:
                pending.append((_PREFIX + key, "", _LABELS[key]))
        else:
            pending.append((_PREFIX + "razorpay_key_id", key_id, _LABELS["razorpay_key_id"]))
            for key, value in (("razorpay_key_secret", key_secret), ("razorpay_webhook_secret", webhook_secret)):
                value = (value or "").strip()
                if value:
                    pending.append((_PREFIX + key, _encrypt(value), _LABELS[key]))
        _set_values(pending)

        settings = cls.get()
        warning = None
        if razorpay_enabled and not settings["razorpay_configured"]:
            warning = "Razorpay stays hidden at checkout until both Key ID and Key Secret are set."
        return settings, warning
