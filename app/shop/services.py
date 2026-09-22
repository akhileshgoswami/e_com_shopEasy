from slugify import slugify
from sqlalchemy import false, or_

from app.models import Category, Product, Subcategory

SORT_OPTIONS = {
    "newest": Product.created_at.desc(),
    "price_low": Product.price.asc(),
    "price_high": Product.price.desc(),
    "name_asc": Product.name.asc(),
}


class CategoryService:
    @staticmethod
    def list_active_categories():
        return Category.query.filter_by(is_active=True).order_by(Category.sort_order, Category.name).all()

    @staticmethod
    def get_by_slug_or_404(slug):
        return Category.query.filter_by(slug=slug, is_active=True).first_or_404()

    @staticmethod
    def get_subcategory_by_slug_or_404(category, slug):
        return Subcategory.query.filter_by(category_id=category.id, slug=slug, is_active=True).first_or_404()

    @staticmethod
    def list_active_subcategories(category_id):
        return Subcategory.query.filter_by(category_id=category_id, is_active=True).order_by(Subcategory.sort_order).all()

    @staticmethod
    def unique_slug(name, exclude_id=None, subcategory_of=None):
        base = slugify(name)
        slug = base
        counter = 2
        if subcategory_of is not None:
            query = Subcategory.query.filter_by(category_id=subcategory_of, slug=slug)
        else:
            query = Category.query.filter_by(slug=slug)
        while True:
            existing = query.first()
            if existing is None or existing.id == exclude_id:
                return slug
            slug = f"{base}-{counter}"
            counter += 1
            if subcategory_of is not None:
                query = Subcategory.query.filter_by(category_id=subcategory_of, slug=slug)
            else:
                query = Category.query.filter_by(slug=slug)


class ProductService:
    @staticmethod
    def get_by_slug_or_404(slug):
        return Product.query.filter_by(slug=slug, is_active=True).first_or_404()

    @staticmethod
    def unique_slug(name, exclude_id=None):
        base = slugify(name)
        slug = base
        counter = 2
        while True:
            existing = Product.query.filter_by(slug=slug).first()
            if existing is None or existing.id == exclude_id:
                return slug
            slug = f"{base}-{counter}"
            counter += 1

    @staticmethod
    def base_query():
        return Product.query.filter_by(is_active=True)

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
        query = cls.base_query()

        if category_slug:
            category = Category.query.filter_by(slug=category_slug).first()
            if category is None:
                query = query.filter(false())
            else:
                query = query.filter(Product.category_id == category.id)

        if subcategory_slug:
            subcategory = Subcategory.query.filter_by(slug=subcategory_slug).first()
            if subcategory is None:
                query = query.filter(false())
            else:
                query = query.filter(Product.subcategory_id == subcategory.id)

        if q:
            like = f"%{q.strip()}%"
            query = query.filter(
                or_(Product.name.ilike(like), Product.short_description.ilike(like), Product.description.ilike(like))
            )

        if min_price is not None:
            query = query.filter(Product.price >= min_price)
        if max_price is not None:
            query = query.filter(Product.price <= max_price)
        if in_stock_only:
            query = query.filter(Product.stock_quantity > 0)
        if on_sale_only:
            query = query.filter(Product.sale_price.isnot(None), Product.sale_price > 0, Product.sale_price < Product.price)

        order_clause = SORT_OPTIONS.get(sort, SORT_OPTIONS["newest"])
        query = query.order_by(order_clause)

        return query.paginate(page=page, per_page=per_page, error_out=False)

    @classmethod
    def featured_products(cls, limit=8):
        return cls.base_query().order_by(Product.created_at.desc()).limit(limit).all()

    @classmethod
    def new_products(cls, limit=8):
        return cls.base_query().order_by(Product.created_at.desc()).limit(limit).all()

    @classmethod
    def sale_products(cls, limit=8):
        return (
            cls.base_query()
            .filter(Product.sale_price.isnot(None), Product.sale_price > 0, Product.sale_price < Product.price)
            .order_by(Product.updated_at.desc())
            .limit(limit)
            .all()
        )

    @classmethod
    def related_products(cls, product, limit=4):
        query = cls.base_query().filter(Product.id != product.id)
        if product.subcategory_id:
            query = query.filter(Product.subcategory_id == product.subcategory_id)
        else:
            query = query.filter(Product.category_id == product.category_id)
        return query.limit(limit).all()
