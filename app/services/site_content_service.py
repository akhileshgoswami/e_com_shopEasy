from flask import current_app

from google.cloud import ndb

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
        row = SiteContent.get_by_id(key)
        if row is not None:
            return row.value
        return DEFAULTS.get(key, ("", ""))[1]

    @staticmethod
    def get_many(keys):
        rows = SiteContent.get_many(keys)
        return {key: rows[key].value if key in rows else DEFAULTS.get(key, ("", ""))[1] for key in keys}

    @staticmethod
    def list_all():
        """Every editable content row, DB values layered over defaults, for
        the admin listing — so every key always shows up even before it's
        ever been saved."""
        existing = SiteContent.get_many(DEFAULTS.keys())
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
        row = SiteContent.get_by_id(key)
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
        row = SiteContent.get_by_id(key) or SiteContent(id=key, label=DEFAULTS[key][0])
        row.value = value
        row.put()
        return row


# Branding lives in the same key/value table as page copy, but is edited from
# the admin Settings screen rather than the Content list.
BRANDING_DEFAULTS = {
    "site_name": "ShopEasy",
    "theme_color": "#b8873f",
    "logo_url": "",
    "logo_path": "",
    "show_name_with_logo": "1",
    "heading_font": "fraunces",
    "body_font": "inter",
}

THEME_PRESETS = [
    ("Gold", "#b8873f"),
    ("Emerald", "#1f8a5b"),
    ("Ocean", "#1f6fb2"),
    ("Royal", "#5b3fb8"),
    ("Rose", "#c2416b"),
    ("Coral", "#e0613a"),
    ("Teal", "#138a8a"),
    ("Charcoal", "#4a4a4a"),
]


# Fonts are served by @fontsource on jsdelivr (already allowed by the CSP).
# key -> (label, CSS family, generic fallback, weights published by fontsource)
_SERIF = 'Georgia, "Times New Roman", serif'
_SANS = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
FONT_CHOICES = {
    "fraunces": ("Fraunces (elegant serif)", "Fraunces", _SERIF, (400, 500, 600, 700)),
    "playfair-display": ("Playfair Display (luxury serif)", "Playfair Display", _SERIF, (400, 500, 600, 700)),
    "cormorant-garamond": ("Cormorant Garamond (classic serif)", "Cormorant Garamond", _SERIF, (400, 500, 600, 700)),
    "lora": ("Lora (soft serif)", "Lora", _SERIF, (400, 500, 600, 700)),
    "merriweather": ("Merriweather (readable serif)", "Merriweather", _SERIF, (400, 500, 600, 700)),
    "libre-baskerville": ("Libre Baskerville (bookish serif)", "Libre Baskerville", _SERIF, (400, 500, 600, 700)),
    "dm-serif-display": ("DM Serif Display (bold serif)", "DM Serif Display", _SERIF, (400,)),
    "inter": ("Inter (clean sans)", "Inter", _SANS, (400, 500, 600, 700)),
    "poppins": ("Poppins (geometric sans)", "Poppins", _SANS, (400, 500, 600, 700)),
    "montserrat": ("Montserrat (modern sans)", "Montserrat", _SANS, (400, 500, 600, 700)),
    "dm-sans": ("DM Sans (friendly sans)", "DM Sans", _SANS, (400, 500, 600, 700)),
    "roboto": ("Roboto (neutral sans)", "Roboto", _SANS, (400, 500, 600, 700)),
    "open-sans": ("Open Sans (neutral sans)", "Open Sans", _SANS, (400, 500, 600, 700)),
    "lato": ("Lato (warm sans)", "Lato", _SANS, (400, 700)),
    "nunito": ("Nunito (rounded sans)", "Nunito", _SANS, (400, 500, 600, 700)),
    "raleway": ("Raleway (stylish sans)", "Raleway", _SANS, (400, 500, 600, 700)),
    "work-sans": ("Work Sans (simple sans)", "Work Sans", _SANS, (400, 500, 600, 700)),
}
_FONTSOURCE_URL = "https://cdn.jsdelivr.net/npm/@fontsource/{key}@5/{weight}.css"


def font_stack(key):
    _label, family, fallback, _weights = FONT_CHOICES[key]
    return f'"{family}", {fallback}'


def font_stylesheet_urls(key, wanted_weights):
    available = FONT_CHOICES[key][3]
    weights = [w for w in wanted_weights if w in available] or [available[0]]
    return [_FONTSOURCE_URL.format(key=key, weight=w) for w in weights]


def build_font_theme(heading_key, body_key):
    """CSS stacks plus the stylesheet URLs for just the weights the site uses."""
    heading_key = heading_key if heading_key in FONT_CHOICES else BRANDING_DEFAULTS["heading_font"]
    body_key = body_key if body_key in FONT_CHOICES else BRANDING_DEFAULTS["body_font"]
    urls = font_stylesheet_urls(heading_key, (600, 700)) + font_stylesheet_urls(body_key, (400, 500, 600))
    return {
        "heading": font_stack(heading_key),
        "body": font_stack(body_key),
        "urls": list(dict.fromkeys(urls)),
    }


