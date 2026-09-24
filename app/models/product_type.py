from google.cloud import ndb

from app.models.base import BaseModel


class ProductType(BaseModel):
    """Admin-managed kind of product ("Clothing", "Footwear", ...) that
    decides which sizes a product of that type can be sold in. A type with
    no sizes (e.g. "Electronics") means products keep a single stock count."""

    name = ndb.StringProperty(required=True)
    slug = ndb.StringProperty(required=True)
    # What the storefront calls the choice: "Size", "Shoe size", "Waist", ...
    size_label = ndb.TextProperty(default="Size")
    sizes = ndb.TextProperty(repeated=True)
    is_active = ndb.BooleanProperty(default=True)
    sort_order = ndb.IntegerProperty(default=0)

    @property
    def has_sizes(self):
        return bool(self.sizes)

    @property
    def products(self):
        from app.models.product import Product

        return Product.all(Product.product_type_id == self.id)

    def __repr__(self):
        return f"<ProductType {self.slug}>"
