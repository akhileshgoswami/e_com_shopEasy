"""Admin-editable wording for transactional emails.

Admins edit plain text — subject, heading, main message, button label and an
optional note — with ``{placeholder}`` tokens. The layout, order tables,
links and security notices stay in the Jinja templates under
``templates/emails/``, so an edit can never break an email, inject markup or
drop the reset link / expiry warning.

Placeholders are substituted with a plain regex, never ``str.format`` (which
would let ``{order.__class__}``-style lookups reach Python objects), and the
result is autoescaped by the HTML templates like any other value.

Overrides are stored as SiteContent rows ``email.<template>.<field>``; a
field left at its default has no row, so improved defaults ship with code.
"""

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from google.cloud import ndb

from app.models import SiteContent

PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")

FIELDS = (
    # (name, label, multiline, max length, required)
    ("subject", "Subject line", False, 200, True),
    ("heading", "Heading", False, 150, True),
    ("intro", "Main message", True, 3000, True),
    ("button_label", "Button label", False, 40, True),
    ("note", "Extra note (optional)", True, 1500, False),
)
FIELD_NAMES = tuple(f[0] for f in FIELDS)

PLACEHOLDER_HELP = {
    "store_name": "Your website name",
    "support_email": "Support email (Content settings)",
    "customer_name": "Customer's name",
    "customer_email": "Customer's email",
    "order_number": "Order number, e.g. ORD-20260925-AB12CD",
    "order_total": "Order total, e.g. ₹1,299.00",
    "order_date": "Order date and time (IST)",
    "payment_method": "Cash on Delivery / Online payment",
    "payment_status": "Paid, Pay on delivery, ...",
    "order_status": "Current order status",
    "old_status": "Previous status",
    "new_status": "New status",
    "status_message": "Standard sentence for the new status, e.g. 'Your order is on its way.'",
    "status_subject": "Standard subject for the new status",
    "tracking_number": "Courier tracking number (if set)",
    "expiry_minutes": "Minutes until the reset link expires",
    "changed_at": "When the password was changed (IST)",
    "code_expiry_minutes": "Minutes until the verification code expires",
}

_ACCOUNT = ("store_name", "support_email", "customer_name", "customer_email")
_ORDER = _ACCOUNT + ("order_number", "order_total", "order_date", "payment_method", "payment_status", "order_status")
_STATUS = _ORDER + ("old_status", "new_status", "status_message", "status_subject", "tracking_number")

