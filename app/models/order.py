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
        DELIVERED,
        CANCELLED,
        FAILED,
        RETURNED,
        REFUNDED,
    )

    # statuses from which inventory that was already decremented should be restored
    STOCK_RESTORING = (CANCELLED, FAILED, RETURNED)
    TERMINAL = (DELIVERED, CANCELLED, FAILED, RETURNED, REFUNDED)

    # allowed forward transitions for admin-driven status changes
    TRANSITIONS = {
        PENDING_PAYMENT: (PLACED, FAILED, CANCELLED),
        PLACED: (CONFIRMED, PROCESSING, CANCELLED, FAILED),
        CONFIRMED: (PROCESSING, CANCELLED),
        PROCESSING: (PACKED, CANCELLED),
        PACKED: (SHIPPED, CANCELLED),
        SHIPPED: (DELIVERED, RETURNED),
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
