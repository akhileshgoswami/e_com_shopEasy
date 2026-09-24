import re

from google.cloud import ndb
from slugify import slugify

from app.models import (
    Category,
    Coupon,
    Order,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    Product,
    ProductImage,
    ProductSize,
    ProductType,
    Subcategory,
    User,
)
from app.models.base import ZERO
from app.shop.services import CategoryService, ProductService
from app.storage import get_storage
from app.utils import newest_first


class AdminError(Exception):
    pass


class AdminCategoryService:
    @staticmethod
    def create_category(form):
        slug = CategoryService.unique_slug(form.name.data)
        category = Category(
            name=form.name.data,
            slug=slug,
            description=form.description.data,
            is_active=form.is_active.data,
            sort_order=form.sort_order.data or 0,
        )
        if form.image.data:
            url, _path = get_storage().upload(form.image.data, folder="categories")
            category.image_url = url
        category.put()
        return category

    @staticmethod
    def update_category(category, form):
        if form.name.data != category.name:
            category.slug = CategoryService.unique_slug(form.name.data, exclude_id=category.id)
        category.name = form.name.data
        category.description = form.description.data
        category.is_active = form.is_active.data
        category.sort_order = form.sort_order.data or 0
        if form.image.data:
            url, _path = get_storage().upload(form.image.data, folder="categories")
            category.image_url = url
        category.put()
        return category

    @staticmethod
    def delete_category(category):
        category.is_active = False
        subcategories = category.subcategories
        for sub in subcategories:
            sub.is_active = False
        ndb.put_multi([category, *subcategories])

    @staticmethod
    def create_subcategory(form):
        slug = CategoryService.unique_slug(form.name.data, subcategory_of=form.category_id.data)
        subcategory = Subcategory(
            category_id=form.category_id.data,
            name=form.name.data,
            slug=slug,
            description=form.description.data,
            is_active=form.is_active.data,
            sort_order=form.sort_order.data or 0,
        )
        if form.image.data:
            url, _path = get_storage().upload(form.image.data, folder="subcategories")
            subcategory.image_url = url
        subcategory.put()
        return subcategory

    @staticmethod
    def update_subcategory(subcategory, form):
        if form.name.data != subcategory.name or form.category_id.data != subcategory.category_id:
            subcategory.slug = CategoryService.unique_slug(
                form.name.data, exclude_id=subcategory.id, subcategory_of=form.category_id.data
            )
        subcategory.category_id = form.category_id.data
        subcategory.name = form.name.data
        subcategory.description = form.description.data
        subcategory.is_active = form.is_active.data
        subcategory.sort_order = form.sort_order.data or 0
        if form.image.data:
            url, _path = get_storage().upload(form.image.data, folder="subcategories")
            subcategory.image_url = url
        subcategory.put()
        return subcategory

    @staticmethod
    def delete_subcategory(subcategory):
        subcategory.is_active = False
        subcategory.put()


MAX_SIZES = 50
MAX_SIZE_LENGTH = 30

# Starting point for a new store; admins edit/extend these freely.
DEFAULT_PRODUCT_TYPES = [
    {"name": "Clothing", "size_label": "Size", "sizes": ["XS", "S", "M", "L", "XL", "XXL"]},
    {"name": "Bottomwear", "size_label": "Waist", "sizes": ["28", "30", "32", "34", "36", "38", "40"]},
    {"name": "Footwear", "size_label": "Shoe size", "sizes": ["UK 5", "UK 6", "UK 7", "UK 8", "UK 9", "UK 10", "UK 11"]},
    {"name": "Kids clothing", "size_label": "Age", "sizes": ["0-1 Y", "1-2 Y", "2-4 Y", "4-6 Y", "6-8 Y", "8-10 Y", "10-12 Y"]},
    {"name": "Rings", "size_label": "Ring size", "sizes": ["6", "7", "8", "9", "10", "11", "12"]},
    {"name": "Free size", "size_label": "Size", "sizes": ["Free size"]},
    {"name": "No size (electronics, home, ...)", "size_label": "Size", "sizes": []},
]


