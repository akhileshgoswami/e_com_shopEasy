"""Outbound transactional email.

Every email is rendered from two Jinja templates — ``emails/<name>.html``
(autoescaped) and ``emails/<name>.txt`` (plain-text fallback) — on top of a
shared branded layout, and sent over SMTP with a verified TLS connection.

Notifications that must go out at most once (order confirmations, owner
alerts, status updates...) are claimed in the ``EmailOutbox`` kind under an
idempotency key before sending, and a failed send stays there to be retried
by ``flask send-pending-emails``. Sending is synchronous today; because each
outbox row is rebuilt from ids alone, moving delivery to Cloud Tasks or a
worker later only means calling ``EmailService.send_outbox_row`` from there.

Nothing here raises into the caller: an SMTP outage must never roll back an
order or a payment. Logs carry masked recipients and the email kind only —
never bodies, reset links, or credentials.
"""

import logging
import re
import smtplib
import ssl
from datetime import datetime, timezone

from flask import current_app, has_request_context, render_template, url_for
from flask_mail import Connection, Message

from app.models import EmailOutbox, Order, OrderStatus, PaymentMethod, PaymentStatus, User

logger = logging.getLogger("app.email")

_ADDRESS_SPLIT = re.compile(r"[,;\s]+")


def mask_email(address):
    """c***@example.com — enough to correlate logs, not to harvest addresses."""
    local, _, domain = (address or "").partition("@")
    if not domain:
        return "***"
    return f"{local[:1]}***@{domain}"


class _VerifiedSMTPConnection(Connection):
    """Flask-Mail's connection with two fixes: a socket timeout (so a slow
    SMTP server can't hang a checkout request forever) and a TLS context
    that verifies the server certificate — plain ``starttls()`` does not."""

    def configure_host(self):
        timeout = current_app.config.get("MAIL_TIMEOUT_SECONDS", 15)
        context = ssl.create_default_context()
        if self.mail.use_ssl:
            host = smtplib.SMTP_SSL(self.mail.server, self.mail.port, timeout=timeout, context=context)
        else:
            host = smtplib.SMTP(self.mail.server, self.mail.port, timeout=timeout)
        # Never enable smtplib debug output: it echoes the AUTH exchange.
        host.set_debuglevel(0)
        if self.mail.use_tls and not self.mail.use_ssl:
            host.starttls(context=context)
        if self.mail.username and self.mail.password:
            host.login(self.mail.username, self.mail.password)
        return host


# ---------------------------------------------------------------------------
# Presentation helpers shared by the templates
# ---------------------------------------------------------------------------

PAYMENT_METHOD_LABELS = {
    PaymentMethod.COD: "Cash on Delivery",
    PaymentMethod.RAZORPAY: "Online payment (Razorpay)",
}

STATUS_MESSAGES = {
    OrderStatus.PENDING_PAYMENT: "Your order is waiting for payment.",
    OrderStatus.PLACED: "Your order has been placed.",
    OrderStatus.CONFIRMED: "Your order has been confirmed.",
    OrderStatus.PROCESSING: "Your order is being prepared.",
    OrderStatus.PACKED: "Your order is packed and ready to ship.",
    OrderStatus.SHIPPED: "Your order is on its way.",
    OrderStatus.OUT_FOR_DELIVERY: "Your order is out for delivery and is expected to arrive soon.",
    OrderStatus.DELIVERED: "Your order has been delivered.",
    OrderStatus.CANCELLED: "Your order has been cancelled.",
    OrderStatus.FAILED: "We couldn't complete your order.",
    OrderStatus.RETURNED: "Your return has been received.",
    OrderStatus.REFUNDED: "Your refund has been processed.",
}