EMAIL_TEMPLATES = {
    "order_confirmation": {
        "name": "Order confirmation",
        "audience": "Customer",
        "trigger": "Cash on Delivery order placed, or online payment verified",
        "placeholders": _ORDER,
        "defaults": {
            "subject": "Order Confirmed — #{order_number}",
            "heading": "Thanks for your order!",
            "intro": "Hi {customer_name}, we've received your order and will let you know as soon as it ships.",
            "button_label": "View Order",
            "note": "",
        },
    },
    "owner_new_order": {
        "name": "New order alert (owner)",
        "audience": "Store owner",
        "trigger": "Same moment as the order confirmation, sent to OWNER_EMAIL",
        "placeholders": _ORDER,
        "defaults": {
            "subject": "New Order Received — #{order_number}",
            "heading": "New order received",
            "intro": "A new order has been placed on {store_name}.",
            "button_label": "View Order in Admin Panel",
            "note": "",
        },
    },
    "order_status_updated": {
        "name": "Order status update",
        "audience": "Customer",
        "trigger": "Status changes to confirmed, processing, packed, shipped, out for delivery, returned, refunded ...",
        "placeholders": _STATUS,
        "defaults": {
            "subject": "{status_subject}",
            "heading": "{status_message}",
            "intro": "Hi {customer_name}, there's an update on your order #{order_number}.",
            "button_label": "View Order",
            "note": "",
        },
    },
    "order_cancelled": {
        "name": "Order cancelled",
        "audience": "Customer",
        "trigger": "Order cancelled by an admin or the customer",
        "placeholders": _STATUS,
        "defaults": {
            "subject": "Your order #{order_number} has been cancelled",
            "heading": "Your order has been cancelled",
            "intro": (
                "Hi {customer_name}, your order #{order_number} has been cancelled.\n\n"
                "If you didn't expect this or have questions, contact our support team at {support_email}."
            ),
            "button_label": "View Order",
            "note": "",
        },
    },
    "order_delivered": {
        "name": "Order delivered",
        "audience": "Customer",
        "trigger": "Order marked as delivered",
        "placeholders": _STATUS,
        "defaults": {
            "subject": "Your order #{order_number} has been delivered",
            "heading": "Your order has been delivered",
            "intro": (
                "Hi {customer_name}, your order #{order_number} has been delivered. We hope you love it!\n\n"
                "Something not right? Contact us at {support_email} and we'll help."
            ),
            "button_label": "View Order",
            "note": "",
        },
    },
    "payment_confirmation": {
        "name": "Payment received",
        "audience": "Customer",
        "trigger": "Admin marks a Cash on Delivery payment as collected",
        "placeholders": _ORDER,
        "defaults": {
            "subject": "Payment received — #{order_number}",
            "heading": "Payment received",
            "intro": "Hi {customer_name}, we've received your payment of {order_total} for order #{order_number}. Thank you!",
            "button_label": "View Order",
            "note": "",
        },
    },
    "verify_email": {
        "name": "Email verification code",
        "audience": "Customer",
        "trigger": "Customer signs up with email and password, or logs in before verifying",
        "placeholders": _ACCOUNT + ("code_expiry_minutes",),
        "note_help": "The 6-digit code, its expiry and the \"didn't sign up?\" notice are always included.",
        "defaults": {
            "subject": "Verify your email | {store_name}",
            "heading": "Confirm your email address",
            "intro": (
                "Hi {customer_name},\n\n"
                "Thanks for signing up with {store_name}! Enter the code below to verify your email "
                "and activate your account."
            ),
            "button_label": "Enter code",
            "note": "",
        },
    },
    "forgot_password": {
        "name": "Password reset",
        "audience": "Customer",
        "trigger": "Customer requests a password reset",
        "placeholders": _ACCOUNT + ("expiry_minutes",),
        "note_help": "The reset link, its expiry time and the \"didn't ask for this?\" notice are always included.",
        "defaults": {
            "subject": "Reset Your Password | {store_name}",
            "heading": "Reset your password",
            "intro": (
                "Hi {customer_name},\n\n"
                "We received a request to reset the password for your {store_name} account. "
                "Click the button below to choose a new one."
            ),
            "button_label": "Reset Password",
            "note": "",
        },
    },
    "password_changed": {
        "name": "Password changed",
        "audience": "Customer",
        "trigger": "Password reset or changed from the profile page",
        "placeholders": _ACCOUNT + ("changed_at",),
        "note_help": "The \"wasn't you?\" security notice is always included.",
        "defaults": {
            "subject": "Your password was changed | {store_name}",
            "heading": "Your password was changed",
            "intro": (
                "Hi {customer_name},\n\n"
                "The password for your {store_name} account ({customer_email}) was changed on {changed_at}. "
                "For your security, you've been signed out on all other devices."
            ),
            "button_label": "Log in",
            "note": "",
        },
    },
    "registration": {
        "name": "Welcome",
        "audience": "Customer",
        "trigger": "Customer creates an account with email and password",
        "placeholders": _ACCOUNT,
        "defaults": {
            "subject": "Welcome to {store_name}",
            "heading": "Welcome, {customer_name}!",
            "intro": (
                "Thanks for creating an account with {store_name}. You can now shop, track orders, save items "
                "to your wishlist and manage your addresses from your profile."
            ),
            "button_label": "Start Shopping",
            "note": "",
        },
    },
}


class EmailTemplateError(Exception):
    pass


def fill(text, values):
    """Replace {name} tokens; unknown tokens are left as typed."""
    return PLACEHOLDER_RE.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), text or "")


def paragraphs(text):
    """Blank line = new paragraph, single newline = line break."""
    blocks = [b.strip() for b in (text or "").replace("\r\n", "\n").split("\n\n")]
    return [b.split("\n") for b in blocks if b]


def _row_key(template_key, field):
    return f"email.{template_key}.{field}"


