import logging
import random
import string
from datetime import datetime, timezone
from decimal import Decimal

from flask import current_app

from app.cart.services import CartService
from app.extensions import db
from app.models import (
    Order,
    OrderItem,
    OrderStatus,
    OrderStatusHistory,
    Payment,
    PaymentMethod,
    PaymentStatus,
)
from app.services.coupon_service import CouponError, CouponService
from app.services.email_service import EmailService
from app.services.inventory_service import InsufficientStockError, InventoryService

logger = logging.getLogger("app.checkout")


class CheckoutError(Exception):
    pass


def _generate_order_number():
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    for _ in range(10):
        suffix = "".join(random.choices(string.digits + string.ascii_uppercase, k=6))
        candidate = f"ORD-{today}-{suffix}"
        if not Order.query.filter_by(order_number=candidate).first():
            return candidate
    raise CheckoutError("Could not generate a unique order number, please retry.")


class CheckoutService:
    @staticmethod
    def build_summary(user, coupon_code=None):
        """Read-only server-side computation used to render the checkout page.
        Never trusts any client-provided price."""
        cart = CartService.get_or_create_cart(user)
        adjustments = CartService.sync_cart(cart)

        subtotal = sum((item.subtotal for item in cart.items), Decimal("0.00"))

        discount = Decimal("0.00")
        coupon = None
        coupon_error = None
        if coupon_code:
            try:
                coupon = CouponService.get_valid_coupon(coupon_code)
                discount = CouponService.calculate_discount(coupon, subtotal)
            except CouponError as exc:
                coupon_error = str(exc)

        shipping_charge = CheckoutService._shipping_charge(subtotal - discount)
        tax = CheckoutService._tax(subtotal - discount)
        total = subtotal - discount + shipping_charge + tax

        return {
            "cart": cart,
            "adjustments": adjustments,
            "subtotal": subtotal,
            "discount": discount,
            "coupon": coupon,
            "coupon_error": coupon_error,
            "shipping_charge": shipping_charge,
            "tax": tax,
            "total": total,
        }

    @staticmethod
    def _shipping_charge(taxable_subtotal):
        threshold = Decimal(str(current_app.config["FREE_SHIPPING_THRESHOLD"]))
        if taxable_subtotal >= threshold:
            return Decimal("0.00")
        return Decimal(str(current_app.config["DEFAULT_SHIPPING_CHARGE"]))

    @staticmethod
    def _tax(taxable_subtotal):
        rate = Decimal(str(current_app.config["TAX_RATE_PERCENT"]))
        return (taxable_subtotal * rate / Decimal("100")).quantize(Decimal("0.01"))

    @classmethod
    def create_order(cls, user, address, payment_method, coupon_code=None, notes=None):
        if payment_method not in PaymentMethod.CHOICES:
            raise CheckoutError("Invalid payment method.")

        cart = CartService.get_or_create_cart(user)
        adjustments = CartService.sync_cart(cart)
        if not cart.items:
            raise CheckoutError("Your cart is empty.")

        summary = cls.build_summary(user, coupon_code=coupon_code)
        if summary["coupon_error"]:
            raise CheckoutError(summary["coupon_error"])

        cart_snapshot = [
            {"product_id": i.product_id, "product": i.product, "quantity": i.quantity, "unit_price": i.unit_price}
            for i in cart.items
        ]

        try:
            order = Order(
                user_id=user.id,
                order_number=_generate_order_number(),
                subtotal=summary["subtotal"],
                discount=summary["discount"],
                shipping_charge=summary["shipping_charge"],
                tax=summary["tax"],
                total_amount=summary["total"],
                coupon_code=summary["coupon"].code if summary["coupon"] else None,
                payment_method=payment_method,
                payment_status=PaymentStatus.PENDING,
                order_status=(
                    OrderStatus.PLACED if payment_method == PaymentMethod.COD else OrderStatus.PENDING_PAYMENT
                ),
                shipping_name=address.full_name,
                shipping_phone=address.phone,
                shipping_address=address.address_line_1
                + (f", {address.address_line_2}" if address.address_line_2 else ""),
                shipping_city=address.city,
                shipping_state=address.state,
                shipping_postal_code=address.postal_code,
                shipping_country=address.country,
                notes=notes,
            )
            db.session.add(order)
            db.session.flush()

            for line in cart_snapshot:
                product = line["product"]
                InventoryService.reserve_stock(product.id, line["quantity"])
                db.session.add(
                    OrderItem(
                        order_id=order.id,
                        product_id=product.id,
                        product_name=product.name,
                        sku=product.sku,
                        quantity=line["quantity"],
                        unit_price=line["unit_price"],
                        subtotal=line["unit_price"] * line["quantity"],
                    )
                )
            order.stock_committed = True

            db.session.add(
                Payment(
                    order_id=order.id,
                    provider="cod" if payment_method == PaymentMethod.COD else "razorpay",
                    amount=order.total_amount,
                    currency="INR",
                    status="pending",
                )
            )

            db.session.add(
                OrderStatusHistory(
                    order_id=order.id,
                    old_status=None,
                    new_status=order.order_status,
                    changed_by=user.email,
                    note="Order created.",
                )
            )

            if summary["coupon"]:
                CouponService.redeem(summary["coupon"])

            CartService.clear(cart)

            db.session.commit()
        except InsufficientStockError as exc:
            db.session.rollback()
            logger.warning("Order creation failed for insufficient stock: user_id=%s product=%s", user.id, exc.product.id)
            raise CheckoutError(str(exc)) from exc
        except Exception:
            db.session.rollback()
            logger.exception("Order creation failed unexpectedly: user_id=%s", user.id)
            raise

        logger.info("Order created: order_number=%s user_id=%s method=%s", order.order_number, user.id, payment_method)

        if payment_method == PaymentMethod.COD:
            EmailService.send_order_confirmation(order)

        return order
