"""Admin-managed homepage product sections (Featured, Trending, On sale,
New arrivals).

Each section is either "auto" (products picked by the built-in rule, same as
the storefront always did) or "manual" (admin picks the products and their
order). Sections can be hidden and reordered. The whole layout is stored as a
single JSON row in ``site_content`` so no migration is needed.
"""

import json

from sqlalchemy import func

from app.extensions import db
from app.models import Order, OrderItem, OrderStatus, Product, SiteContent

STORAGE_KEY = "home_sections"
MAX_LIMIT = 24
MAX_MANUAL_PRODUCTS = 24

# Orders in these states never really sold anything, so they don't count
# toward "most ordered".
NON_SALE_STATUSES = (
    OrderStatus.PENDING_PAYMENT,
    OrderStatus.CANCELLED,
    OrderStatus.FAILED,
    OrderStatus.RETURNED,
    OrderStatus.REFUNDED,
)

# Default layout = what the homepage showed before this was configurable,
# plus Trending (hidden automatically while there are no orders yet).
SECTION_DEFAULTS = [
    {"key": "featured", "title": "Featured products", "rule": "Newest active products"},
    {"key": "trending", "title": "Trending products", "rule": "Most ordered products"},
    {"key": "sale", "title": "On sale", "rule": "Products with a sale price, recently updated first"},
    {"key": "new_arrivals", "title": "New arrivals", "rule": "Newest active products"},
]
SECTION_KEYS = [s["key"] for s in SECTION_DEFAULTS]
_DEFAULTS_BY_KEY = {s["key"]: s for s in SECTION_DEFAULTS}


def _default_section(key):
    return {
        "key": key,
        "title": _DEFAULTS_BY_KEY[key]["title"],
        "enabled": True,
        "mode": "auto",
        "limit": 8,
        "product_ids": [],
    }


def _on_sale_filter(query):
    return query.filter(Product.sale_price.isnot(None), Product.sale_price > 0, Product.sale_price < Product.price)


def order_stats(product_ids=None):
    """{product_id: {"units": total quantity sold, "orders": distinct orders}}."""
    query = (
        db.session.query(
            OrderItem.product_id,
            func.sum(OrderItem.quantity).label("units"),
            func.count(func.distinct(OrderItem.order_id)).label("orders"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(OrderItem.product_id.isnot(None), Order.order_status.notin_(NON_SALE_STATUSES))
        .group_by(OrderItem.product_id)
    )
    if product_ids is not None:
        query = query.filter(OrderItem.product_id.in_(product_ids))
    return {row.product_id: {"units": int(row.units or 0), "orders": int(row.orders or 0)} for row in query.all()}


class HomeSectionsService:
    @staticmethod
    def get_layout():
        """Saved layout merged with defaults: unknown keys dropped, missing
        sections appended, values clamped."""
        row = SiteContent.query.filter_by(key=STORAGE_KEY).first()
        saved = []
        if row and row.value:
            try:
                saved = json.loads(row.value)
            except (ValueError, TypeError):
                saved = []
        return HomeSectionsService._normalize(saved if isinstance(saved, list) else [])

    @staticmethod
    def _normalize(sections):
        result, seen = [], set()
        for raw in sections:
            if not isinstance(raw, dict) or raw.get("key") not in SECTION_KEYS or raw["key"] in seen:
                continue
            key = raw["key"]
            seen.add(key)
            section = _default_section(key)
            title = str(raw.get("title") or "").strip()[:80]
            section["title"] = title or section["title"]
            section["enabled"] = bool(raw.get("enabled", True))
            section["mode"] = "manual" if raw.get("mode") == "manual" else "auto"
            try:
                section["limit"] = max(1, min(MAX_LIMIT, int(raw.get("limit", 8))))
            except (TypeError, ValueError):
                pass
            ids = []
            for pid in raw.get("product_ids") or []:
                try:
                    pid = int(pid)
                except (TypeError, ValueError):
                    continue
                if pid not in ids:
                    ids.append(pid)
            section["product_ids"] = ids[:MAX_MANUAL_PRODUCTS]
            result.append(section)
        for key in SECTION_KEYS:
            if key not in seen:
                result.append(_default_section(key))
        return result

    @staticmethod
    def save_layout(sections):
        layout = HomeSectionsService._normalize(sections)
        value = json.dumps(layout)
        row = SiteContent.query.filter_by(key=STORAGE_KEY).first()
        if row is None:
            db.session.add(SiteContent(key=STORAGE_KEY, label="Homepage sections", value=value))
        else:
            row.value = value
        db.session.commit()
        return layout

    @staticmethod
    def auto_products(key, limit):
        base = Product.query.filter_by(is_active=True)
        if key in ("featured", "new_arrivals"):
            return base.order_by(Product.created_at.desc()).limit(limit).all()
        if key == "sale":
            return _on_sale_filter(base).order_by(Product.updated_at.desc()).limit(limit).all()
        if key == "trending":
            units = func.sum(OrderItem.quantity).label("units")
            rows = (
                db.session.query(Product, units)
                .join(OrderItem, OrderItem.product_id == Product.id)
                .join(Order, Order.id == OrderItem.order_id)
                .filter(Product.is_active.is_(True), Order.order_status.notin_(NON_SALE_STATUSES))
                .group_by(Product.id)
                .order_by(units.desc(), Product.id)
                .limit(limit)
                .all()
            )
            return [product for product, _units in rows]
        return []

    @staticmethod
    def manual_products(key, product_ids):
        if not product_ids:
            return []
        query = Product.query.filter(Product.id.in_(product_ids), Product.is_active.is_(True))
        if key == "sale":
            # Never advertise a product "on sale" that no longer has a discount.
            query = _on_sale_filter(query)
        by_id = {p.id: p for p in query.all()}
        return [by_id[pid] for pid in product_ids if pid in by_id]

    @staticmethod
    def homepage_sections():
        """Visible, non-empty sections in admin order, ready to render."""
        rendered = []
        for section in HomeSectionsService.get_layout():
            if not section["enabled"]:
                continue
            if section["mode"] == "manual":
                products = HomeSectionsService.manual_products(section["key"], section["product_ids"])
            else:
                products = HomeSectionsService.auto_products(section["key"], section["limit"])
            if products:
                rendered.append({**section, "products": products})
        return rendered
