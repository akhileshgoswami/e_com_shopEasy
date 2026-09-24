from google.cloud import ndb

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
    """Centralizes stock mutation so it never goes negative.

    Callers must apply these inside an NDB transaction on entities read in
    that same transaction: if another request changes the same product
    concurrently, Datastore aborts one commit and NDB retries it against
    fresh values (optimistic concurrency, replacing SELECT ... FOR UPDATE).
    """

    @staticmethod
    def take_stock(product, quantity):
        """Decrement in memory; the caller puts the product. Raises
        InsufficientStockError if not enough stock remains."""
        if product.stock_quantity < quantity:
            raise InsufficientStockError(product, quantity, product.stock_quantity)
        product.stock_quantity -= quantity
        return product

    @staticmethod
    def return_stock(product, quantity):
        """Increment back in memory, e.g. on cancellation/failed payment/return."""
        product.stock_quantity += quantity
        return product

    @classmethod
    @ndb.transactional()
    def reserve_stock(cls, product_id, quantity):
        """Standalone transactional decrement of a single product."""
        product = Product.get_by_id(int(product_id))
        if product is None:
            raise ValueError(f"Product {product_id} not found.")
        cls.take_stock(product, quantity)
        product.put()
        return product

    @staticmethod
    def has_sufficient_stock(product, quantity):
        return product.is_active and product.stock_quantity >= quantity