class EmailTemplateService:
    @staticmethod
    def spec(template_key):
        spec = EMAIL_TEMPLATES.get(template_key)
        if spec is None:
            raise EmailTemplateError(f"Unknown email template '{template_key}'.")
        return spec

    @classmethod
    def overrides(cls, template_key):
        rows = SiteContent.get_many([_row_key(template_key, f) for f in FIELD_NAMES])
        return {f: rows[_row_key(template_key, f)].value for f in FIELD_NAMES if _row_key(template_key, f) in rows}

    @classmethod
    def current(cls, template_key):
        """Saved wording layered over the defaults (raw, placeholders unfilled)."""
        values = dict(cls.spec(template_key)["defaults"])
        try:
            values.update(cls.overrides(template_key))
        except Exception:
            # Emails must still go out if the datastore read fails.
            pass
        return values

    @classmethod
    def list_all(cls):
        overrides = SiteContent.get_many(
            [_row_key(k, f) for k in EMAIL_TEMPLATES for f in FIELD_NAMES]
        )
        items = []
        for key, spec in EMAIL_TEMPLATES.items():
            customized = any(_row_key(key, f) in overrides for f in FIELD_NAMES)
            subject_row = overrides.get(_row_key(key, "subject"))
            items.append(
                {
                    "key": key,
                    "name": spec["name"],
                    "audience": spec["audience"],
                    "trigger": spec["trigger"],
                    "subject": subject_row.value if subject_row else spec["defaults"]["subject"],
                    "customized": customized,
                }
            )
        return items

    @classmethod
    def validate(cls, template_key, values):
        """{field: error} for placeholders this email doesn't provide."""
        allowed = set(cls.spec(template_key)["placeholders"])
        errors = {}
        for field in FIELD_NAMES:
            unknown = sorted({m for m in PLACEHOLDER_RE.findall(values.get(field) or "")} - allowed)
            if unknown:
                errors[field] = "Unknown placeholder: " + ", ".join("{" + u + "}" for u in unknown)
        return errors

    @classmethod
    def save(cls, template_key, values):
        spec = cls.spec(template_key)
        errors = cls.validate(template_key, values)
        if errors:
            raise EmailTemplateError(next(iter(errors.values())))
        to_put, to_delete = [], []
        for name, label, multiline, max_length, _required in FIELDS:
            value = (values.get(name) or "").replace("\r\n", "\n").strip()
            if not multiline:
                value = " ".join(value.split())
            value = value[:max_length]
            key = ndb.Key(SiteContent, _row_key(template_key, name))
            if value == spec["defaults"][name] or (not value and name == "note"):
                to_delete.append(key)
            else:
                to_put.append(SiteContent(key=key, label=f"Email: {spec['name']} — {label}", value=value))
        if to_put:
            ndb.put_multi(to_put)
        if to_delete:
            ndb.delete_multi(to_delete)

    @classmethod
    def reset(cls, template_key):
        cls.spec(template_key)
        ndb.delete_multi([ndb.Key(SiteContent, _row_key(template_key, f)) for f in FIELD_NAMES])

    @classmethod
    def resolve(cls, template_key, values, raw=None):
        """Wording ready for the templates: placeholders filled, subject on
        one line, message split into paragraphs. raw overrides the stored
        wording (used for previews of unsaved edits)."""
        raw = raw or cls.current(template_key)
        copy = {name: fill(raw.get(name) or "", values) for name in FIELD_NAMES}
        copy["subject"] = " ".join(copy["subject"].split())[:250] or fill(
            cls.spec(template_key)["defaults"]["subject"], values
        )
        copy["intro_paragraphs"] = paragraphs(copy["intro"])
        copy["note_paragraphs"] = paragraphs(copy["note"])
        return copy

    # ------------------------------------------------------------------
    # Previews with sample data (no database reads besides branding)
    # ------------------------------------------------------------------

    @classmethod
    def preview(cls, template_key, raw=None):
        """(subject, html, text) rendered with sample data."""
        from app.services.email_service import EmailService, build_email_values

        cls.spec(template_key)
        template, context, values = _sample(template_key)
        brand = EmailService._brand_context()
        values = build_email_values(brand, **values)
        copy = cls.resolve(template_key, values, raw=raw)
        html, text = EmailService.render(template, copy["subject"], copy=copy, **context)
        return copy["subject"], html, text