STATUS_SUBJECTS = {
    OrderStatus.CONFIRMED: "Your order #{number} is confirmed",
    OrderStatus.PROCESSING: "Your order #{number} is being prepared",
    OrderStatus.PACKED: "Your order #{number} is packed",
    OrderStatus.SHIPPED: "Your order #{number} has shipped",
    OrderStatus.OUT_FOR_DELIVERY: "Your order #{number} is out for delivery",
    OrderStatus.DELIVERED: "Your order #{number} has been delivered",
    OrderStatus.CANCELLED: "Your order #{number} has been cancelled",
    OrderStatus.REFUNDED: "Refund processed for order #{number}",
}


def status_subject(order_number, new_status):
    template = STATUS_SUBJECTS.get(new_status, "Order #{number} update: " + OrderStatus.label(new_status))
    return template.replace("{number}", order_number)


def payment_status_label(order):
    if order.payment_status == PaymentStatus.PAID:
        return "Paid" if order.payment_method == PaymentMethod.COD else "Paid (verified)"
    if order.payment_status == PaymentStatus.FAILED:
        return "Failed"
    if order.payment_status == PaymentStatus.REFUNDED:
        return "Refunded"
    if order.payment_method == PaymentMethod.COD:
        return "Pay on delivery"
    return "Awaiting payment"


def _order_items(order):
    """Order lines as plain dicts, with an absolute image URL where the
    product still has one."""
    from app.models import Product, ProductImage

    items = order.items
    product_ids = [i.product_id for i in items if i.product_id]
    products = Product.find_many(product_ids)
    images = {}
    for pid in dict.fromkeys(product_ids):
        rows = sorted(ProductImage.all(ProductImage.product_id == pid), key=lambda r: r.sort_order)
        url = rows[0].image_url if rows else (products[pid].image_url if pid in products else None)
        if url:
            images[pid] = EmailService.absolute_asset_url(url)
    return [
        {
            "name": item.product_name,
            "sku": item.sku,
            "size": item.size,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "subtotal": item.subtotal,
            "image_url": images.get(item.product_id),
        }
        for item in items
    ]


