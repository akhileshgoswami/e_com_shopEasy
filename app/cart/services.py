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

    @staticmethod
    def resolve_size(product, size):
        """The size a cart line should carry: must be one of the product's
        sizes for sized products, and is dropped for everything else."""
        if not product.has_sizes:
            return None
        size = (size or "").strip()
        if not size:
            raise CartError(f"Please select a {product.display_size_label.lower()} for '{product.name}'.")
        if product.get_size(size) is None:
            raise CartError(f"{product.display_size_label} '{size}' is not available for '{product.name}'.")
        return size

    @staticmethod
    def line_label(product, size):
        return f"'{product.name}' ({product.display_size_label}: {size})" if size else f"'{product.name}'"

    @staticmethod
    def find_line(cart_id, product_id, size=None):
        # size isn't indexed; a cart holds few lines per product anyway.
        for item in CartItem.all(CartItem.cart_id == cart_id, CartItem.product_id == product_id):
            if (item.size or None) == (size or None):
                return item
        return None

    @classmethod
    def add_item(cls, user, product_id, quantity=1, size=None):
        if quantity < 1:
            raise CartError("Quantity must be at least 1.")

        product = Product.find(product_id)
        if product is None or not product.is_active:
            raise CartError("This product is no longer available.")
        size = cls.resolve_size(product, size)

        cart = cls.get_or_create_cart(user)
        item = cls.find_line(cart.id, product.id, size)
        desired_qty = quantity + (item.quantity if item else 0)

        available = product.stock_for(size)
        if desired_qty > available:
            if available <= 0:
                raise CartError(f"{cls.line_label(product, size)} is out of stock.")
            raise CartError(f"Only {available} unit(s) of {cls.line_label(product, size)} available.")

        if item:
            item.quantity = desired_qty
            item.unit_price = product.effective_price
        else:
            item = CartItem(
                cart_id=cart.id, product_id=product.id, size=size, quantity=desired_qty, unit_price=product.effective_price
            )

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
        available = product.stock_for(item.size)
        if quantity > available:
            raise CartError(f"Only {available} unit(s) of {cls.line_label(product, item.size)} available.")

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
            if product.has_sizes and product.get_size(item.size) is None:
                messages.append(
                    f"{product.display_size_label} '{item.size or '-'}' of '{product.name}' is no longer available "
                    "and was removed from your cart."
                )
                to_delete.append(item.key)
                continue
            if not product.has_sizes and item.size:
                item.size = None
                changed = True

            if item.unit_price != product.effective_price:
                messages.append(f"Price for '{product.name}' has been updated.")
                item.unit_price = product.effective_price
                changed = True

            available = product.stock_for(item.size)
            label = CartService.line_label(product, item.size)
            if item.quantity > available:
                if available <= 0:
                    messages.append(f"{label} is out of stock and was removed from your cart.")
                    to_delete.append(item.key)
                    continue
                messages.append(f"Quantity for {label} was reduced to {available} (limited stock).")
                item.quantity = available
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