def _sample(template_key):
    """(template, context, placeholder values) for a realistic fake order."""
    from app.models import OrderStatus
    from app.services.email_service import EmailService

    now = datetime.now(timezone.utc)
    order = SimpleNamespace(
        id=0,
        order_number="ORD-20260101-SAMPLE",
        created_at=now,
        subtotal=Decimal("2498.00"),
        discount=Decimal("250.00"),
        coupon_code="WELCOME10",
        shipping_charge=Decimal("0.00"),
        tax=Decimal("0.00"),
        total_amount=Decimal("2248.00"),
        payment_method="cod",
        payment_status="pending",
        order_status=OrderStatus.SHIPPED,
        shipping_name="Priya Sharma",
        shipping_phone="98765 43210",
        shipping_address="12 MG Road, Apartment 4B",
        shipping_city="Bengaluru",
        shipping_state="Karnataka",
        shipping_postal_code="560001",
        shipping_country="India",
        notes="Please call before delivery.",
        tracking_number="AWB123456789",
        tracking_url="https://courier.example/track/AWB123456789",
        estimated_delivery_date=(now + timedelta(days=3)).date(),
    )
    items = [
        {"name": "Classic Cotton T-Shirt", "sku": "TSHIRT-BLK-M", "size": "M", "quantity": 2,
         "unit_price": Decimal("499.00"), "subtotal": Decimal("998.00"), "image_url": None},
        {"name": "Canvas Sneakers", "sku": "SNK-WHT-42", "size": "42", "quantity": 1,
         "unit_price": Decimal("1500.00"), "subtotal": Decimal("1500.00"), "image_url": None},
    ]
    user = SimpleNamespace(name="Priya Sharma", email="priya@example.com")
    view_url = EmailService.base_url() + "/orders/0"
    order_context = {
        "order": order,
        "customer_name": user.name,
        "items": items,
        "status_label": "Placed",
        "payment_method_label": "Cash on Delivery",
        "payment_status_label": "Pay on delivery",
        "view_order_url": view_url,
    }
    order_values = {
        "customer_name": user.name,
        "customer_email": user.email,
        "order": order,
        "payment_method_label": "Cash on Delivery",
        "payment_status_label": "Pay on delivery",
        "status_label": "Placed",
    }

    if template_key in ("forgot_password", "password_changed", "registration", "verify_email"):
        context = {
            "code": "482913",
            "verify_url": EmailService.base_url() + "/verify-email",
            "user": user,
            "reset_url": EmailService.base_url() + "/reset-password/SAMPLE-TOKEN",
            "expiry_minutes": 30,
            "forgot_url": EmailService.base_url() + "/forgot-password",
            "login_url": EmailService.base_url() + "/login",
            "shop_url": EmailService.base_url() + "/",
            "changed_at": now,
        }
        values = {
            "customer_name": user.name,
            "customer_email": user.email,
            "expiry_minutes": 30,
            "changed_at": now,
            "code_expiry_minutes": 10,
        }
        if template_key == "verify_email":
            context["expiry_minutes"] = 10
        return template_key, context, values

    if template_key in ("order_status_updated", "order_cancelled", "order_delivered"):
        new_status = {
            "order_cancelled": OrderStatus.CANCELLED,
            "order_delivered": OrderStatus.DELIVERED,
        }.get(template_key, OrderStatus.SHIPPED)
        order.order_status = new_status
        from app.services.email_service import status_context

        context = {**order_context, **status_context(order, OrderStatus.PACKED, new_status)}
        context["refund_due"] = False
        values = {**order_values, "old_status": OrderStatus.PACKED, "new_status": new_status}
        return template_key, context, values

    context = dict(order_context)
    if template_key == "owner_new_order":
        context.update(
            {
                "customer_email": user.email,
                "customer_phone": order.shipping_phone,
                "admin_order_url": EmailService.base_url() + "/admin/orders/0",
            }
        )
    return template_key, context, order_values