class EmailService:
    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    @staticmethod
    def enabled():
        return bool(current_app.config.get("MAIL_ENABLED"))

    @staticmethod
    def validate_config(app):
        """Log (never raise) configuration mistakes at startup, so a missing
        SMTP setting shows up in the deploy logs instead of at checkout."""
        config = app.config
        problems = []
        if config.get("MAIL_ENABLED"):
            for name in ("MAIL_SERVER", "MAIL_PORT", "MAIL_DEFAULT_SENDER"):
                if not config.get(name):
                    problems.append(f"{name} is not set")
            if config.get("MAIL_USERNAME") and not config.get("MAIL_PASSWORD"):
                problems.append("MAIL_USERNAME is set but MAIL_PASSWORD is empty")
            if config.get("MAIL_USE_TLS") and config.get("MAIL_USE_SSL"):
                problems.append("MAIL_USE_TLS and MAIL_USE_SSL are both true; use TLS on 587 or SSL on 465")
            if not config.get("OWNER_EMAIL"):
                problems.append("OWNER_EMAIL is not set; new-order notifications will be skipped")
        base_url = config.get("BASE_URL") or ""
        if not base_url.startswith(("http://", "https://")):
            problems.append("BASE_URL must be an absolute http(s) URL")
        elif config.get("FLASK_ENV") == "production" and "localhost" in base_url:
            problems.append("BASE_URL points at localhost in production; email links will be broken")

        for problem in problems:
            app.logger.error("Email configuration: %s", problem)
        if not config.get("MAIL_ENABLED"):
            app.logger.info("Email sending disabled (MAIL_ENABLED=false); emails will only be logged.")
        return problems

    @staticmethod
    def owner_recipients():
        raw = current_app.config.get("OWNER_EMAIL") or ""
        return [a for a in _ADDRESS_SPLIT.split(raw) if "@" in a]

    @staticmethod
    def base_url():
        return (current_app.config.get("BASE_URL") or "").rstrip("/")

    @classmethod
    def absolute_url(cls, endpoint, **values):
        """Public link for an email, always built on BASE_URL — never on the
        request's Host header, which a client controls."""
        if has_request_context():
            path = url_for(endpoint, **values)
        else:
            with current_app.test_request_context():
                path = url_for(endpoint, **values)
        return cls.base_url() + path

    @classmethod
    def absolute_asset_url(cls, url):
        if not url:
            return None
        if url.startswith(("http://", "https://")):
            return url
        return cls.base_url() + "/" + url.lstrip("/")

    # ------------------------------------------------------------------
    # Rendering and delivery
    # ------------------------------------------------------------------

    @classmethod
    def _brand_context(cls):
        from app.services.site_content_service import (
            BRANDING_DEFAULTS,
            BrandingService,
            SiteContentService,
            build_theme_palette,
        )

        branding = dict(BRANDING_DEFAULTS)
        contact = {}
        try:
            branding = BrandingService.get()
            contact = SiteContentService.get_many(["contact_email", "contact_phone", "contact_address"])
        except Exception:
            logger.exception("Could not load branding for email; using defaults")
        try:
            palette = build_theme_palette(branding["theme_color"])
        except (ValueError, TypeError):
            palette = build_theme_palette(BRANDING_DEFAULTS["theme_color"])
        return {
            "store_name": branding["site_name"],
            "logo_url": cls.absolute_asset_url(branding.get("logo_url")),
            "brand": palette,
            "support_email": contact.get("contact_email") or current_app.config.get("MAIL_DEFAULT_SENDER"),
            "support_phone": contact.get("contact_phone"),
            "support_address": contact.get("contact_address"),
            "base_url": cls.base_url(),
            "home_url": cls.base_url() + "/",
            "year": datetime.now(timezone.utc).year,
        }

    @classmethod
    def render(cls, template, subject, **context):
        """(html, text) for emails/<template>.html and .txt."""
        context = {**cls._brand_context(), "subject": subject, **context}
        html = render_template(f"emails/{template}.html", **context)
        text = render_template(f"emails/{template}.txt", **context)
        return html, text

    @classmethod
    def deliver(cls, subject, recipients, template, context, kind=None):
        """Render and send one email. True on success, False when disabled
        or on any failure (already logged)."""
        return cls._deliver(subject, recipients, template, context, kind) is None

    @classmethod
    def deliver_rendered(cls, subject, recipients, html, text, kind, reply_to=None):
        """Send an already-rendered email (admin previews / SMTP test)."""
        return cls._deliver(subject, recipients, None, None, kind, rendered=(html, text), reply_to=reply_to) is None

    @classmethod
    def _deliver(cls, subject, recipients, template, context, kind=None, rendered=None, reply_to=None):
        """Like deliver(), but returns None on success or a short, secret-free
        error description."""
        kind = kind or template
        masked = ", ".join(mask_email(r) for r in recipients)
        if not recipients:
            logger.warning("Email not sent, no recipients: kind=%s", kind)
            return "no recipients"
        if not cls.enabled():
            logger.info("Email suppressed (MAIL_ENABLED=false): kind=%s to=%s", kind, masked)
            return "mail disabled"
        try:
            html, text = rendered or cls.render(template, subject, **context)
            message = Message(
                subject=subject,
                recipients=list(recipients),
                html=html,
                body=text,
                sender=current_app.config.get("MAIL_DEFAULT_SENDER"),
                reply_to=reply_to or (context or {}).get("reply_to"),
            )
            with _VerifiedSMTPConnection(current_app.extensions["mail"]) as connection:
                connection.send(message)
        except Exception as exc:
            error = f"{type(exc).__name__}: {str(exc)[:200]}"
            logger.error("Email delivery failed: kind=%s to=%s error=%s", kind, masked, error)
            return error
        logger.info("Email sent: kind=%s to=%s", kind, masked)
        return None

    # ------------------------------------------------------------------
    # Outbox (idempotent, retryable notifications)
    # ------------------------------------------------------------------

    @classmethod
    def _send_once(cls, key_name, kind, payload):
        """Send the email identified by key_name unless it already went out.
        Never raises."""
        if not cls.enabled():
            logger.info("Email suppressed (MAIL_ENABLED=false): kind=%s key=%s", kind, key_name)
            return False
        try:
            row = EmailOutbox.claim(key_name, kind, payload)
            if row is None:
                logger.info("Email already sent or in progress, skipped: key=%s", key_name)
                return False
            return cls.send_outbox_row(row)
        except Exception:
            logger.exception("Email outbox error: key=%s", key_name)
            return False

    @classmethod
    def send_outbox_row(cls, row):
        """Build and send a claimed outbox row, recording the outcome."""
        builder = _BUILDERS.get(row.kind)
        try:
            built = builder(row.payload or {}) if builder else None
        except Exception as exc:
            logger.exception("Could not build email: key=%s", row.key_name)
            row.mark_failed(f"build error: {type(exc).__name__}")
            return False
        if built is None:
            # The order/user it refers to is gone; nothing will ever send it.
            row.attempts = EmailOutbox.MAX_ATTEMPTS
            row.mark_failed("nothing to send (missing data or recipient)")
            return False

        error = cls._deliver(built["subject"], built["recipients"], built["template"], built["context"], kind=row.kind)
        if error is None:
            row.mark_sent()
            return True
        row.mark_failed(error)
        return False

    @classmethod
    def retry_pending(cls):
        """Resend failed / stuck notifications. Returns (sent, failed)."""
        sent = failed = 0
        for row in EmailOutbox.retryable():
            claimed = EmailOutbox.claim(row.key_name, row.kind, row.payload)
            if claimed is None:
                continue
            if cls.send_outbox_row(claimed):
                sent += 1
            else:
                failed += 1
        return sent, failed

    # ------------------------------------------------------------------
    # Public API — one method per email
    # ------------------------------------------------------------------

    @classmethod
    def send_registration_confirmation(cls, user):
        return cls._send_once(f"registration:{user.id}", "registration", {"user_id": user.id})

    @classmethod
    def send_password_reset(cls, user, token):
        """Not in the outbox: the link must never be persisted, and a user
        who didn't receive it simply asks for a new one."""
        try:
            minutes = current_app.config["PASSWORD_RESET_TOKEN_EXPIRY_MINUTES"]
            copy = _copy(
                "forgot_password",
                customer_name=user.name,
                customer_email=user.email,
                expiry_minutes=minutes,
            )
            return cls.deliver(
                subject=copy["subject"],
                recipients=[user.email],
                template="forgot_password",
                context={
                    "copy": copy,
                    "user": user,
                    "reset_url": cls.absolute_url("auth.reset_password", token=token),
                    "expiry_minutes": minutes,
                    "forgot_url": cls.absolute_url("auth.forgot_password"),
                },
                kind="password_reset",
            )
        except Exception:
            logger.exception("Could not send password reset email: user_id=%s", user.id)
            return False

    @classmethod
    def send_password_changed(cls, user):
        return cls._send_once(
            f"password_changed:{user.id}:{user.session_version or 0}", "password_changed", {"user_id": user.id}
        )

    @classmethod
    def send_order_confirmation(cls, order):
        return cls._send_once(f"order_confirmation:{order.id}", "order_confirmation", {"order_id": order.id})

    @classmethod
    def send_owner_new_order(cls, order):
        if not cls.owner_recipients():
            logger.error("OWNER_EMAIL is not configured; new-order notification skipped: order=%s", order.order_number)
            return False
        return cls._send_once(f"owner_new_order:{order.id}", "owner_new_order", {"order_id": order.id})

    @classmethod
    def send_new_order_notifications(cls, order):
        """Customer confirmation and owner alert, independently: one failing
        never stops the other."""
        customer_sent = cls.send_order_confirmation(order)
        owner_sent = cls.send_owner_new_order(order)
        return customer_sent, owner_sent

    @classmethod
    def send_payment_confirmation(cls, order):
        return cls._send_once(f"payment_received:{order.id}", "payment_received", {"order_id": order.id})

    @classmethod
    def send_order_status_update(cls, order, old_status, new_status, history_id):
        """Keyed on the status-history row, so each real transition emails
        exactly once however many times the request is retried."""
        return cls._send_once(
            f"order_status:{order.id}:{history_id}",
            "order_status",
            {"order_id": order.id, "old_status": old_status, "new_status": new_status},
        )


