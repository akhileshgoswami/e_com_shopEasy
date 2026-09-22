from datetime import datetime, timezone

from app.extensions import db


class PaymentProvider:
    RAZORPAY = "razorpay"
    COD = "cod"


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = db.Column(db.String(30), nullable=False)
    provider_order_id = db.Column(db.String(64), nullable=True, index=True)
    provider_payment_id = db.Column(db.String(64), nullable=True, index=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    currency = db.Column(db.String(10), nullable=False, default="INR")
    status = db.Column(db.String(20), nullable=False, default="pending")
    signature_verified = db.Column(db.Boolean, nullable=False, default=False)
    raw_reference = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    order = db.relationship("Order", back_populates="payments")

    def __repr__(self):
        return f"<Payment {self.id} order={self.order_id} status={self.status}>"


class WebhookEvent(db.Model):
    """Tracks processed Razorpay webhook event ids for idempotency."""

    __tablename__ = "webhook_events"

    id = db.Column(db.Integer, primary_key=True)
    provider = db.Column(db.String(30), nullable=False, default="razorpay")
    event_id = db.Column(db.String(128), nullable=False, unique=True, index=True)
    event_type = db.Column(db.String(100), nullable=False)
    payload = db.Column(db.Text, nullable=True)
    processed_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def __repr__(self):
        return f"<WebhookEvent {self.event_id}>"
