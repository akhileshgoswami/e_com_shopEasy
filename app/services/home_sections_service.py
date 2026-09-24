"""Admin-managed homepage product sections (Featured, Trending, On sale,
New arrivals).

Each section is either "auto" (products picked by the built-in rule, same as
the storefront always did) or "manual" (admin picks the products and their
order). Sections can be hidden and reordered. The whole layout is stored as a
single JSON row in ``site_content``.
"""

import json

from collections import defaultdict

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


def _active_products():
    return Product.all(Product.is_active == True)  # noqa: E712


def order_stats(product_ids=None):
    """{product_id: {"units": total quantity sold, "orders": distinct orders}}.

    Datastore has no joins/GROUP BY, so this aggregates in Python over
    every order line — fine at shop scale; move to a precomputed counter
    if order volume grows large."""
    sold_order_ids = {
        key.id() for key in Order.query().fetch(keys_only=True)
    } - {
        key.id() for key in Order.query(Order.order_status.IN(NON_SALE_STATUSES)).fetch(keys_only=True)
    }
    units = defaultdict(int)
    orders = defaultdict(set)
    wanted = set(product_ids) if product_ids is not None else None
    for item in OrderItem.query().fetch():
        if item.product_id is None or item.order_id not in sold_order_ids:
            continue
        if wanted is not None and item.product_id not in wanted:
            continue
        units[item.product_id] += item.quantity or 0
        orders[item.product_id].add(item.order_id)
    return {pid: {"units": units[pid], "orders": len(orders[pid])} for pid in units}


class HomeSectionsService:
    @staticmethod
    def get_layout():
        """Saved layout merged with defaults: unknown keys dropped, missing
        sections appended, values clamped."""
        row = SiteContent.get_by_id(STORAGE_KEY)
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
        row = SiteContent.get_by_id(STORAGE_KEY) or SiteContent(id=STORAGE_KEY, label="Homepage sections")
        row.value = value
        row.put()
        return layout

    @staticmethod
    def auto_products(key, limit):
        if key in ("featured", "new_arrivals"):
            return sorted(_active_products(), key=lambda p: p.created_at, reverse=True)[:limit]
        if key == "sale":
            on_sale = [p for p in _active_products() if p.is_on_sale]
            return sorted(on_sale, key=lambda p: p.updated_at, reverse=True)[:limit]
        if key == "trending":
            stats = order_stats()
            if not stats:
                return []
            products = [p for p in Product.find_many(stats).values() if p.is_active]
            return sorted(products, key=lambda p: (-stats[p.id]["units"], p.id))[:limit]
        return []

    @staticmethod
    def manual_products(key, product_ids):
        if not product_ids:
            return []
        by_id = {pid: p for pid, p in Product.find_many(product_ids).items() if p.is_active}
        if key == "sale":
            # Never advertise a product "on sale" that no longer has a discount.
            by_id = {pid: p for pid, p in by_id.items() if p.is_on_sale}
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
