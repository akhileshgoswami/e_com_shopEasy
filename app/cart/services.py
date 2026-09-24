from decimal import Decimal

from google.cloud import ndb

from app.models import Cart, CartItem, Product


class CartError(Exception):
    pass


class CartService:
    @staticmethod
    def get_or_create_cart(user):
        cart = Cart.get_by_id(user.id)
        if cart is None:
            cart = Cart(id=user.id, user_id=user.id)
            cart.put()
        return cart

    @staticmethod
    def _find_item(cart, item_id):
        item = CartItem.find(item_id)
        if item is None or item.cart_id != cart.id:
            raise CartError("Cart item not found.")
        return item

    @classmethod
    def add_item(cls, user, product_id, quantity=1):
        if quantity < 1:
            raise CartError("Quantity must be at least 1.")

        product = Product.find(product_id)
        if product is None or not product.is_active:
            raise CartError("This product is no longer available.")

        cart = cls.get_or_create_cart(user)
        item = CartItem.first(CartItem.cart_id == cart.id, CartItem.product_id == product.id)
        desired_qty = quantity + (item.quantity if item else 0)

        if desired_qty > product.stock_quantity:
            raise CartError(
                f"Only {product.stock_quantity} unit(s) of '{product.name}' available."
            )

        if item:
            item.quantity = desired_qty
            item.unit_price = product.effective_price
        else:
            item = CartItem(cart_id=cart.id, product_id=product.id, quantity=desired_qty, unit_price=product.effective_price)

        item.put()
        return item

    @classmethod
    def update_quantity(cls, user, item_id, quantity):
        cart = cls.get_or_create_cart(user)
        item = cls._find_item(cart, item_id)

        if quantity < 1:
            item.key.delete()
            return None

        product = item.product
        if quantity > product.stock_quantity:
            raise CartError(f"Only {product.stock_quantity} unit(s) of '{product.name}' available.")

        item.quantity = quantity
        item.unit_price = product.effective_price
        item.put()
        return item

    @classmethod
    def remove_item(cls, user, item_id):
        cart = cls.get_or_create_cart(user)
        cls._find_item(cart, item_id).key.delete()

    @staticmethod
    def sync_cart(cart):
        """Re-validate every line against live product state. Never trust
        stored prices/quantities blindly; returns a list of human-readable
        adjustment messages so the UI can tell the customer what changed."""
        messages = []
        items = cart.items
        products = Product.find_many(item.product_id for item in items)
        to_put, to_delete = [], []
        for item in items:
            product = products.get(item.product_id)
            if product is None or not product.is_active:
                messages.append("An item in your cart is no longer available and was removed.")
                to_delete.append(item.key)
                continue

            changed = False
            if item.unit_price != product.effective_price:
                messages.append(f"Price for '{product.name}' has been updated.")
                item.unit_price = product.effective_price
                changed = True

            if item.quantity > product.stock_quantity:
                if product.stock_quantity <= 0:
                    messages.append(f"'{product.name}' is out of stock and was removed from your cart.")
                    to_delete.append(item.key)
                    continue
                messages.append(
                    f"Quantity for '{product.name}' was reduced to {product.stock_quantity} (limited stock)."
                )
                item.quantity = product.stock_quantity
                changed = True

            if changed:
                to_put.append(item)

        ndb.put_multi(to_put)
        ndb.delete_multi(to_delete)
        return messages

    @staticmethod
    def get_totals(cart, items=None):
        """Pass the items already being rendered so the totals and the
        listed lines always come from the same read."""
        items = cart.items if items is None else items
        subtotal = sum((item.subtotal for item in items), Decimal("0.00"))
        item_count = sum(item.quantity for item in items)
        return {"subtotal": subtotal, "item_count": item_count}

    @staticmethod
    def clear(cart):
        ndb.delete_multi(CartItem.query(CartItem.cart_id == cart.id).fetch(keys_only=True))

    @staticmethod
    def get_item_count(user):
        # The cart id is the user id, so there's no need to load the cart.
        return sum(item.quantity for item in CartItem.all(CartItem.cart_id == user.id))