def _size_stock_field(name):
    return f"size_stock__{name}"


class AdminProductTypeService:
    @staticmethod
    def parse_sizes(raw):
        """Comma- or line-separated sizes -> list: trimmed, de-duplicated
        (case insensitive), original order kept."""
        sizes, seen = [], set()
        for part in re.split(r"[,\n]", raw or ""):
            name = " ".join(part.split())
            if not name or name.lower() in seen:
                continue
            if len(name) > MAX_SIZE_LENGTH:
                raise AdminError(f"Size '{name[:20]}...' is too long (max {MAX_SIZE_LENGTH} characters).")
            seen.add(name.lower())
            sizes.append(name)
        if len(sizes) > MAX_SIZES:
            raise AdminError(f"A product type can have at most {MAX_SIZES} sizes.")
        return sizes

    @staticmethod
    def unique_slug(name, exclude_id=None):
        base = slugify(name) or "type"
        slug, counter = base, 2
        while True:
            existing = ProductType.first(ProductType.slug == slug)
            if existing is None or existing.id == exclude_id:
                return slug
            slug = f"{base}-{counter}"
            counter += 1

    @classmethod
    def _apply(cls, product_type, form):
        product_type.name = form.name.data.strip()
        product_type.size_label = (form.size_label.data or "").strip() or "Size"
        product_type.sizes = cls.parse_sizes(form.sizes.data)
        product_type.is_active = form.is_active.data
        product_type.sort_order = form.sort_order.data or 0

    @classmethod
    def create(cls, form):
        product_type = ProductType(slug=cls.unique_slug(form.name.data))
        cls._apply(product_type, form)
        product_type.put()
        return product_type

    @classmethod
    def update(cls, product_type, form):
        """Products keep their own size list (and stock) until they're next
        saved, so editing a type never wipes stock. The label is copied
        straight away since it's only wording."""
        if form.name.data.strip() != product_type.name:
            product_type.slug = cls.unique_slug(form.name.data, exclude_id=product_type.id)
        cls._apply(product_type, form)
        products = product_type.products
        for product in products:
            product.size_label = product_type.size_label if product.sizes else None
        ndb.put_multi([product_type, *products])
        return product_type

    @staticmethod
    def deactivate(product_type):
        product_type.is_active = False
        product_type.put()

    @classmethod
    def create_defaults(cls):
        """Adds the DEFAULT_PRODUCT_TYPES that don't exist yet (by name)."""
        existing = {t.name.lower() for t in ProductType.all()}
        created = []
        for index, data in enumerate(DEFAULT_PRODUCT_TYPES):
            if data["name"].lower() in existing:
                continue
            created.append(
                ProductType(
                    name=data["name"],
                    slug=cls.unique_slug(data["name"]),
                    size_label=data["size_label"],
                    sizes=list(data["sizes"]),
                    is_active=True,
                    sort_order=index,
                )
            )
        ndb.put_multi(created)
        return created


