from google.cloud import ndb

from app.models.base import ZERO, BaseModel, DecimalProperty


class PaymentMethod:
    COD = "cod"
    RAZORPAY = "razorpay"
    CHOICES = (COD, RAZORPAY)


class PaymentStatus:
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"
    CHOICES = (PENDING, PAID, FAILED, REFUNDED)


class OrderStatus:
    PENDING_PAYMENT = "pending_payment"
    PLACED = "placed"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    PACKED = "packed"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    FAILED = "failed"
    RETURNED = "returned"
    REFUNDED = "refunded"

    CHOICES = (
        PENDING_PAYMENT,
        PLACED,
        CONFIRMED,
        PROCESSING,
        PACKED,
        SHIPPED,
        OUT_FOR_DELIVERY,
        DELIVERED,
        CANCELLED,
        FAILED,
        RETURNED,
        REFUNDED,
    )

    # statuses from which inventory that was already decremented should be restored
    STOCK_RESTORING = (CANCELLED, FAILED, RETURNED)
    TERMINAL = (DELIVERED, CANCELLED, FAILED, RETURNED, REFUNDED)

    # a customer can cancel on their own until the order is being packed
    CUSTOMER_CANCELLABLE = (PENDING_PAYMENT, PLACED, CONFIRMED)

    # preset reasons offered when cancelling; the first is pre-selected and
    # "Other" asks for the customer's own words
    OTHER_REASON = "Other"
    CANCEL_REASONS = (
        "Ordered by mistake",
        "Found a better price elsewhere",
        "Delivery is taking too long",
        "Want to change size, colour or quantity",
        "Want to change the delivery address",
        "Changed my mind",
        OTHER_REASON,
    )
    ADMIN_CANCEL_REASONS = (
        "Customer requested cancellation",
        "Item out of stock",
        "Unable to deliver to this address",
        "Customer unreachable for confirmation",
        "Suspected fraudulent order",
        "Payment not received",
        OTHER_REASON,
    )

    LABELS = {
        PENDING_PAYMENT: "Awaiting payment",
        PLACED: "Placed",
        CONFIRMED: "Confirmed",
        PROCESSING: "Processing",
        PACKED: "Packed",
        SHIPPED: "Shipped",
        OUT_FOR_DELIVERY: "Out for delivery",
        DELIVERED: "Delivered",
        CANCELLED: "Cancelled",
        FAILED: "Failed",
        RETURNED: "Returned",
        REFUNDED: "Refunded",
    }

    @classmethod
    def label(cls, status):
        return cls.LABELS.get(status) or (status or "").replace("_", " ").title()

    # allowed forward transitions for admin-driven status changes
    TRANSITIONS = {
        PENDING_PAYMENT: (PLACED, FAILED, CANCELLED),
        PLACED: (CONFIRMED, PROCESSING, CANCELLED, FAILED),
        CONFIRMED: (PROCESSING, CANCELLED),
        PROCESSING: (PACKED, CANCELLED),
        PACKED: (SHIPPED, CANCELLED),
        SHIPPED: (OUT_FOR_DELIVERY, DELIVERED, RETURNED),
        OUT_FOR_DELIVERY: (DELIVERED, RETURNED),
        DELIVERED: (RETURNED,),
        CANCELLED: (),
        FAILED: (PLACED,),
        RETURNED: (REFUNDED,),
        REFUNDED: (),
    }


class Order(BaseModel):
    user_id = ndb.IntegerProperty(required=True)
    order_number = ndb.StringProperty(required=True)

    subtotal = DecimalProperty(default=ZERO, indexed=False)
    discount = DecimalProperty(default=ZERO, indexed=False)
    shipping_charge = DecimalProperty(default=ZERO, indexed=False)
    tax = DecimalProperty(default=ZERO, indexed=False)
    total_amount = DecimalProperty(default=ZERO)

    coupon_code = ndb.StringProperty()

    payment_method = ndb.StringProperty(required=True)
    payment_status = ndb.StringProperty(default=PaymentStatus.PENDING)
    order_status = ndb.StringProperty(default=OrderStatus.PENDING_PAYMENT)

    stock_committed = ndb.BooleanProperty(default=False)

    shipping_name = ndb.TextProperty(required=True)
    shipping_phone = ndb.TextProperty(required=True)
    shipping_address = ndb.TextProperty(required=True)
    shipping_city = ndb.TextProperty(required=True)
    shipping_state = ndb.TextProperty(required=True)
    shipping_postal_code = ndb.TextProperty(required=True)
    shipping_country = ndb.TextProperty(default="India")

    razorpay_order_id = ndb.StringProperty()
    razorpay_payment_id = ndb.StringProperty()
    razorpay_signature = ndb.TextProperty()

    notes = ndb.TextProperty()

    # Filled in by an admin when the parcel ships; all optional.
    tracking_number = ndb.TextProperty()
    tracking_url = ndb.TextProperty()
    estimated_delivery_date = ndb.DateProperty(indexed=False)

    @property
    def user(self):
        from app.models.user import User

        return User.find(self.user_id)

    @property
    def items(self):
        return OrderItem.all(OrderItem.order_id == self.id)

    @property
    def payments(self):
        from app.models.payment import Payment

        return Payment.all(Payment.order_id == self.id)

    @property
    def status_history(self):
        return sorted(OrderStatusHistory.all(OrderStatusHistory.order_id == self.id), key=lambda h: h.created_at)

    def __repr__(self):
        return f"<Order {self.order_number}>"


class OrderItem(BaseModel):
    order_id = ndb.IntegerProperty(required=True)
    product_id = ndb.IntegerProperty()
    product_name = ndb.TextProperty(required=True)
    sku = ndb.TextProperty(required=True)
    size = ndb.TextProperty()
    quantity = ndb.IntegerProperty(required=True, indexed=False)
    unit_price = DecimalProperty(required=True, indexed=False)
    subtotal = DecimalProperty(required=True, indexed=False)

    @property
    def order(self):
        return Order.find(self.order_id)

    @property
    def product(self):
        from app.models.product import Product

        return Product.find(self.product_id)

    def __repr__(self):
        return f"<OrderItem {self.id} order={self.order_id}>"


class OrderStatusHistory(BaseModel):
    order_id = ndb.IntegerProperty(required=True)
    old_status = ndb.TextProperty()
    new_status = ndb.TextProperty(required=True)
    changed_by = ndb.TextProperty()
    note = ndb.TextProperty()

    @property
    def order(self):
        return Order.find(self.order_id)

    def __repr__(self):
        return f"<OrderStatusHistory order={self.order_id} {self.old_status}->{self.new_status}>"
