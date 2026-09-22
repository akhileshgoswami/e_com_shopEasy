import logging

from flask import current_app, jsonify, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db, limiter
from app.models import Order, OrderStatus, Payment, PaymentMethod, PaymentStatus
from app.payments import payments_bp
from app.payments.razorpay_service import RazorpayError, RazorpayService
from app.services.order_service import OrderService

logger = logging.getLogger("app.payments")


def _get_owned_pending_order(order_id):
    order = Order.query.filter_by(id=order_id, user_id=current_user.id).first()
    if order is None:
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
        razorpay_key_id=current_app.config.get("RAZORPAY_KEY_ID"),
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
            "key_id": current_app.config.get("RAZORPAY_KEY_ID"),
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
        payment = Payment.query.filter_by(order_id=order.id, provider="razorpay").first()
        if payment:
            payment.status = "failed"
            payment.signature_verified = False
            db.session.commit()
        return jsonify({"success": False, "message": str(exc)}), 400

    payment = Payment.query.filter_by(order_id=order.id, provider="razorpay").first()
    if payment:
        payment.provider_payment_id = razorpay_payment_id
        payment.status = "paid"
        payment.signature_verified = True

    order.razorpay_payment_id = razorpay_payment_id
    order.razorpay_signature = razorpay_signature
    db.session.commit()

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

    if order.order_status == OrderStatus.PENDING_PAYMENT:
        payment = Payment.query.filter_by(order_id=order.id, provider="razorpay").first()
        if payment:
            payment.status = "failed"
            payment.raw_reference = reason
            db.session.commit()
        OrderService.mark_payment_failed(order, note=reason)

    return jsonify({"success": True})
