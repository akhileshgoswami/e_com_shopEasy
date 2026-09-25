import logging
import random
import string
from datetime import datetime
from decimal import Decimal

from google.cloud import ndb

from app.cart.services import CartError, CartService
from app.models import (
    CartItem,
    Coupon,
    Order,
    OrderItem,
    OrderStatus,
    OrderStatusHistory,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Product,
)
from app.services.coupon_service import CouponError, CouponService
from app.services.email_service import EmailService
from app.services.inventory_service import InsufficientStockError, InventoryService
from app.services.payment_settings_service import PaymentSettingsService
from app.services.site_content_service import StorefrontService
from app.utils import IST

logger = logging.getLogger("app.checkout")


class CheckoutError(Exception):
    pass


def _generate_order_number():
    # India date, so an order at 1 AM IST isn't stamped with yesterday.
    today = datetime.now(IST).strftime("%Y%m%d")
    for _ in range(10):
        suffix = "".join(random.choices(string.digits + string.ascii_uppercase, k=6))
        candidate = f"ORD-{today}-{suffix}"
        if not Order.first(Order.order_number == candidate):
            return candidate
    raise CheckoutError("Could not generate a unique order number, please retry.")


def _buy_now_line(user, buy_now):
    """A single unsaved cart line for "Buy now", re-validated against live
    product state like sync_cart() does for real cart lines. Returns
    (items, adjustment_messages)."""
    product = Product.find(buy_now.get("product_id"))
    if product is None or not product.is_active:
        return [], ["This product is no longer available."]
    try:
        size = CartService.resolve_size(product, buy_now.get("size"))
    except CartError as exc:
        return [], [str(exc)]
    label = CartService.line_label(product, size)
    available = product.stock_for(size)
    if available <= 0:
        return [], [f"{label} is out of stock."]
    quantity = max(1, int(buy_now.get("quantity") or 1))
    messages = []
    if quantity > available:
        messages.append(f"Quantity for {label} was reduced to {available} (limited stock).")
        quantity = available
    line = CartItem(
        cart_id=user.id, product_id=product.id, size=size, quantity=quantity, unit_price=product.effective_price
    )
    return [line], messages


class CheckoutService:
    @staticmethod
    def build_summary(user, coupon_code=None, buy_now=None):
        """Read-only server-side computation used to render the checkout page.
        Never trusts any client-provided price. With buy_now
        ({"product_id", "quantity"}) only that product is checked out and
        the cart is left alone."""
        cart = CartService.get_or_create_cart(user)
        if buy_now:
            items, adjustments = _buy_now_line(user, buy_now)
        else:
            adjustments = CartService.sync_cart(cart)
            items = cart.items

        subtotal = sum((item.subtotal for item in items), Decimal("0.00"))

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
            "cart_items": items,
            "buy_now": bool(buy_now),
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
        rules = StorefrontService.get()
        if taxable_subtotal >= rules["free_shipping_threshold"]:
            return Decimal("0.00")
        return rules["shipping_charge"]

    @staticmethod
    def _tax(taxable_subtotal):
        rate = StorefrontService.get()["tax_rate_percent"]
        return (taxable_subtotal * rate / Decimal("100")).quantize(Decimal("0.01"))

    @classmethod
    def create_order(cls, user, address, payment_method, coupon_code=None, notes=None, buy_now=None):
        if payment_method not in PaymentSettingsService.enabled_methods():
            raise CheckoutError("This payment method is not available right now.")

        summary = cls.build_summary(user, coupon_code=coupon_code, buy_now=buy_now)
        cart_items = summary["cart_items"]
        if not cart_items:
            if buy_now and summary["adjustments"]:
                raise CheckoutError(summary["adjustments"][0])
            raise CheckoutError("Your cart is empty.")
        if summary["coupon_error"]:
            raise CheckoutError(summary["coupon_error"])

        coupon = summary["coupon"]
        order_number = _generate_order_number()
        # Allocate the id up front so every child row can reference it
        # inside the transaction.
        order_key = Order.allocate_ids(1)[0]

        def txn():
            # Re-read stock (and the coupon) inside the transaction: if a
            # concurrent checkout touched the same product, Datastore aborts
            # one commit and this runs again on fresh values.
            # One entity per product: two sizes of the same product are two
            # lines, and both must decrement the same entity before it's put.
            product_ids = list(dict.fromkeys(item.product_id for item in cart_items))
            fetched = ndb.get_multi([ndb.Key(Product, pid) for pid in product_ids])
            products_by_id = dict(zip(product_ids, fetched))
            order = Order(
                key=order_key,
                user_id=user.id,
                order_number=order_number,
                subtotal=summary["subtotal"],
                discount=summary["discount"],
                shipping_charge=summary["shipping_charge"],
                tax=summary["tax"],
                total_amount=summary["total"],
                coupon_code=coupon.code if coupon else None,
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
                stock_committed=True,
            )
            to_put = [order]

            for item in cart_items:
                product = products_by_id.get(item.product_id)
                if product is None or not product.is_active:
                    raise CheckoutError("An item in your cart is no longer available.")
                if product.has_sizes and product.get_size(item.size) is None:
                    raise CheckoutError(f"The selected size of '{product.name}' is no longer available.")
                size = item.size if product.has_sizes else None
                InventoryService.take_stock(product, item.quantity, size)
                to_put.append(
                    OrderItem(
                        order_id=order.id,
                        product_id=product.id,
                        product_name=product.name,
                        sku=product.sku,
                        size=size,
                        quantity=item.quantity,
                        unit_price=item.unit_price,
                        subtotal=item.unit_price * item.quantity,
                    )
                )

            to_put.extend(p for p in products_by_id.values() if p is not None)

            to_put.append(
                Payment(
                    order_id=order.id,
                    provider="cod" if payment_method == PaymentMethod.COD else "razorpay",
                    amount=order.total_amount,
                    currency="INR",
                    status="pending",
                )
            )
            to_put.append(
                OrderStatusHistory(
                    order_id=order.id,
                    old_status=None,
                    new_status=order.order_status,
                    changed_by=user.email,
                    note="Order created.",
                )
            )

            if coupon:
                fresh_coupon = Coupon.get_by_id(coupon.id)
                CouponService.redeem(fresh_coupon)
                to_put.append(fresh_coupon)

            ndb.put_multi(to_put)
            # Buy-now lines were never saved, so the rest of the cart stays put.
            ndb.delete_multi([item.key for item in cart_items if item.key])
            return order

        try:
            order = ndb.transaction(txn)
        except InsufficientStockError as exc:
            logger.warning("Order creation failed for insufficient stock: user_id=%s product=%s", user.id, exc.product.id)
            raise CheckoutError(str(exc)) from exc
        except CouponError as exc:
            raise CheckoutError(str(exc)) from exc
        except CheckoutError:
            raise
        except Exception:
            logger.exception("Order creation failed unexpectedly: user_id=%s", user.id)
            raise

        logger.info("Order created: order_number=%s user_id=%s method=%s", order.order_number, user.id, payment_method)

        # Online orders are confirmed only once Razorpay payment is verified
        # (OrderService.mark_paid); a COD order is real as soon as it commits.
        if payment_method == PaymentMethod.COD:
            EmailService.send_new_order_notifications(order)

        return order
