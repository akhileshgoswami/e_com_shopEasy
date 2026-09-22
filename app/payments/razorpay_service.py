import json
import logging

import razorpay
from flask import current_app

from app.extensions import db
from app.models import Payment

logger = logging.getLogger("app.payments.razorpay")


class RazorpayError(Exception):
    pass


class RazorpayService:
    @staticmethod
    def _client():
        key_id = current_app.config.get("RAZORPAY_KEY_ID")
        key_secret = current_app.config.get("RAZORPAY_KEY_SECRET")
        if not key_id or not key_secret:
            raise RazorpayError("Razorpay is not configured on this server.")
        return razorpay.Client(auth=(key_id, key_secret))

    @classmethod
    def create_order(cls, order):
        """Create (or reuse) the Razorpay Order for our internal Order.

        The amount is always taken from the server-computed order.total_amount,
        never from any client-supplied value.
        """
        if order.razorpay_order_id:
            return {
                "razorpay_order_id": order.razorpay_order_id,
                "amount_paise": int(round(float(order.total_amount) * 100)),
                "currency": current_app.config["RAZORPAY_CURRENCY"],
            }

        amount_paise = int(round(float(order.total_amount) * 100))
        client = cls._client()

        try:
            razorpay_order = client.order.create(
                {
                    "amount": amount_paise,
                    "currency": current_app.config["RAZORPAY_CURRENCY"],
                    "receipt": order.order_number,
                    "payment_capture": 1,
                    "notes": {"internal_order_id": str(order.id), "order_number": order.order_number},
                }
            )
        except Exception as exc:
            logger.exception("Razorpay order creation failed: order_number=%s", order.order_number)
            raise RazorpayError("Unable to initiate payment with Razorpay right now.") from exc

        order.razorpay_order_id = razorpay_order["id"]

        payment = Payment.query.filter_by(order_id=order.id, provider="razorpay").first()
        if payment:
            payment.provider_order_id = razorpay_order["id"]
            payment.raw_reference = json.dumps(razorpay_order)

        db.session.commit()
        logger.info("Razorpay order created: order_number=%s razorpay_order_id=%s", order.order_number, razorpay_order["id"])

        return {
            "razorpay_order_id": razorpay_order["id"],
            "amount_paise": amount_paise,
            "currency": razorpay_order["currency"],
        }

    @classmethod
    def verify_payment_signature(cls, razorpay_order_id, razorpay_payment_id, razorpay_signature):
        client = cls._client()
        try:
            client.utility.verify_payment_signature(
                {
                    "razorpay_order_id": razorpay_order_id,
                    "razorpay_payment_id": razorpay_payment_id,
                    "razorpay_signature": razorpay_signature,
                }
            )
        except razorpay.errors.SignatureVerificationError as exc:
            logger.warning("Razorpay signature verification failed: razorpay_order_id=%s", razorpay_order_id)
            raise RazorpayError("Payment signature verification failed.") from exc
        return True

    @classmethod
    def verify_webhook_signature(cls, raw_body, signature):
        secret = current_app.config.get("RAZORPAY_WEBHOOK_SECRET")
        if not secret:
            raise RazorpayError("Razorpay webhook secret is not configured.")
        client = cls._client()
        try:
            client.utility.verify_webhook_signature(raw_body, signature, secret)
        except razorpay.errors.SignatureVerificationError as exc:
            logger.warning("Razorpay webhook signature verification failed.")
            raise RazorpayError("Webhook signature verification failed.") from exc
        return True
