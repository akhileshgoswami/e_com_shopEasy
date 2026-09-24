from google.cloud import ndb

from app.models.base import BaseModel, DecimalProperty


class Cart(BaseModel):
    """One per user; the entity id *is* the user id, so the lookup is a
    direct key get and a second cart for the same user can't exist."""

    user_id = ndb.IntegerProperty(required=True)

    @property
    def user(self):
        from app.models.user import User

        return User.find(self.user_id)

    @property
    def items(self):
        return CartItem.all(CartItem.cart_id == self.id)

    def __repr__(self):
        return f"<Cart {self.id} user={self.user_id}>"


class CartItem(BaseModel):
    cart_id = ndb.IntegerProperty(required=True)
    product_id = ndb.IntegerProperty(required=True)
    # Chosen size for sized products; None otherwise. The same product in
    # two sizes is two cart lines.
    size = ndb.TextProperty()
    quantity = ndb.IntegerProperty(default=1, indexed=False)
    unit_price = DecimalProperty(required=True, indexed=False)

    def _pre_put_hook(self):
        if self.quantity is None or self.quantity < 1:
            raise ValueError("Cart item quantity must be positive.")

    @property
    def product(self):
        from app.models.product import Product

        return Product.find(self.product_id)

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    def __repr__(self):
        return f"<CartItem {self.id} product={self.product_id} qty={self.quantity}>"
