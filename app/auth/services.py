import logging
import secrets
from datetime import datetime, timedelta, timezone

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.models import Cart, Role, User
from app.utils import as_aware_utc

logger = logging.getLogger("app.auth")

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
RESET_TOKEN_MAX_AGE_SECONDS = 3600
RESET_SALT = "password-reset-salt"


class AuthError(Exception):
    pass


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

    @staticmethod
    def _serializer():
        from flask import current_app

        return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])

    @classmethod
    def generate_reset_token(cls, user):
        return cls._serializer().dumps({"user_id": user.id}, salt=RESET_SALT)

    @classmethod
    def verify_reset_token(cls, token):
        try:
            data = cls._serializer().loads(token, salt=RESET_SALT, max_age=RESET_TOKEN_MAX_AGE_SECONDS)
        except SignatureExpired:
            raise AuthError("This password reset link has expired.")
        except BadSignature:
            raise AuthError("This password reset link is invalid.")

        user = User.find(data.get("user_id"))
        if user is None:
            raise AuthError("This password reset link is invalid.")
        return user

    @staticmethod
    def reset_password(user, new_password):
        user.set_password(new_password)
        user.failed_login_attempts = 0
        user.locked_until = None
        user.put()
        logger.info("Password reset completed: user_id=%s", user.id)

    @staticmethod
    def change_password(user, current_password, new_password):
        if not user.check_password(current_password):
            raise AuthError("Current password is incorrect.")
        user.set_password(new_password)
        user.put()
        logger.info("Password changed: user_id=%s", user.id)