class AdminProductService:
    @staticmethod
    def size_options(product_type, product=None, custom=()):
        """Sizes the product form offers: the type's sizes, then any size
        the product still sells that was since removed from the type (so
        its stock stays visible and editable), then sizes the admin added
        by hand for just this product."""
        names = list(product_type.sizes) if product_type else []
        extra = list(product.size_names) if product is not None else []
        for name in extra + list(custom):
            if name.lower() not in {n.lower() for n in names}:
                names.append(name)
        return names

    @classmethod
    def _apply_sizes(cls, product, form, size_input):
        """size_input is the submitted form (a MultiDict): size_on lists the
        sizes the product is sold in, size_stock__<name> their stock and
        size_custom any sizes added on the form itself. Only names offered
        by the chosen type, already on the product, or added by hand count."""
        product_type = ProductType.find(form.product_type_id.data) if form.product_type_id.data else None
        if form.product_type_id.data and product_type is None:
            raise AdminError("Please choose a valid product type.")
        product.product_type_id = product_type.id if product_type else None

        custom = (
            AdminProductTypeService.parse_sizes("\n".join(size_input.getlist("size_custom")))
            if size_input is not None
            else []
        )
        offered = cls.size_options(product_type, product if product.key else None, custom)
        if len(offered) > MAX_SIZES:
            raise AdminError(f"A product can have at most {MAX_SIZES} sizes.")
        label = (product_type.size_label if product_type else None) or "Size"
        if not offered:
            product.sizes = []
            product.size_label = None
            product.stock_quantity = form.stock_quantity.data or 0
            return

        enabled = set(size_input.getlist("size_on")) if size_input is not None else set()
        sizes = []
        for name in offered:
            if name not in enabled:
                continue
            raw = (size_input.get(_size_stock_field(name)) or "0").strip()
            try:
                stock = int(raw)
            except ValueError:
                raise AdminError(f"Stock for size '{name}' must be a whole number.")
            if stock < 0:
                raise AdminError(f"Stock for size '{name}' cannot be negative.")
            sizes.append(ProductSize(name=name, stock_quantity=stock))
        if not sizes and product_type is None:
            # Only hand-added sizes and none ticked: not sold by size.
            product.sizes = []
            product.size_label = None
            product.stock_quantity = form.stock_quantity.data or 0
            return
        if not sizes:
            raise AdminError(f"Select at least one {label.lower()} this product is sold in.")
        product.sizes = sizes
        product.size_label = label
        product.stock_quantity = sum(s.stock_quantity for s in sizes)

    @staticmethod
    def _apply_common_fields(product, form):
        product.category_id = form.category_id.data
        product.subcategory_id = form.subcategory_id.data or None
        product.name = form.name.data
        product.sku = form.sku.data.strip().upper()
        product.short_description = form.short_description.data
        product.description = form.description.data
        product.price = form.price.data
        product.sale_price = form.sale_price.data or None
        product.low_stock_threshold = form.low_stock_threshold.data
        product.is_active = form.is_active.data

    @classmethod
    def create_product(cls, form, size_input=None):
        existing_sku = Product.first(Product.sku == form.sku.data.strip().upper())
        if existing_sku:
            raise AdminError(f"SKU '{form.sku.data}' is already in use.")

        product = Product(slug=ProductService.unique_slug(form.name.data))
        cls._apply_common_fields(product, form)
        cls._apply_sizes(product, form, size_input)
        product.put()
        return product

    @classmethod
    def update_product(cls, product, form, size_input=None):
        existing_sku = Product.first(Product.sku == form.sku.data.strip().upper())
        if existing_sku and existing_sku.id != product.id:
            raise AdminError(f"SKU '{form.sku.data}' is already in use.")

        # Validate sizes on a copy first so a rejected form doesn't leave the
        # in-memory product half-updated for the re-rendered page.
        cls._apply_sizes(Product(key=product.key, sizes=list(product.sizes)), form, size_input)
        if form.name.data != product.name:
            product.slug = ProductService.unique_slug(form.name.data, exclude_id=product.id)
        cls._apply_common_fields(product, form)
        cls._apply_sizes(product, form, size_input)
        product.put()
        return product

    @staticmethod
    def toggle_active(product):
        product.is_active = not product.is_active
        product.put()
        return product

    @staticmethod
    def update_stock(product, stock_quantity, low_stock_threshold, size_input=None):
        """Sized products take per-size stock from size_input
        (size_stock__<name>); a missing value keeps that size's stock."""
        if product.has_sizes:
            for size in product.sizes:
                raw = (size_input.get(_size_stock_field(size.name)) if size_input is not None else None) or ""
                if not raw.strip():
                    continue
                try:
                    stock = int(raw)
                except ValueError:
                    raise AdminError(f"Stock for size '{size.name}' must be a whole number.")
                if stock < 0:
                    raise AdminError(f"Stock for size '{size.name}' cannot be negative.")
                size.stock_quantity = stock
        else:
            if stock_quantity is None:
                raise AdminError("Stock quantity is required.")
            product.stock_quantity = stock_quantity
        product.low_stock_threshold = low_stock_threshold
        product.put()
        return product

    @staticmethod
    def add_image(product, file_storage, set_as_main=False):
        url, storage_path = get_storage().upload(file_storage, folder="products")
        max_sort = max([img.sort_order for img in product.images], default=-1)
        image = ProductImage(product_id=product.id, image_url=url, storage_path=storage_path, sort_order=max_sort + 1)
        to_put = [image]
        if set_as_main or not product.image_url:
            product.image_url = url
            to_put.append(product)
        ndb.put_multi(to_put)
        return image

    @staticmethod
    def set_main_image(product, image):
        product.image_url = image.image_url
        product.put()

    @staticmethod
    def delete_image(product, image):
        get_storage().delete(image.storage_path)
        was_main = product.image_url == image.image_url
        image.key.delete()
        if was_main:
            remaining = product.images
            product.image_url = remaining[0].image_url if remaining else None
            product.put()