# ---------------------------------------------------------------------------
# Admin-editable wording (EmailTemplateService) and its placeholder values
# ---------------------------------------------------------------------------


def build_email_values(brand, customer_name=None, customer_email=None, order=None, old_status=None,
                       new_status=None, expiry_minutes=None, changed_at=None, payment_method_label=None,
                       payment_status_label=None, status_label=None):
    """Every {placeholder} an admin may use, as display strings."""
    from app.utils import to_ist

    values = {
        "store_name": brand["store_name"],
        "support_email": brand["support_email"] or "",
        "customer_name": customer_name or "there",
        "customer_email": customer_email or "",
    }
    if order is not None:
        values.update(
            {
                "order_number": order.order_number,
                "order_total": f"\u20b9{order.total_amount:,.2f}",
                "order_date": to_ist(order.created_at).strftime("%d %b %Y, %I:%M %p IST") if order.created_at else "",
                "payment_method": payment_method_label or "",
                "payment_status": payment_status_label or "",
                "order_status": status_label or OrderStatus.label(order.order_status),
                "tracking_number": order.tracking_number or "",
            }
        )
    if new_status:
        values.update(
            {
                "old_status": OrderStatus.label(old_status) if old_status else "",
                "new_status": OrderStatus.label(new_status),
                "status_message": STATUS_MESSAGES.get(new_status, f"Your order is now {OrderStatus.label(new_status)}."),
                "status_subject": status_subject(values.get("order_number", ""), new_status),
            }
        )
    if expiry_minutes is not None:
        values["expiry_minutes"] = str(expiry_minutes)
    if changed_at is not None:
        values["changed_at"] = to_ist(changed_at).strftime("%d %b %Y, %I:%M %p IST")
    return values


