from datetime import datetime, timezone

from google.cloud import ndb

from app.models.base import ZERO, BaseModel, DecimalProperty, UTCDateTimeProperty


class DiscountType:
    PERCENT = "percent"
    FLAT = "flat"
    CHOICES = (PERCENT, FLAT)


class Coupon(BaseModel):
    code = ndb.StringProperty(required=True)
    discount_type = ndb.TextProperty(default=DiscountType.PERCENT)
    discount_value = DecimalProperty(required=True, indexed=False)
    minimum_order_value = DecimalProperty(default=ZERO, indexed=False)
    maximum_discount = DecimalProperty(indexed=False)
    start_at = UTCDateTimeProperty(indexed=False)
    expires_at = UTCDateTimeProperty(indexed=False)
    usage_limit = ndb.IntegerProperty(indexed=False)
    used_count = ndb.IntegerProperty(default=0, indexed=False)
    is_active = ndb.BooleanProperty(default=True)

    @classmethod
    def by_code(cls, code):
        return cls.first(cls.code == (code or "").strip().upper())

    def is_valid_now(self):
        from app.utils import as_aware_utc

        now = datetime.now(timezone.utc)
        if not self.is_active:
            return False
        if self.start_at and now < as_aware_utc(self.start_at):
            return False
        if self.expires_at and now > as_aware_utc(self.expires_at):
            return False
        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            return False
        return True

    def __repr__(self):
        return f"<Coupon {self.code}>"
