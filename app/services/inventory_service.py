from google.cloud import ndb

from app.models import Product, ProductSize


class InsufficientStockError(Exception):
    def __init__(self, product, requested, available, size=None):
        self.product = product
        self.requested = requested
        self.available = available
        self.size = size
        label = f"'{product.name}' ({product.display_size_label}: {size})" if size else f"'{product.name}'"
        super().__init__(f"Insufficient stock for {label}: requested {requested}, available {available}.")


class InventoryService:
    """Centralizes stock mutation so it never goes negative.

    Callers must apply these inside an NDB transaction on entities read in
    that same transaction: if another request changes the same product
    concurrently, Datastore aborts one commit and NDB retries it against
    fresh values (optimistic concurrency, replacing SELECT ... FOR UPDATE).
    """

    @staticmethod
    def take_stock(product, quantity, size=None):
        """Decrement in memory; the caller puts the product. Sized products
        decrement the chosen size (the total follows on put). Raises
        InsufficientStockError if not enough stock remains."""
        available = product.stock_for(size)
        if available < quantity:
            raise InsufficientStockError(product, quantity, available, size=size if product.has_sizes else None)
        if product.has_sizes:
            product.get_size(size).stock_quantity -= quantity
        product.stock_quantity -= quantity
        return product

    @staticmethod
    def return_stock(product, quantity, size=None):
        """Increment back in memory, e.g. on cancellation/failed payment/return.
        If the size has since been removed from a sized product it's added
        back, so the units aren't silently lost when the total is recomputed."""
        if product.has_sizes:
            entry = product.get_size(size)
            if entry is None:
                entry = ProductSize(name=size or "Other", stock_quantity=0)
                product.sizes.append(entry)
            entry.stock_quantity += quantity
        product.stock_quantity += quantity
        return product

    @classmethod
    @ndb.transactional()
    def reserve_stock(cls, product_id, quantity, size=None):
        """Standalone transactional decrement of a single product."""
        product = Product.get_by_id(int(product_id))
        if product is None:
            raise ValueError(f"Product {product_id} not found.")
        cls.take_stock(product, quantity, size)
        product.put()
        return product

    @staticmethod
    def has_sufficient_stock(product, quantity, size=None):
        return product.is_active and product.stock_for(size) >= quantity