def _hex_to_rgb(hex_color):
    value = hex_color.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def build_theme_palette(hex_color):
    """Derive the accent shades the stylesheet uses from one admin-picked
    color: a darker hover shade, a pale tint, and the raw RGB triplet for
    translucent effects."""
    r, g, b = _hex_to_rgb(hex_color)
    return {
        "accent": _rgb_to_hex((r, g, b)),
        "accent_dark": _rgb_to_hex((r * 0.8, g * 0.8, b * 0.8)),
        "accent_soft": _rgb_to_hex((r + (255 - r) * 0.85, g + (255 - g) * 0.85, b + (255 - b) * 0.85)),
        "accent_rgb": f"{r}, {g}, {b}",
    }


class BrandingService:
    @staticmethod
    def get():
        rows = SiteContent.get_many(BRANDING_DEFAULTS.keys())
        values = dict(BRANDING_DEFAULTS)
        values.update({key: row.value for key, row in rows.items() if row.value})
        return values

    @staticmethod
    def update(
        site_name,
        theme_color,
        logo=None,
        remove_logo=False,
        show_name_with_logo=True,
        heading_font=None,
        body_font=None,
    ):
        """Old logo file is deleted only after the new one is saved, so a
        failed upload never leaves the header without a logo."""
        from app.storage import get_storage

        old_path = BrandingService.get()["logo_path"]
        pending = []

        if logo:
            url, path = get_storage().upload(logo, folder="branding")
            pending.append(("logo_url", url, "Logo URL"))
            pending.append(("logo_path", path, "Logo path"))
        elif remove_logo:
            pending.append(("logo_url", "", "Logo URL"))
            pending.append(("logo_path", "", "Logo path"))

        pending.append(("site_name", site_name.strip(), "Website name"))
        pending.append(("theme_color", theme_color.lower(), "Theme color"))
        pending.append(("show_name_with_logo", "1" if show_name_with_logo else "0", "Show name with logo"))
        if heading_font in FONT_CHOICES:
            pending.append(("heading_font", heading_font, "Heading font"))
        if body_font in FONT_CHOICES:
            pending.append(("body_font", body_font, "Body font"))
        _set_values(pending)

        if (logo or remove_logo) and old_path:
            _delete_stored_file(old_path)


HERO_DEFAULTS = {
    "hero_eyebrow": "Curated for you",
    "hero_title": "Everyday essentials, elevated.",
    "hero_subtitle": (
        "Thoughtfully sourced electronics, fashion and home pieces — secure checkout, effortless delivery."
    ),
    "hero_button_text": "Shop the collection",
    "hero_image_url": "",
    "hero_image_path": "",
}


def _set_values(pending):
    """Upsert (key, value, label) rows in one batch write."""
    existing = SiteContent.get_many(key for key, _value, _label in pending)
    rows = []
    for key, value, label in pending:
        row = existing.get(key) or SiteContent(id=key, label=label)
        row.value = value
        rows.append(row)
    ndb.put_multi(rows)


def _delete_stored_file(path):
    from app.storage import get_storage

    try:
        get_storage().delete(path)
    except Exception:
        current_app.logger.exception("Failed to delete old uploaded file %s", path)


class HeroBannerService:
    @staticmethod
    def get():
        rows = SiteContent.get_many(HERO_DEFAULTS.keys())
        values = dict(HERO_DEFAULTS)
        values.update({key: row.value for key, row in rows.items()})
        # An admin clearing a text field falls back to the default copy.
        for key in ("hero_eyebrow", "hero_title", "hero_subtitle", "hero_button_text"):
            if not values[key].strip():
                values[key] = HERO_DEFAULTS[key]
        return values

    @staticmethod
    def update(eyebrow, title, subtitle, button_text, image=None, remove_image=False):
        """Save banner copy and optionally replace/remove the background
        image. The old stored file is deleted only after a replacement
        upload succeeds, so a failed upload never leaves the banner blank."""
        from app.storage import get_storage

        current = HeroBannerService.get()
        old_path = current["hero_image_path"]
        pending = []

        if image:
            url, path = get_storage().upload(image, folder="banners")
            pending.append(("hero_image_url", url, "Banner image URL"))
            pending.append(("hero_image_path", path, "Banner image path"))
        elif remove_image:
            pending.append(("hero_image_url", "", "Banner image URL"))
            pending.append(("hero_image_path", "", "Banner image path"))

        pending.append(("hero_eyebrow", eyebrow.strip(), "Banner eyebrow"))
        pending.append(("hero_title", title.strip(), "Banner title"))
        pending.append(("hero_subtitle", subtitle.strip(), "Banner subtitle"))
        pending.append(("hero_button_text", button_text.strip(), "Banner button text"))
        _set_values(pending)

        if (image or remove_image) and old_path:
            _delete_stored_file(old_path)
