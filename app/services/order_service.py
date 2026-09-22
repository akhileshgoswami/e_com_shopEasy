import logging

from app.extensions import db
from app.models import Order, OrderStatus, OrderStatusHistory, Payment, PaymentMethod, PaymentStatus
from app.services.email_service import EmailService
from app.services.inventory_service import InventoryService

logger = logging.getLogger("app.orders")


class OrderTransitionError(Exception):
    pass


class PaymentCollectionError(Exception):
    pass


class OrderService:
    @staticmethod
    def get_user_order_or_404(user, order_id):
        return Order.query.filter_by(id=order_id, user_id=user.id).first_or_404()

    @staticmethod
    def list_user_orders(user, page=1, per_page=10):
        return (
            Order.query.filter_by(user_id=user.id)
            .order_by(Order.created_at.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
        )

    @classmethod
    def change_status(cls, order, new_status, changed_by, note=None, force=False):
        if new_status not in OrderStatus.CHOICES:
            raise OrderTransitionError(f"Unknown status '{new_status}'.")

        allowed = OrderStatus.TRANSITIONS.get(order.order_status, ())
        if not force and new_status != order.order_status and new_status not in allowed:
            raise OrderTransitionError(
                f"Cannot move order from '{order.order_status}' to '{new_status}'."
            )

        old_status = order.order_status
        if old_status == new_status:
            return order

        if new_status in OrderStatus.STOCK_RESTORING and order.stock_committed:
            for item in order.items:
                if item.product_id:
                    InventoryService.restore_stock(item.product_id, item.quantity)
            order.stock_committed = False

        order.order_status = new_status
        db.session.add(
            OrderStatusHistory(order_id=order.id, old_status=old_status, new_status=new_status, changed_by=changed_by, note=note)
        )
        db.session.commit()

        logger.info("Order status changed: order_number=%s %s -> %s by=%s", order.order_number, old_status, new_status, changed_by)
        EmailService.send_order_status_update(order)
        return order

    @classmethod
    def mark_payment_failed(cls, order, note="Payment failed."):
        order.payment_status = PaymentStatus.FAILED
        cls.change_status(order, OrderStatus.FAILED, changed_by="system", note=note, force=True)
        return order

    @classmethod
    def mark_paid(cls, order):
        if order.payment_status == PaymentStatus.PAID:
            return order

        order.payment_status = PaymentStatus.PAID
        db.session.commit()
        if order.order_status == OrderStatus.PENDING_PAYMENT:
            cls.change_status(order, OrderStatus.PLACED, changed_by="system", note="Payment verified.", force=True)
        EmailService.send_payment_confirmation(order)
        return order

    @classmethod
    def mark_cod_payment_collected(cls, order, changed_by, note=None):
        """Record that cash was collected for a COD order — typically once
        it's delivered, but admins may also collect at handoff time. This
        only updates payment_status; it never touches order_status/inventory,
        since those are driven by change_status()."""
        if order.payment_method != PaymentMethod.COD:
            raise PaymentCollectionError("Only Cash on Delivery orders can be marked as collected here.")
        if order.payment_status == PaymentStatus.PAID:
            return order
        if order.order_status in OrderStatus.STOCK_RESTORING:
            raise PaymentCollectionError(
                f"Cannot collect payment for an order that is '{order.order_status}'."
            )

        order.payment_status = PaymentStatus.PAID
        db.session.commit()

        payment = Payment.query.filter_by(order_id=order.id, provider="cod").first()
        if payment:
            payment.status = "paid"
            db.session.commit()

        db.session.add(
            OrderStatusHistory(
                order_id=order.id,
                old_status=order.order_status,
                new_status=order.order_status,
                changed_by=changed_by,
                note=note or "Cash payment collected.",
            )
        )
        db.session.commit()

        logger.info("COD payment collected: order_number=%s by=%s", order.order_number, changed_by)
        EmailService.send_payment_confirmation(order)
        return order
