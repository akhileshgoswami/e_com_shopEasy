from datetime import datetime, timezone

from app.extensions import db


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False, index=True)
    subcategory_id = db.Column(db.Integer, db.ForeignKey("subcategories.id"), nullable=True, index=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(220), nullable=False, unique=True, index=True)
    sku = db.Column(db.String(64), nullable=False, unique=True, index=True)
    short_description = db.Column(db.String(500), nullable=True)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    sale_price = db.Column(db.Numeric(10, 2), nullable=True)
    stock_quantity = db.Column(db.Integer, nullable=False, default=0)
    low_stock_threshold = db.Column(db.Integer, nullable=False, default=5)
    image_url = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        db.CheckConstraint("stock_quantity >= 0", name="ck_product_stock_nonnegative"),
        db.CheckConstraint("price >= 0", name="ck_product_price_nonnegative"),
    )

    category = db.relationship("Category", back_populates="products")
    subcategory = db.relationship("Subcategory", back_populates="products")
    images = db.relationship(
        "ProductImage", back_populates="product", cascade="all, delete-orphan", order_by="ProductImage.sort_order"
    )

    @property
    def effective_price(self):
        if self.sale_price is not None and self.sale_price > 0 and self.sale_price < self.price:
            return self.sale_price
        return self.price

    @property
    def discount_percent(self):
        if self.sale_price is not None and self.sale_price > 0 and self.sale_price < self.price:
            return round((1 - (self.sale_price / self.price)) * 100)
        return 0

    @property
    def is_on_sale(self):
        return self.discount_percent > 0

    @property
    def in_stock(self):
        return self.stock_quantity > 0

    @property
    def is_low_stock(self):
        return 0 < self.stock_quantity <= self.low_stock_threshold

    def __repr__(self):
        return f"<Product {self.slug}>"


class ProductImage(db.Model):
    __tablename__ = "product_images"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    image_url = db.Column(db.String(500), nullable=False)
    storage_path = db.Column(db.String(500), nullable=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    product = db.relationship("Product", back_populates="images")

    def __repr__(self):
        return f"<ProductImage {self.id} product={self.product_id}>"
