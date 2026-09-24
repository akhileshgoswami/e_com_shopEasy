from flask import abort
from slugify import slugify

from app.models import Category, Product, Subcategory
from app.utils import Pagination, contains_text

# Sorting/filtering happen in Python over the active catalog: Datastore
# would need a composite index for every filter+sort combination, and a
# shop-sized catalog fits comfortably in memory.
SORT_OPTIONS = {
    "newest": (lambda p: p.created_at, True),
    "price_low": (lambda p: p.price, False),
    "price_high": (lambda p: p.price, True),
    "name_asc": (lambda p: p.name.lower(), False),
}


def _or_404(entity):
    if entity is None:
        abort(404)
    return entity


class CategoryService:
    @staticmethod
    def list_active_categories():
        categories = Category.all(Category.is_active == True)  # noqa: E712
        return sorted(categories, key=lambda c: (c.sort_order, c.name))

    @staticmethod
    def get_by_slug_or_404(slug):
        return _or_404(Category.first(Category.slug == slug, Category.is_active == True))  # noqa: E712

    @staticmethod
    def get_subcategory_by_slug_or_404(category, slug):
        return _or_404(
            Subcategory.first(
                Subcategory.category_id == category.id,
                Subcategory.slug == slug,
                Subcategory.is_active == True,  # noqa: E712
            )
        )

    @staticmethod
    def list_active_subcategories(category_id):
        subcategories = Subcategory.all(Subcategory.category_id == category_id, Subcategory.is_active == True)  # noqa: E712
        return sorted(subcategories, key=lambda s: s.sort_order)

    @staticmethod
    def unique_slug(name, exclude_id=None, subcategory_of=None):
        base = slugify(name)
        slug = base
        counter = 2
        while True:
            if subcategory_of is not None:
                existing = Subcategory.first(Subcategory.category_id == subcategory_of, Subcategory.slug == slug)
            else:
                existing = Category.first(Category.slug == slug)
            if existing is None or existing.id == exclude_id:
                return slug
            slug = f"{base}-{counter}"
            counter += 1


class ProductService:
    @staticmethod
    def get_by_slug_or_404(slug):
        return _or_404(Product.first(Product.slug == slug, Product.is_active == True))  # noqa: E712

    @staticmethod
    def unique_slug(name, exclude_id=None):
        base = slugify(name)
        slug = base
        counter = 2
        while True:
            existing = Product.first(Product.slug == slug)
            if existing is None or existing.id == exclude_id:
                return slug
            slug = f"{base}-{counter}"
            counter += 1

    @staticmethod
    def active_products(*filters):
        return Product.all(Product.is_active == True, *filters)  # noqa: E712

    @staticmethod
    def sort(products, sort="newest"):
        key, reverse = SORT_OPTIONS.get(sort, SORT_OPTIONS["newest"])
        return sorted(products, key=key, reverse=reverse)

    @classmethod
    def search_and_filter(
        cls,
        q=None,
        category_slug=None,
        subcategory_slug=None,
        min_price=None,
        max_price=None,
        in_stock_only=False,
        on_sale_only=False,
        sort="newest",
        page=1,
        per_page=12,
    ):
        filters = []
        if category_slug:
            category = Category.first(Category.slug == category_slug)
            if category is None:
                return Pagination([], page, per_page)
            filters.append(Product.category_id == category.id)

        if subcategory_slug:
            subcategory = Subcategory.first(Subcategory.slug == subcategory_slug)
            if subcategory is None:
                return Pagination([], page, per_page)
            filters.append(Product.subcategory_id == subcategory.id)

        products = cls.active_products(*filters)

        if q:
            products = [p for p in products if contains_text(q, p.name, p.short_description, p.description)]
        if min_price is not None:
            products = [p for p in products if p.price >= min_price]
        if max_price is not None:
            products = [p for p in products if p.price <= max_price]
        if in_stock_only:
            products = [p for p in products if p.stock_quantity > 0]
        if on_sale_only:
            products = [p for p in products if p.is_on_sale]

        return Pagination(cls.sort(products, sort), page, per_page)

    @classmethod
    def related_products(cls, product, limit=4):
        if product.subcategory_id:
            candidates = cls.active_products(Product.subcategory_id == product.subcategory_id)
        else:
            candidates = cls.active_products(Product.category_id == product.category_id)
        return [p for p in candidates if p.id != product.id][:limit]
