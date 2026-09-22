from datetime import datetime, timezone

from app.extensions import db


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


def _now():
    return datetime.now(timezone.utc)


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    order_number = db.Column(db.String(32), nullable=False, unique=True, index=True)

    subtotal = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    discount = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    shipping_charge = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    tax = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False, default=0)

    coupon_code = db.Column(db.String(50), nullable=True)

    payment_method = db.Column(db.String(20), nullable=False)
    payment_status = db.Column(db.String(20), nullable=False, default=PaymentStatus.PENDING)
    order_status = db.Column(db.String(30), nullable=False, default=OrderStatus.PENDING_PAYMENT)

    stock_committed = db.Column(db.Boolean, nullable=False, default=False)

    shipping_name = db.Column(db.String(120), nullable=False)
    shipping_phone = db.Column(db.String(20), nullable=False)
    shipping_address = db.Column(db.String(255), nullable=False)
    shipping_city = db.Column(db.String(100), nullable=False)
    shipping_state = db.Column(db.String(100), nullable=False)
    shipping_postal_code = db.Column(db.String(20), nullable=False)
    shipping_country = db.Column(db.String(100), nullable=False, default="India")

    razorpay_order_id = db.Column(db.String(64), nullable=True, index=True)
    razorpay_payment_id = db.Column(db.String(64), nullable=True, index=True)
    razorpay_signature = db.Column(db.String(255), nullable=True)

    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    user = db.relationship("User", back_populates="orders")
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payments = db.relationship("Payment", back_populates="order", cascade="all, delete-orphan")
    status_history = db.relationship(
        "OrderStatusHistory", back_populates="order", cascade="all, delete-orphan",
        order_by="OrderStatusHistory.created_at",
    )

    def __repr__(self):
        return f"<Order {self.order_number}>"


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=True, index=True)
    product_name = db.Column(db.String(200), nullable=False)
    sku = db.Column(db.String(64), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False)

    order = db.relationship("Order", back_populates="items")
    product = db.relationship("Product")

    def __repr__(self):
        return f"<OrderItem {self.id} order={self.order_id}>"


class OrderStatusHistory(db.Model):
    __tablename__ = "order_status_history"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    old_status = db.Column(db.String(30), nullable=True)
    new_status = db.Column(db.String(30), nullable=False)
    changed_by = db.Column(db.String(120), nullable=True)
    note = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=_now, nullable=False)

    order = db.relationship("Order", back_populates="status_history")

    def __repr__(self):
        return f"<OrderStatusHistory order={self.order_id} {self.old_status}->{self.new_status}>"
