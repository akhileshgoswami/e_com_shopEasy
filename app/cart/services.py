from decimal import Decimal

from app.extensions import db
from app.models import Cart, CartItem, Product


class CartError(Exception):
    pass


class CartService:
    @staticmethod
    def get_or_create_cart(user):
        cart = Cart.query.filter_by(user_id=user.id).first()
        if cart is None:
            cart = Cart(user_id=user.id)
            db.session.add(cart)
            db.session.commit()
        return cart

    @classmethod
    def add_item(cls, user, product_id, quantity=1):
        if quantity < 1:
            raise CartError("Quantity must be at least 1.")

        product = Product.query.filter_by(id=product_id, is_active=True).first()
        if product is None:
            raise CartError("This product is no longer available.")

        cart = cls.get_or_create_cart(user)
        item = CartItem.query.filter_by(cart_id=cart.id, product_id=product.id).first()
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
            db.session.add(item)

        db.session.commit()
        return item

    @classmethod
    def update_quantity(cls, user, item_id, quantity):
        cart = cls.get_or_create_cart(user)
        item = CartItem.query.filter_by(id=item_id, cart_id=cart.id).first()
        if item is None:
            raise CartError("Cart item not found.")

        if quantity < 1:
            db.session.delete(item)
            db.session.commit()
            return None

        if quantity > item.product.stock_quantity:
            raise CartError(f"Only {item.product.stock_quantity} unit(s) of '{item.product.name}' available.")

        item.quantity = quantity
        item.unit_price = item.product.effective_price
        db.session.commit()
        return item

    @classmethod
    def remove_item(cls, user, item_id):
        cart = cls.get_or_create_cart(user)
        item = CartItem.query.filter_by(id=item_id, cart_id=cart.id).first()
        if item is None:
            raise CartError("Cart item not found.")
        db.session.delete(item)
        db.session.commit()

    @staticmethod
    def sync_cart(cart):
        """Re-validate every line against live product state. Never trust
        stored prices/quantities blindly; returns a list of human-readable
        adjustment messages so the UI can tell the customer what changed."""
        messages = []
        for item in list(cart.items):
            product = item.product
            if product is None or not product.is_active:
                messages.append("An item in your cart is no longer available and was removed.")
                db.session.delete(item)
                continue

            if item.unit_price != product.effective_price:
                messages.append(f"Price for '{product.name}' has been updated.")
                item.unit_price = product.effective_price

            if item.quantity > product.stock_quantity:
                if product.stock_quantity <= 0:
                    messages.append(f"'{product.name}' is out of stock and was removed from your cart.")
                    db.session.delete(item)
                else:
                    messages.append(
                        f"Quantity for '{product.name}' was reduced to {product.stock_quantity} (limited stock)."
                    )
                    item.quantity = product.stock_quantity

        db.session.commit()
        return messages

    @staticmethod
    def get_totals(cart):
        subtotal = sum((item.subtotal for item in cart.items), Decimal("0.00"))
        item_count = sum(item.quantity for item in cart.items)
        return {"subtotal": subtotal, "item_count": item_count}

    @staticmethod
    def clear(cart):
        CartItem.query.filter_by(cart_id=cart.id).delete()
        db.session.commit()

    @staticmethod
    def get_item_count(user):
        cart = Cart.query.filter_by(user_id=user.id).first()
        if cart is None:
            return 0
        return db.session.query(db.func.coalesce(db.func.sum(CartItem.quantity), 0)).filter(
            CartItem.cart_id == cart.id
        ).scalar()
