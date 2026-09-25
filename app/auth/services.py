import logging
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app
from google.cloud import ndb

from app.models import Cart, PasswordResetToken, Role, User
from app.utils import as_aware_utc

logger = logging.getLogger("app.auth")

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
# Anything longer than this can't be one of our tokens; reject before hashing.
MAX_RESET_TOKEN_LENGTH = 128
# Spent/expired reset rows are kept this long (for the per-hour throttle and
# the "already used" message), then cleaned up on the account's next request.
RESET_TOKEN_RETENTION = timedelta(days=1)


class AuthError(Exception):
    pass


class ResetTokenError(AuthError):
    """state is "invalid", "expired" or "used" so the page can explain."""

    MESSAGES = {
        "invalid": "This password reset link is invalid. Please request a new one.",
        "expired": "This password reset link has expired. Please request a new one.",
        "used": "This password reset link has already been used. Please request a new one if you still need to reset your password.",
    }

    def __init__(self, state):
        self.state = state
        super().__init__(self.MESSAGES[state])


def _create_with_cart(user):
    """The cart's id is the user's id, so it can only be created once the
    user has one."""
    user.put()
    Cart(id=user.id, user_id=user.id).put()


class AuthenticationService:
    @staticmethod
    def register_customer(name, email, password, phone=None):
        email = email.strip().lower()
        if User.by_email(email):
            raise AuthError("An account with this email already exists.")

        user = User(name=name.strip(), email=email, phone=phone, role=Role.CUSTOMER, is_active=True)
        user.set_password(password)
        _create_with_cart(user)
        logger.info("New customer registered: user_id=%s", user.id)
        return user

    @staticmethod
    def find_or_create_google_user(email, name, email_verified):
        """Log in via "Sign in with Google". Matches an existing account by
        email (only when Google reports the email as verified, so a stolen
        unverified address can't hijack an existing password-based account),
        or creates a new customer. The created account gets an unusable
        random password — it can only ever be signed into via Google, unless
        the owner later uses "forgot password" to set one explicitly."""
        email = (email or "").strip().lower()
        if not email:
            raise AuthError("Google did not share an email address with this app.")
        if not email_verified:
            raise AuthError("Your Google email address is not verified.")

        user = User.by_email(email)
        if user is not None:
            if not user.is_active:
                raise AuthError("This account has been deactivated.")
            return user

        user = User(name=name or email.split("@")[0], email=email, role=Role.CUSTOMER, is_active=True)
        user.set_password(secrets.token_urlsafe(32))
        _create_with_cart(user)
        logger.info("New customer registered via Google: user_id=%s", user.id)
        return user

    @staticmethod
    def authenticate(email, password):
        user = User.by_email(email)

        if user is None:
            logger.info("Login failed: unknown email")
            raise AuthError("Invalid email or password.")

        now = datetime.now(timezone.utc)
        locked_until = as_aware_utc(user.locked_until)
        if locked_until and locked_until > now:
            remaining = int((locked_until - now).total_seconds() // 60) + 1
            logger.warning("Login blocked: user_id=%s locked for %s more minutes", user.id, remaining)
            raise AuthError(f"Account temporarily locked. Try again in {remaining} minute(s).")

        if not user.is_active:
            logger.warning("Login failed: user_id=%s inactive", user.id)
            raise AuthError("This account has been deactivated.")

        if not user.check_password(password):
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
                user.failed_login_attempts = 0
                user.put()
                logger.warning("Account locked after repeated failures: user_id=%s", user.id)
                raise AuthError(f"Too many failed attempts. Account locked for {LOCKOUT_MINUTES} minutes.")
            user.put()
            logger.info("Login failed: bad password user_id=%s attempts=%s", user.id, user.failed_login_attempts)
            raise AuthError("Invalid email or password.")

        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        user.put()
        logger.info("Login success: user_id=%s", user.id)
        return user

    # ------------------------------------------------------------------
    # Password reset
    # ------------------------------------------------------------------

    @staticmethod
    def request_password_reset(email):
        """Issue a single-use reset token for the account with this email.

        Returns (user, raw_token), or (None, None) when the email is unknown,
        the account is inactive, or the account hit its hourly limit. The
        caller must respond identically in every case so the page can't be
        used to discover which emails are registered."""
        user = User.by_email(email)
        if user is None or not user.is_active:
            logger.info("Password reset requested for unknown or inactive account")
            return None, None

        config = current_app.config
        now = datetime.now(timezone.utc)
        existing = PasswordResetToken.for_user(user.id)
        recent = [t for t in existing if as_aware_utc(t.created_at) > now - timedelta(hours=1)]
        if len(recent) >= config["PASSWORD_RESET_MAX_PER_HOUR"]:
            logger.warning("Password reset throttled: user_id=%s", user.id)
            return None, None

        token = secrets.token_urlsafe(32)
        to_put = [
            PasswordResetToken(
                key=PasswordResetToken.key_for(token),
                user_id=user.id,
                expires_at=now + timedelta(minutes=config["PASSWORD_RESET_TOKEN_EXPIRY_MINUTES"]),
            )
        ]
        # Only the newest link works.
        for old in existing:
            if old.used_at is None:
                old.used_at = now
                old.superseded = True
                to_put.append(old)
        stale = [t.key for t in existing if as_aware_utc(t.created_at) < now - RESET_TOKEN_RETENTION]
        ndb.put_multi(to_put)
        if stale:
            ndb.delete_multi(stale)
        logger.info("Password reset token issued: user_id=%s", user.id)
        return user, token

    @staticmethod
    def _check_reset_record(record, now):
        if record is None:
            raise ResetTokenError("invalid")
        if record.used_at is not None:
            raise ResetTokenError("used")
        if as_aware_utc(record.expires_at) <= now:
            raise ResetTokenError("expired")

    @classmethod
    def verify_reset_token(cls, token):
        """The user a still-valid token belongs to, without spending it."""
        if not token or len(token) > MAX_RESET_TOKEN_LENGTH:
            raise ResetTokenError("invalid")
        record = PasswordResetToken.key_for(token).get()
        cls._check_reset_record(record, datetime.now(timezone.utc))
        user = User.find(record.user_id)
        if user is None or not user.is_active:
            raise ResetTokenError("invalid")
        return user

    @classmethod
    def reset_password_with_token(cls, token, new_password):
        """Spend the token and set the new password in one transaction, so
        two concurrent submissions can't both succeed. Signs the account out
        everywhere. Returns the updated user."""
        if not token or len(token) > MAX_RESET_TOKEN_LENGTH:
            raise ResetTokenError("invalid")
        record_key = PasswordResetToken.key_for(token)
        # Hash outside the transaction: it is deliberately slow and a
        # contended transaction may run more than once.
        from werkzeug.security import generate_password_hash

        password_hash = generate_password_hash(new_password)

        def txn():
            now = datetime.now(timezone.utc)
            record = record_key.get()
            cls._check_reset_record(record, now)
            user = User.get_by_id(record.user_id)
            if user is None or not user.is_active:
                raise ResetTokenError("invalid")
            user.password_hash = password_hash
            user.failed_login_attempts = 0
            user.locked_until = None
            user.password_changed_at = now
            user.revoke_sessions()
            record.used_at = now
            ndb.put_multi([record, user])
            return user

        user = ndb.transaction(txn)
        logger.info("Password reset completed: user_id=%s", user.id)
        return user

    @staticmethod
    def change_password(user, current_password, new_password):
        if not user.check_password(current_password):
            raise AuthError("Current password is incorrect.")
        user.set_password(new_password)
        user.password_changed_at = datetime.now(timezone.utc)
        # Other devices are signed out; the caller re-logs-in this session.
        user.revoke_sessions()
        user.put()
        logger.info("Password changed: user_id=%s", user.id)
