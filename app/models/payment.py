from google.cloud import ndb

from app.models.base import BaseModel, DecimalProperty, UTCDateTimeProperty


class PaymentProvider:
    RAZORPAY = "razorpay"
    COD = "cod"


class Payment(BaseModel):
    order_id = ndb.IntegerProperty(required=True)
    provider = ndb.StringProperty(required=True)
    provider_order_id = ndb.StringProperty()
    provider_payment_id = ndb.StringProperty()
    amount = DecimalProperty(required=True, indexed=False)
    currency = ndb.TextProperty(default="INR")
    status = ndb.StringProperty(default="pending")
    signature_verified = ndb.BooleanProperty(default=False, indexed=False)
    raw_reference = ndb.TextProperty()

    @classmethod
    def for_order(cls, order_id, provider):
        return cls.first(cls.order_id == order_id, cls.provider == provider)

    @property
    def order(self):
        from app.models.order import Order

        return Order.find(self.order_id)

    def __repr__(self):
        return f"<Payment {self.id} order={self.order_id} status={self.status}>"


class WebhookEvent(BaseModel):
    """Processed Razorpay webhook event ids, for idempotency. The entity id
    is the provider's event id, so "already processed?" is a key lookup."""

    provider = ndb.StringProperty(default="razorpay")
    event_type = ndb.StringProperty(required=True)
    payload = ndb.TextProperty()
    processed_at = UTCDateTimeProperty(auto_now_add=True)

    @property
    def event_id(self):
        return self.key.id() if self.key else None

    def __repr__(self):
        return f"<WebhookEvent {self.event_id}>"