class DashboardService:
    @staticmethod
    def get_stats():
        # Counts use keys-only queries (cheap); comparisons between two
        # properties (stock vs. threshold) and sums run in Python since
        # Datastore can't express them.
        total_users = User.query().count()
        total_categories = Category.query().count()
        orders = Order.query().fetch()
        products = Product.query().fetch()

        pending_statuses = (OrderStatus.PLACED, OrderStatus.CONFIRMED, OrderStatus.PROCESSING)
        pending_orders = sum(1 for o in orders if o.order_status in pending_statuses)
        completed_orders = sum(1 for o in orders if o.order_status == OrderStatus.DELIVERED)
        online_payments = sum(
            1 for o in orders if o.payment_method == PaymentMethod.RAZORPAY and o.payment_status == PaymentStatus.PAID
        )
        cod_orders = sum(1 for o in orders if o.payment_method == PaymentMethod.COD)
        revenue = sum((o.total_amount for o in orders if o.payment_status == PaymentStatus.PAID), ZERO)

        out_of_stock = sum(1 for p in products if p.stock_quantity == 0)
        low_stock_products = sorted((p for p in products if p.is_low_stock), key=lambda p: p.stock_quantity)

        total_products = len(products)
        total_orders = len(orders)
        low_stock = len(low_stock_products)
        recent_orders = newest_first(orders)[:10]
        low_stock_products = low_stock_products[:10]
        latest_users = User.query().order(-User.created_at).fetch(10)

        return {
            "total_users": total_users,
            "total_products": total_products,
            "total_categories": total_categories,
            "total_orders": total_orders,
            "pending_orders": pending_orders,
            "completed_orders": completed_orders,
            "online_payments": online_payments,
            "cod_orders": cod_orders,
            "out_of_stock": out_of_stock,
            "low_stock": low_stock,
            "revenue": revenue,
            "recent_orders": recent_orders,
            "low_stock_products": low_stock_products,
            "latest_users": latest_users,
        }


class AdminUserService:
    @staticmethod
    def update_user(user, form):
        user.name = form.name.data
        user.role = form.role.data
        user.is_active = form.is_active.data
        user.put()
        return user


class AdminCouponService:
    @staticmethod
    def create_coupon(form):
        code = form.code.data.strip().upper()
        if Coupon.by_code(code):
            raise AdminError(f"Coupon code '{code}' already exists.")
        coupon = Coupon(code=code)
        AdminCouponService._apply(coupon, form)
        coupon.put()
        return coupon

    @staticmethod
    def update_coupon(coupon, form):
        code = form.code.data.strip().upper()
        existing = Coupon.by_code(code)
        if existing and existing.id != coupon.id:
            raise AdminError(f"Coupon code '{code}' already exists.")
        coupon.code = code
        AdminCouponService._apply(coupon, form)
        coupon.put()
        return coupon

    @staticmethod
    def _apply(coupon, form):
        coupon.discount_type = form.discount_type.data
        coupon.discount_value = form.discount_value.data
        coupon.minimum_order_value = form.minimum_order_value.data or 0
        coupon.maximum_discount = form.maximum_discount.data or None
        coupon.usage_limit = form.usage_limit.data or None
        coupon.is_active = form.is_active.data
