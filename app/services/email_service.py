import logging

from flask import current_app, render_template
from flask_mail import Message

from app.extensions import mail

logger = logging.getLogger("app.email")


class EmailService:
    """Thin abstraction around outbound transactional email.

    When MAIL_ENABLED is false (default for local dev), emails are logged
    instead of sent so the app works without SMTP credentials configured.
    """

    @staticmethod
    def _send(subject, recipients, template_base, context):
        if not current_app.config.get("MAIL_ENABLED"):
            logger.info("Email suppressed (MAIL_ENABLED=false): subject=%s to=%s", subject, recipients)
            return

        try:
            html_body = render_template(f"emails/{template_base}.html", **context)
        except Exception:
            html_body = None

        msg = Message(
            subject=subject,
            recipients=recipients,
            html=html_body,
            body=context.get("text_body", subject),
            sender=current_app.config.get("MAIL_DEFAULT_SENDER"),
        )
        try:
            mail.send(msg)
        except Exception:
            logger.exception("Failed to send email: subject=%s to=%s", subject, recipients)

    @classmethod
    def send_registration_confirmation(cls, user):
        cls._send(
            subject="Welcome to our store",
            recipients=[user.email],
            template_base="registration",
            context={"user": user, "text_body": f"Welcome, {user.name}!"},
        )

    @classmethod
    def send_password_reset(cls, user, reset_url):
        cls._send(
            subject="Reset your password",
            recipients=[user.email],
            template_base="password_reset",
            context={"user": user, "reset_url": reset_url, "text_body": f"Reset your password: {reset_url}"},
        )

    @classmethod
    def send_order_confirmation(cls, order):
        cls._send(
            subject=f"Order confirmed: {order.order_number}",
            recipients=[order.user.email],
            template_base="order_confirmation",
            context={"order": order, "text_body": f"Your order {order.order_number} has been placed."},
        )

    @classmethod
    def send_payment_confirmation(cls, order):
        cls._send(
            subject=f"Payment received for order {order.order_number}",
            recipients=[order.user.email],
            template_base="payment_confirmation",
            context={"order": order, "text_body": f"Payment received for order {order.order_number}."},
        )

    @classmethod
    def send_order_status_update(cls, order):
        cls._send(
            subject=f"Order {order.order_number} status update: {order.order_status}",
            recipients=[order.user.email],
            template_base="order_status_update",
            context={"order": order, "text_body": f"Order {order.order_number} is now {order.order_status}."},
        )
