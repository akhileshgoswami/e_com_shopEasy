from flask_login import UserMixin
from google.cloud import ndb
from werkzeug.security import check_password_hash, generate_password_hash

from app.models.base import BaseModel, UTCDateTimeProperty


class Role:
    ADMIN = "admin"
    CUSTOMER = "customer"
    CHOICES = (ADMIN, CUSTOMER)


class User(UserMixin, BaseModel):
    name = ndb.StringProperty(required=True)
    email = ndb.StringProperty(required=True)
    phone = ndb.StringProperty()
    password_hash = ndb.TextProperty(required=True)
    role = ndb.StringProperty(default=Role.CUSTOMER)
    is_active = ndb.BooleanProperty(default=True)
    last_login_at = UTCDateTimeProperty()

    failed_login_attempts = ndb.IntegerProperty(default=0, indexed=False)
    locked_until = UTCDateTimeProperty(indexed=False)
    # Bumped on every password change/reset. It is part of the Flask-Login
    # id, so sessions and "remember me" cookies issued before the change
    # stop working everywhere at once.
    session_version = ndb.IntegerProperty(default=0, indexed=False)
    password_changed_at = UTCDateTimeProperty(indexed=False)

    @classmethod
    def by_email(cls, email):
        return cls.first(cls.email == (email or "").strip().lower())

    @property
    def addresses(self):
        from app.models.address import Address

        return Address.all(Address.user_id == self.id)

    @property
    def cart(self):
        from app.models.cart import Cart

        return Cart.get_by_id(self.id)

    @property
    def orders(self):
        from app.models.order import Order

        return Order.all(Order.user_id == self.id)

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    @property
    def is_admin(self):
        return self.role == Role.ADMIN

    def revoke_sessions(self):
        self.session_version = (self.session_version or 0) + 1

    def get_id(self):
        # Accounts that never changed their password keep the plain id, so
        # existing sessions survive this field being introduced.
        if self.session_version:
            return f"{self.id}:{self.session_version}"
        return str(self.id)

    @classmethod
    def from_session_id(cls, session_id):
        """Inverse of get_id(): None when the id is malformed, the user is
        gone, or the password changed since the session was issued."""
        raw_id, _, version = str(session_id or "").partition(":")
        try:
            version = int(version or 0)
        except ValueError:
            return None
        user = cls.find(raw_id)
        if user is None or version != (user.session_version or 0):
            return None
        return user

    def __repr__(self):
        return f"<User {self.email}>"