def _copy(template_key, **value_kwargs):
    from app.services.email_template_service import EmailTemplateService

    values = build_email_values(EmailService._brand_context(), **value_kwargs)
    return EmailTemplateService.resolve(template_key, values)


def status_context(order, old_status, new_status):
    """Template variables shared by the three status-change emails."""
    return {
        "old_status_label": OrderStatus.label(old_status) if old_status else None,
        "new_status_label": OrderStatus.label(new_status),
        "status_message": STATUS_MESSAGES.get(new_status, f"Your order is now {OrderStatus.label(new_status)}."),
        "new_status": new_status,
        "show_tracking": new_status in (OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED)
        and bool(order.tracking_number or order.tracking_url),
        "show_eta": new_status in (OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY)
        and order.estimated_delivery_date is not None,
        "refund_due": order.payment_status == PaymentStatus.PAID and order.payment_method == PaymentMethod.RAZORPAY,
        "shop_url": EmailService.absolute_url("shop.home"),
    }


# ---------------------------------------------------------------------------
# Builders: outbox payload (ids only) -> subject/recipients/template/context.
# Return None when there is nothing to send.
# ---------------------------------------------------------------------------


def _customer_order_context(order):
    customer = order.user
    return customer, {
        "order": order,
        "customer_name": (customer.name if customer else None) or order.shipping_name,
        "items": _order_items(order),
        "status_label": OrderStatus.label(order.order_status),
        "payment_method_label": PAYMENT_METHOD_LABELS.get(order.payment_method, order.payment_method),
        "payment_status_label": payment_status_label(order),
        "view_order_url": EmailService.absolute_url("checkout.order_detail", order_id=order.id),
    }


