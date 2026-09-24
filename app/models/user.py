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

    def get_id(self):
        return str(self.id)

    def __repr__(self):
        return f"<User {self.email}>"
