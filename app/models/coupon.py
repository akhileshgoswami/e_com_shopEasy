from datetime import datetime, timezone

from app.extensions import db


class DiscountType:
    PERCENT = "percent"
    FLAT = "flat"
    CHOICES = (PERCENT, FLAT)


class Coupon(db.Model):
    __tablename__ = "coupons"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), nullable=False, unique=True, index=True)
    discount_type = db.Column(db.String(10), nullable=False, default=DiscountType.PERCENT)
    discount_value = db.Column(db.Numeric(10, 2), nullable=False)
    minimum_order_value = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    maximum_discount = db.Column(db.Numeric(10, 2), nullable=True)
    start_at = db.Column(db.DateTime(timezone=True), nullable=True)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=True)
    usage_limit = db.Column(db.Integer, nullable=True)
    used_count = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

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
