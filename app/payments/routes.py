import logging

from flask import jsonify, render_template, request, url_for
from flask_login import current_user, login_required
from google.cloud import ndb

from app.extensions import limiter
from app.models import Order, OrderStatus, Payment, PaymentMethod, PaymentStatus
from app.payments import payments_bp
from app.payments.razorpay_service import RazorpayError, RazorpayService
from app.services.order_service import OrderService

logger = logging.getLogger("app.payments")


def _get_owned_pending_order(order_id):
    order = Order.find(order_id)
    if order is None or order.user_id != current_user.id:
        return None
    if order.payment_method != PaymentMethod.RAZORPAY:
        return None
    return order


@payments_bp.route("/payment/pay/<int:order_id>")
@login_required
def pay(order_id):
    order = _get_owned_pending_order(order_id)
    if order is None:
        return render_template("errors/404.html"), 404

    if order.order_status != OrderStatus.PENDING_PAYMENT:
        return render_template("payment_result.html", order=order)

    return render_template(
        "payment_checkout.html",
        order=order,
        razorpay_key_id=RazorpayService.public_key_id(),
    )


@payments_bp.route("/payment/razorpay/create-order", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def create_razorpay_order():
    data = request.get_json(silent=True) or {}
    order_id = data.get("order_id")
    order = _get_owned_pending_order(order_id) if order_id else None

    if order is None:
        return jsonify({"success": False, "message": "Order not found."}), 404
    if order.order_status != OrderStatus.PENDING_PAYMENT:
        return jsonify({"success": False, "message": "This order is not awaiting payment."}), 400

    try:
        result = RazorpayService.create_order(order)
    except RazorpayError as exc:
        return jsonify({"success": False, "message": str(exc)}), 502

    return jsonify(
        {
            "success": True,
            "key_id": RazorpayService.public_key_id(),
            "razorpay_order_id": result["razorpay_order_id"],
            "amount": result["amount_paise"],
            "currency": result["currency"],
            "order_number": order.order_number,
            "name": current_user.name,
            "email": current_user.email,
            "contact": current_user.phone or "",
        }
    )


@payments_bp.route("/payment/razorpay/verify", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def verify_razorpay_payment():
    data = request.get_json(silent=True) or {}
    order_id = data.get("order_id")
    razorpay_order_id = data.get("razorpay_order_id")
    razorpay_payment_id = data.get("razorpay_payment_id")
    razorpay_signature = data.get("razorpay_signature")

    if not all([order_id, razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        return jsonify({"success": False, "message": "Missing payment verification fields."}), 400

    order = _get_owned_pending_order(order_id)
    if order is None:
        return jsonify({"success": False, "message": "Order not found."}), 404

    if order.razorpay_order_id != razorpay_order_id:
        logger.warning("Razorpay order id mismatch on verify: order_id=%s", order_id)
        return jsonify({"success": False, "message": "Order mismatch."}), 400

    if order.payment_status == PaymentStatus.PAID:
        return jsonify({"success": True, "redirect": url_for("checkout.order_success", order_id=order.id)})

    try:
        RazorpayService.verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature)
    except RazorpayError as exc:
        payment = Payment.for_order(order.id, "razorpay")
        if payment:
            payment.status = "failed"
            payment.signature_verified = False
            payment.put()
        return jsonify({"success": False, "message": str(exc)}), 400

    order.razorpay_payment_id = razorpay_payment_id
    order.razorpay_signature = razorpay_signature
    to_put = [order]

    payment = Payment.for_order(order.id, "razorpay")
    if payment:
        payment.provider_payment_id = razorpay_payment_id
        payment.status = "paid"
        payment.signature_verified = True
        to_put.append(payment)

    ndb.put_multi(to_put)

    OrderService.mark_paid(order)

    return jsonify({"success": True, "redirect": url_for("checkout.order_success", order_id=order.id)})


@payments_bp.route("/payment/razorpay/failed", methods=["POST"])
@login_required
def razorpay_payment_failed():
    data = request.get_json(silent=True) or {}
    order_id = data.get("order_id")
    order = _get_owned_pending_order(order_id) if order_id else None
    if order is None:
        return jsonify({"success": False}), 404

    reason = (data.get("reason") or "Payment failed or cancelled by customer.").strip()[:500]

    # Only the attempt is recorded: the order stays pending_payment so the
    # customer can retry from this page or "Complete payment", or cancel it.
    if order.order_status == OrderStatus.PENDING_PAYMENT:
        payment = Payment.for_order(order.id, "razorpay")
        if payment:
            payment.status = "failed"
            payment.raw_reference = reason
            payment.put()
        logger.info("Razorpay attempt failed: order_number=%s reason=%s", order.order_number, reason)

    return jsonify({"success": True})