def _order_copy(template_key, order, customer, context, **extra):
    return _copy(
        template_key,
        customer_name=context["customer_name"],
        customer_email=customer.email if customer else None,
        order=order,
        payment_method_label=context["payment_method_label"],
        payment_status_label=context["payment_status_label"],
        status_label=context["status_label"],
        **extra,
    )


def _build_registration(payload):
    user = User.find(payload.get("user_id"))
    if user is None:
        return None
    copy = _copy("registration", customer_name=user.name, customer_email=user.email)
    return {
        "subject": copy["subject"],
        "recipients": [user.email],
        "template": "registration",
        "context": {"copy": copy, "user": user, "shop_url": EmailService.absolute_url("shop.home")},
    }


def _build_password_changed(payload):
    user = User.find(payload.get("user_id"))
    if user is None:
        return None
    changed_at = user.password_changed_at or datetime.now(timezone.utc)
    copy = _copy("password_changed", customer_name=user.name, customer_email=user.email, changed_at=changed_at)
    return {
        "subject": copy["subject"],
        "recipients": [user.email],
        "template": "password_changed",
        "context": {
            "copy": copy,
            "user": user,
            "changed_at": changed_at,
            "forgot_url": EmailService.absolute_url("auth.forgot_password"),
            "login_url": EmailService.absolute_url("auth.login"),
        },
    }


def _build_order_confirmation(payload):
    order = Order.find(payload.get("order_id"))
    if order is None:
        return None
    customer, context = _customer_order_context(order)
    if customer is None:
        return None
    context["copy"] = _order_copy("order_confirmation", order, customer, context)
    return {
        "subject": context["copy"]["subject"],
        "recipients": [customer.email],
        "template": "order_confirmation",
        "context": context,
    }


def _build_owner_new_order(payload):
    order = Order.find(payload.get("order_id"))
    recipients = EmailService.owner_recipients()
    if order is None or not recipients:
        return None
    customer, context = _customer_order_context(order)
    context.update(
        {
            "customer": customer,
            "customer_email": customer.email if customer else None,
            "customer_phone": (customer.phone if customer else None) or order.shipping_phone,
            "admin_order_url": EmailService.absolute_url("admin.order_detail", order_id=order.id),
            # Replies go straight to the customer.
            "reply_to": customer.email if customer else None,
        }
    )
    context["copy"] = _order_copy("owner_new_order", order, customer, context)
    return {
        "subject": context["copy"]["subject"],
        "recipients": recipients,
        "template": "owner_new_order",
        "context": context,
    }


def _build_payment_received(payload):
    order = Order.find(payload.get("order_id"))
    if order is None:
        return None
    customer, context = _customer_order_context(order)
    if customer is None:
        return None
    context["copy"] = _order_copy("payment_confirmation", order, customer, context)
    return {
        "subject": context["copy"]["subject"],
        "recipients": [customer.email],
        "template": "payment_confirmation",
        "context": context,
    }


def _build_order_status(payload):
    order = Order.find(payload.get("order_id"))
    if order is None:
        return None
    customer, context = _customer_order_context(order)
    if customer is None:
        return None
    old_status = payload.get("old_status")
    new_status = payload.get("new_status")
    context.update(status_context(order, old_status, new_status))
    template = {
        OrderStatus.CANCELLED: "order_cancelled",
        OrderStatus.DELIVERED: "order_delivered",
    }.get(new_status, "order_status_updated")
    context["copy"] = _order_copy(template, order, customer, context, old_status=old_status, new_status=new_status)
    return {
        "subject": context["copy"]["subject"],
        "recipients": [customer.email],
        "template": template,
        "context": context,
    }


_BUILDERS = {
    "registration": _build_registration,
    "password_changed": _build_password_changed,
    "order_confirmation": _build_order_confirmation,
    "owner_new_order": _build_owner_new_order,
    "payment_received": _build_payment_received,
    "order_status": _build_order_status,
}
