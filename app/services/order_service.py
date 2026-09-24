import logging

from flask import abort
from google.cloud import ndb

from app.models import Order, OrderStatus, OrderStatusHistory, Payment, PaymentMethod, PaymentStatus, Product
from app.services.email_service import EmailService
from app.services.inventory_service import InventoryService
from app.utils import Pagination, newest_first

logger = logging.getLogger("app.orders")


class OrderTransitionError(Exception):
    pass


class PaymentCollectionError(Exception):
    pass


class OrderService:
    @staticmethod
    def get_user_order_or_404(user, order_id):
        order = Order.find(order_id)
        if order is None or order.user_id != user.id:
            abort(404)
        return order

    @staticmethod
    def list_user_orders(user, page=1, per_page=10):
        return Pagination(newest_first(Order.all(Order.user_id == user.id)), page, per_page)

    @classmethod
    def change_status(cls, order, new_status, changed_by, note=None, force=False):
        """Returns the updated order. The transition is validated against
        the order as re-read inside the transaction, so two admins acting
        at once can't both restore the same stock."""
        if new_status not in OrderStatus.CHOICES:
            raise OrderTransitionError(f"Unknown status '{new_status}'.")

        # Order lines never change after checkout, so read them up front:
        # transactions should only do key lookups.
        items = [item for item in order.items if item.product_id]

        def txn():
            current = order.key.get()
            old_status = current.order_status
            allowed = OrderStatus.TRANSITIONS.get(old_status, ())
            if not force and new_status != old_status and new_status not in allowed:
                raise OrderTransitionError(f"Cannot move order from '{old_status}' to '{new_status}'.")
            if old_status == new_status:
                return current, None

            to_put = [current]
            if new_status in OrderStatus.STOCK_RESTORING and current.stock_committed:
                products = ndb.get_multi([ndb.Key(Product, item.product_id) for item in items])
                for item, product in zip(items, products):
                    if product is not None:
                        InventoryService.return_stock(product, item.quantity)
                        to_put.append(product)
                current.stock_committed = False

            current.order_status = new_status
            to_put.append(
                OrderStatusHistory(
                    order_id=current.id, old_status=old_status, new_status=new_status, changed_by=changed_by, note=note
                )
            )
            ndb.put_multi(to_put)
            return current, old_status

        updated, old_status = ndb.transaction(txn)
        if old_status is None:
            return updated

        logger.info("Order status changed: order_number=%s %s -> %s by=%s", updated.order_number, old_status, new_status, changed_by)
        EmailService.send_order_status_update(updated)
        return updated

    @classmethod
    def mark_payment_failed(cls, order, note="Payment failed."):
        order.payment_status = PaymentStatus.FAILED
        order.put()
        return cls.change_status(order, OrderStatus.FAILED, changed_by="system", note=note, force=True)

    @classmethod
    def mark_paid(cls, order):
        if order.payment_status == PaymentStatus.PAID:
            return order

        order.payment_status = PaymentStatus.PAID
        order.put()
        if order.order_status == OrderStatus.PENDING_PAYMENT:
            order = cls.change_status(order, OrderStatus.PLACED, changed_by="system", note="Payment verified.", force=True)
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
        to_put = [
            order,
            OrderStatusHistory(
                order_id=order.id,
                old_status=order.order_status,
                new_status=order.order_status,
                changed_by=changed_by,
                note=note or "Cash payment collected.",
            ),
        ]
        payment = Payment.for_order(order.id, "cod")
        if payment:
            payment.status = "paid"
            to_put.append(payment)
        ndb.put_multi(to_put)

        logger.info("COD payment collected: order_number=%s by=%s", order.order_number, changed_by)
        EmailService.send_payment_confirmation(order)
        return order
