from google.cloud import ndb

from app.models.base import BaseModel, DecimalProperty


class ProductSize(ndb.Model):
    """One sellable size of a product with its own stock."""

    name = ndb.StringProperty(required=True)
    stock_quantity = ndb.IntegerProperty(default=0)

    @property
    def in_stock(self):
        return self.stock_quantity > 0


class Product(BaseModel):
    category_id = ndb.IntegerProperty(required=True)
    subcategory_id = ndb.IntegerProperty()
    product_type_id = ndb.IntegerProperty()
    name = ndb.StringProperty(required=True)
    slug = ndb.StringProperty(required=True)
    sku = ndb.StringProperty(required=True)
    short_description = ndb.TextProperty()
    description = ndb.TextProperty()
    price = DecimalProperty(required=True)
    sale_price = DecimalProperty()
    stock_quantity = ndb.IntegerProperty(default=0)
    low_stock_threshold = ndb.IntegerProperty(default=5)
    image_url = ndb.TextProperty()
    is_active = ndb.BooleanProperty(default=True)
    # Snapshot of the product type's sizes the admin chose to sell, each
    # with its own stock. Empty means the product isn't sold by size and
    # stock_quantity is the only count; otherwise stock_quantity is kept as
    # the total across sizes so listings/filters keep working unchanged.
    size_label = ndb.TextProperty()
    sizes = ndb.LocalStructuredProperty(ProductSize, repeated=True)

    def _pre_put_hook(self):
        # Mirrors the old SQL CHECK constraints.
        if any(s.stock_quantity < 0 for s in self.sizes):
            raise ValueError("Size stock cannot be negative.")
        if self.sizes:
            self.stock_quantity = sum(s.stock_quantity for s in self.sizes)
        if self.stock_quantity is not None and self.stock_quantity < 0:
            raise ValueError("stock_quantity cannot be negative.")
        if self.price is not None and self.price < 0:
            raise ValueError("price cannot be negative.")

    @property
    def category(self):
        from app.models.category import Category

        return Category.find(self.category_id)

    @property
    def subcategory(self):
        from app.models.category import Subcategory

        return Subcategory.find(self.subcategory_id)

    @property
    def product_type(self):
        from app.models.product_type import ProductType

        return ProductType.find(self.product_type_id)

    @property
    def has_sizes(self):
        return bool(self.sizes)

    @property
    def size_names(self):
        return [s.name for s in self.sizes]

    @property
    def display_size_label(self):
        return self.size_label or "Size"

    def get_size(self, name):
        for size in self.sizes:
            if size.name == name:
                return size
        return None

    def stock_for(self, size=None):
        """Units available for a cart line: the size's own stock for sized
        products (0 if the size isn't sold), otherwise the product stock."""
        if not self.has_sizes:
            return self.stock_quantity
        entry = self.get_size(size)
        return entry.stock_quantity if entry else 0

    @property
    def images(self):
        return sorted(ProductImage.all(ProductImage.product_id == self.id), key=lambda i: i.sort_order)

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


class ProductImage(BaseModel):
    product_id = ndb.IntegerProperty(required=True)
    image_url = ndb.TextProperty(required=True)
    storage_path = ndb.TextProperty(required=True)
    sort_order = ndb.IntegerProperty(default=0)

    @property
    def product(self):
        return Product.find(self.product_id)

    def __repr__(self):
        return f"<ProductImage {self.id} product={self.product_id}>"
