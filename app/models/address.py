from google.cloud import ndb

from app.models.base import BaseModel


class Address(BaseModel):
    user_id = ndb.IntegerProperty(required=True)
    full_name = ndb.TextProperty(required=True)
    phone = ndb.TextProperty(required=True)
    address_line_1 = ndb.TextProperty(required=True)
    address_line_2 = ndb.TextProperty()
    city = ndb.TextProperty(required=True)
    state = ndb.TextProperty(required=True)
    postal_code = ndb.TextProperty(required=True)
    country = ndb.TextProperty(default="India")
    is_default = ndb.BooleanProperty(default=False)

    @classmethod
    def for_user(cls, user_id):
        """Default address first, then newest."""
        return sorted(cls.all(cls.user_id == user_id), key=lambda a: (not a.is_default, -a.id))

    @classmethod
    def owned_by(cls, address_id, user_id):
        address = cls.find(address_id)
        return address if address is not None and address.user_id == user_id else None

    @classmethod
    def clear_default(cls, user_id, except_id=None):
        others = [a for a in cls.all(cls.user_id == user_id, cls.is_default == True) if a.id != except_id]  # noqa: E712
        for a in others:
            a.is_default = False
        ndb.put_multi(others)

    @property
    def user(self):
        from app.models.user import User

        return User.find(self.user_id)

    def __repr__(self):
        return f"<Address {self.id} user={self.user_id}>"
