from app.extensions import db
from app.models import (
    Category,
    Coupon,
    Order,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    Product,
    ProductImage,
    Subcategory,
    User,
)
from app.shop.services import CategoryService, ProductService
from app.storage import get_storage


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
        db.session.add(category)
        db.session.commit()
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
        db.session.commit()
        return category

    @staticmethod
    def delete_category(category):
        category.is_active = False
        for sub in category.subcategories:
            sub.is_active = False
        db.session.commit()

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
        db.session.add(subcategory)
        db.session.commit()
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
        db.session.commit()
        return subcategory

    @staticmethod
    def delete_subcategory(subcategory):
        subcategory.is_active = False
        db.session.commit()


class AdminProductService:
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
        product.stock_quantity = form.stock_quantity.data
        product.low_stock_threshold = form.low_stock_threshold.data
        product.is_active = form.is_active.data

    @classmethod
    def create_product(cls, form):
        existing_sku = Product.query.filter_by(sku=form.sku.data.strip().upper()).first()
        if existing_sku:
            raise AdminError(f"SKU '{form.sku.data}' is already in use.")

        product = Product(slug=ProductService.unique_slug(form.name.data))
        cls._apply_common_fields(product, form)
        db.session.add(product)
        db.session.commit()
        return product

    @classmethod
    def update_product(cls, product, form):
        existing_sku = Product.query.filter(Product.sku == form.sku.data.strip().upper(), Product.id != product.id).first()
        if existing_sku:
            raise AdminError(f"SKU '{form.sku.data}' is already in use.")

        if form.name.data != product.name:
            product.slug = ProductService.unique_slug(form.name.data, exclude_id=product.id)
        cls._apply_common_fields(product, form)
        db.session.commit()
        return product

    @staticmethod
    def toggle_active(product):
        product.is_active = not product.is_active
        db.session.commit()
        return product

    @staticmethod
    def update_stock(product, stock_quantity, low_stock_threshold):
        product.stock_quantity = stock_quantity
        product.low_stock_threshold = low_stock_threshold
        db.session.commit()
        return product

    @staticmethod
    def add_image(product, file_storage, set_as_main=False):
        url, storage_path = get_storage().upload(file_storage, folder="products")
        max_sort = max([img.sort_order for img in product.images], default=-1)
        image = ProductImage(product_id=product.id, image_url=url, storage_path=storage_path, sort_order=max_sort + 1)
        db.session.add(image)
        if set_as_main or not product.image_url:
            product.image_url = url
        db.session.commit()
        return image

    @staticmethod
    def set_main_image(product, image):
        product.image_url = image.image_url
        db.session.commit()

    @staticmethod
    def delete_image(product, image):
        get_storage().delete(image.storage_path)
        was_main = product.image_url == image.image_url
        db.session.delete(image)
        db.session.flush()
        if was_main:
            remaining = ProductImage.query.filter_by(product_id=product.id).order_by(ProductImage.sort_order).first()
            product.image_url = remaining.image_url if remaining else None
        db.session.commit()


class DashboardService:
    @staticmethod
    def get_stats():
        total_users = User.query.count()
        total_products = Product.query.count()
        total_categories = Category.query.count()
        total_orders = Order.query.count()
        pending_orders = Order.query.filter(
            Order.order_status.in_([OrderStatus.PLACED, OrderStatus.CONFIRMED, OrderStatus.PROCESSING])
        ).count()
        completed_orders = Order.query.filter(Order.order_status == OrderStatus.DELIVERED).count()
        online_payments = Order.query.filter(
            Order.payment_method == PaymentMethod.RAZORPAY, Order.payment_status == PaymentStatus.PAID
        ).count()
        cod_orders = Order.query.filter(Order.payment_method == PaymentMethod.COD).count()
        out_of_stock = Product.query.filter(Product.stock_quantity == 0).count()
        low_stock = Product.query.filter(Product.stock_quantity > 0, Product.stock_quantity <= Product.low_stock_threshold).count()

        revenue = (
            db.session.query(db.func.coalesce(db.func.sum(Order.total_amount), 0))
            .filter(Order.payment_status == PaymentStatus.PAID)
            .scalar()
        )

        recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()
        low_stock_products = (
            Product.query.filter(Product.stock_quantity > 0, Product.stock_quantity <= Product.low_stock_threshold)
            .order_by(Product.stock_quantity)
            .limit(10)
            .all()
        )
        latest_users = User.query.order_by(User.created_at.desc()).limit(10).all()

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
        db.session.commit()
        return user


class AdminCouponService:
    @staticmethod
    def create_coupon(form):
        code = form.code.data.strip().upper()
        if Coupon.query.filter_by(code=code).first():
            raise AdminError(f"Coupon code '{code}' already exists.")
        coupon = Coupon(code=code)
        AdminCouponService._apply(coupon, form)
        db.session.add(coupon)
        db.session.commit()
        return coupon

    @staticmethod
    def update_coupon(coupon, form):
        code = form.code.data.strip().upper()
        existing = Coupon.query.filter(Coupon.code == code, Coupon.id != coupon.id).first()
        if existing:
            raise AdminError(f"Coupon code '{code}' already exists.")
        coupon.code = code
        AdminCouponService._apply(coupon, form)
        db.session.commit()
        return coupon

    @staticmethod
    def _apply(coupon, form):
        coupon.discount_type = form.discount_type.data
        coupon.discount_value = form.discount_value.data
        coupon.minimum_order_value = form.minimum_order_value.data or 0
        coupon.maximum_discount = form.maximum_discount.data or None
        coupon.usage_limit = form.usage_limit.data or None
        coupon.is_active = form.is_active.data
