from google.cloud import ndb

from app.models.base import BaseModel


class Category(BaseModel):
    name = ndb.StringProperty(required=True)
    slug = ndb.StringProperty(required=True)
    description = ndb.TextProperty()
    image_url = ndb.TextProperty()
    is_active = ndb.BooleanProperty(default=True)
    sort_order = ndb.IntegerProperty(default=0)

    @property
    def subcategories(self):
        return sorted(Subcategory.all(Subcategory.category_id == self.id), key=lambda s: s.sort_order)

    @property
    def products(self):
        from app.models.product import Product

        return Product.all(Product.category_id == self.id)

    def __repr__(self):
        return f"<Category {self.slug}>"


class Subcategory(BaseModel):
    category_id = ndb.IntegerProperty(required=True)
    name = ndb.StringProperty(required=True)
    slug = ndb.StringProperty(required=True)
    description = ndb.TextProperty()
    image_url = ndb.TextProperty()
    is_active = ndb.BooleanProperty(default=True)
    sort_order = ndb.IntegerProperty(default=0)

    @property
    def category(self):
        return Category.find(self.category_id)

    @property
    def products(self):
        from app.models.product import Product

        return Product.all(Product.subcategory_id == self.id)

    def __repr__(self):
        return f"<Subcategory {self.slug}>"
