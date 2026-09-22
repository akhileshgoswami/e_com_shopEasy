from app.extensions import db
from app.models import SiteContent

# (label, default value) — used both to seed the admin "Content" screen and
# as a safe fallback so public pages never render empty before an admin has
# edited anything.
DEFAULTS = {
    "about_body": (
        "About us",
        "ShopEasy is an online store bringing you electronics, fashion, and home essentials "
        "at honest prices, with fast delivery and secure checkout.\n\n"
        "We started with a simple idea: online shopping should be easy, transparent, and "
        "reliable — from browsing to checkout to delivery. We work directly with manufacturers "
        "and trusted sellers to keep prices fair.\n\n"
        "Every order is backed by our commitment to quality: secure payments via Razorpay, "
        "cash on delivery where available, and responsive customer support.",
    ),
    "privacy_policy_body": (
        "Privacy Policy",
        "Information we collect: We collect your name, email, phone number and shipping "
        "addresses to process orders and provide customer support. We never store your card, "
        "UPI, or bank details — all online payments are processed directly by Razorpay, a "
        "PCI-DSS compliant payment gateway.\n\n"
        "How we use your information: Your data is used to fulfil orders, send order and "
        "payment notifications, and improve our service. We do not sell your personal data to "
        "third parties.\n\n"
        "Payment security: Online payments are handled by Razorpay. Payment signatures are "
        "verified on our servers before any order is marked as paid. Sensitive payment "
        "credentials never touch our servers or database.\n\n"
        "Cookies: We use essential cookies for session management (keeping you logged in and "
        "your cart intact) and do not use third-party tracking cookies.\n\n"
        "Your rights: You may update or delete your account information at any time from your "
        "profile page, or contact us for assistance.",
    ),
    "terms_body": (
        "Terms and Conditions",
        "Orders: By placing an order, you agree to provide accurate shipping and contact "
        "information. Orders are subject to product availability at the time of payment or "
        "delivery.\n\n"
        "Pricing and payments: All prices are listed in INR and are inclusive of applicable "
        "taxes unless stated otherwise. We accept Cash on Delivery and online payments via "
        "Razorpay. All online payments are verified server-side before an order is confirmed "
        "as paid.\n\n"
        "Cancellations and returns: Orders can be cancelled before they are shipped. Once "
        "shipped, returns are subject to our return policy for the specific product category. "
        "Refunds for online payments are processed back to the original payment method.\n\n"
        "Limitation of liability: We are not liable for delays caused by circumstances beyond "
        "our reasonable control, including courier delays or force majeure events.",
    ),
    "contact_email": ("Support email", "support@example.com"),
    "contact_phone": ("Support phone", "+91 98765 43210"),
    "contact_address": ("Business address", "123 Market Street, Bengaluru, India"),
    "contact_hours": ("Support hours", "Monday to Saturday, 9 AM to 7 PM IST"),
}


class SiteContentService:
    @staticmethod
    def get(key):
        row = SiteContent.query.filter_by(key=key).first()
        if row is not None:
            return row.value
        return DEFAULTS.get(key, ("", ""))[1]

    @staticmethod
    def get_many(keys):
        return {key: SiteContentService.get(key) for key in keys}

    @staticmethod
    def list_all():
        """Every editable content row, DB values layered over defaults, for
        the admin listing — so every key always shows up even before it's
        ever been saved."""
        existing = {row.key: row for row in SiteContent.query.all()}
        items = []
        for key, (label, default_value) in DEFAULTS.items():
            row = existing.get(key)
            items.append(
                {
                    "key": key,
                    "label": label,
                    "value": row.value if row else default_value,
                    "updated_at": row.updated_at if row else None,
                    "is_customized": row is not None,
                }
            )
        return items

    @staticmethod
    def get_or_404(key):
        if key not in DEFAULTS:
            return None
        row = SiteContent.query.filter_by(key=key).first()
        label, default_value = DEFAULTS[key]
        return {
            "key": key,
            "label": label,
            "value": row.value if row else default_value,
        }

    @staticmethod
    def update(key, value):
        if key not in DEFAULTS:
            raise ValueError(f"Unknown content key '{key}'.")
        row = SiteContent.query.filter_by(key=key).first()
        if row is None:
            row = SiteContent(key=key, label=DEFAULTS[key][0], value=value)
            db.session.add(row)
        else:
            row.value = value
        db.session.commit()
        return row
