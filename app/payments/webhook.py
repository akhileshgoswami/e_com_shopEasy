import hashlib
import json
import logging

from flask import request

from app.extensions import csrf, db
from app.models import Order, Payment, WebhookEvent
from app.payments import payments_bp
from app.payments.razorpay_service import RazorpayError, RazorpayService
from app.services.order_service import OrderService

logger = logging.getLogger("app.payments.webhook")

HANDLED_EVENTS = {"payment.captured", "order.paid", "payment.failed"}


@payments_bp.route("/webhooks/razorpay", methods=["POST"])
@csrf.exempt
def razorpay_webhook():
    """Server-to-server notification from Razorpay. Authenticity is proven
    solely by the HMAC signature header, never by session/cookies, and every
    event is processed at most once via the WebhookEvent idempotency table."""
    raw_body = request.get_data()
    signature = request.headers.get("X-Razorpay-Signature", "")

    try:
        RazorpayService.verify_webhook_signature(raw_body, signature)
    except RazorpayError:
        return {"status": "invalid signature"}, 400

    try:
        payload = json.loads(raw_body)
    except ValueError:
        return {"status": "invalid payload"}, 400

    event_type = payload.get("event", "unknown")
    event_id = request.headers.get("X-Razorpay-Event-Id") or hashlib.sha256(raw_body).hexdigest()

    if WebhookEvent.query.filter_by(event_id=event_id).first():
        logger.info("Duplicate Razorpay webhook ignored: event_id=%s type=%s", event_id, event_type)
        return {"status": "already processed"}, 200

    if event_type in HANDLED_EVENTS:
        try:
            _process_event(event_type, payload)
        except Exception:
            logger.exception("Error processing Razorpay webhook event_id=%s type=%s", event_id, event_type)
            return {"status": "processing error"}, 500
    else:
        logger.info("Unhandled Razorpay webhook event type ignored: %s", event_type)

    db.session.add(
        WebhookEvent(provider="razorpay", event_id=event_id, event_type=event_type, payload=raw_body.decode("utf-8", "ignore")[:5000])
    )
    db.session.commit()

    return {"status": "ok"}, 200


def _process_event(event_type, payload):
    entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    razorpay_order_id = entity.get("order_id")
    razorpay_payment_id = entity.get("id")

    if not razorpay_order_id:
        logger.warning("Razorpay webhook missing order id: type=%s", event_type)
        return

    order = Order.query.filter_by(razorpay_order_id=razorpay_order_id).first()
    if order is None:
        logger.warning("Razorpay webhook references unknown order: razorpay_order_id=%s", razorpay_order_id)
        return

    payment = Payment.query.filter_by(order_id=order.id, provider="razorpay").first()

    if event_type in ("payment.captured", "order.paid"):
        if payment:
            payment.provider_payment_id = razorpay_payment_id
            payment.status = "paid"
            payment.signature_verified = True
            payment.raw_reference = json.dumps(entity)
        order.razorpay_payment_id = order.razorpay_payment_id or razorpay_payment_id
        db.session.commit()
        OrderService.mark_paid(order)
        logger.info("Webhook confirmed payment: order_number=%s", order.order_number)

    elif event_type == "payment.failed":
        reason = entity.get("error_description") or "Payment failed (Razorpay webhook)."
        if payment:
            payment.status = "failed"
            payment.raw_reference = reason
            db.session.commit()
        OrderService.mark_payment_failed(order, note=reason)
        logger.info("Webhook confirmed payment failure: order_number=%s", order.order_number)
