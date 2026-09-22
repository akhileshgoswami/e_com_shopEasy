from app.extensions import db
from app.models import Product


class InsufficientStockError(Exception):
    def __init__(self, product, requested, available):
        self.product = product
        self.requested = requested
        self.available = available
        super().__init__(
            f"Insufficient stock for '{product.name}': requested {requested}, available {available}."
        )


class InventoryService:
    """Centralizes stock mutation so it always happens under a row lock,
    inside the caller's transaction, and never goes negative."""

    @staticmethod
    def lock_product(product_id):
        """SELECT ... FOR UPDATE to serialize concurrent stock changes.

        SQLite (used only in tests/dev) does not support row locking and
        ignores with_for_update, which is acceptable there because SQLite
        already serializes writers at the database level.
        """
        query = db.session.query(Product).filter(Product.id == product_id)
        if db.engine.name != "sqlite":
            query = query.with_for_update()
        return query.first()

    @classmethod
    def reserve_stock(cls, product_id, quantity):
        """Decrement stock for a confirmed order. Raises InsufficientStockError
        if not enough stock remains. Must be called within an active transaction."""
        product = cls.lock_product(product_id)
        if product is None:
            raise ValueError(f"Product {product_id} not found.")
        if product.stock_quantity < quantity:
            raise InsufficientStockError(product, quantity, product.stock_quantity)
        product.stock_quantity -= quantity
        return product

    @classmethod
    def restore_stock(cls, product_id, quantity):
        """Increment stock back, e.g. on cancellation/failed payment/return."""
        product = cls.lock_product(product_id)
        if product is None:
            return None
        product.stock_quantity += quantity
        return product

    @staticmethod
    def has_sufficient_stock(product, quantity):
        return product.is_active and product.stock_quantity >= quantity
