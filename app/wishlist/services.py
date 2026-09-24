from flask import g

from app.models import Product, Wishlist


class WishlistError(Exception):
    pass


class WishlistService:
    @staticmethod
    def get(user):
        return Wishlist.get_by_id(user.id)

    @classmethod
    def product_ids(cls, user):
        wishlist = cls.get(user)
        return list(wishlist.product_ids) if wishlist else []

    @classmethod
    def toggle(cls, user, product_id):
        """Add the product if it isn't saved yet, otherwise remove it.
        Returns True when the product is in the wishlist afterwards."""
        product = Product.find(product_id)
        if product is None or not product.is_active:
            raise WishlistError("This product is no longer available.")

        wishlist = cls.get(user) or Wishlist(id=user.id, user_id=user.id, product_ids=[])
        ids = list(wishlist.product_ids)
        if product.id in ids:
            ids.remove(product.id)
            added = False
        else:
            ids.insert(0, product.id)
            added = True
        wishlist.product_ids = ids
        wishlist.put()
        g.pop("wishlist_ids", None)
        return added

    @classmethod
    def add(cls, user, product_id):
        if int(product_id) not in cls.product_ids(user):
            cls.toggle(user, product_id)

    @classmethod
    def products(cls, user):
        """Saved products that are still for sale, newest first."""
        ids = cls.product_ids(user)
        found = Product.find_many(ids)
        return [found[i] for i in ids if i in found and found[i].is_active]


def current_wishlist_ids():
    """Product ids saved by the logged-in user, looked up once per request.
    Exposed to templates as in_wishlist() so imported macros can use it."""
    if "wishlist_ids" not in g:
        from flask_login import current_user

        ids = set()
        try:
            if current_user.is_authenticated:
                ids = set(WishlistService.product_ids(current_user))
        except Exception:
            ids = set()
        g.wishlist_ids = ids
    return g.wishlist_ids
