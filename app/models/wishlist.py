from google.cloud import ndb

from app.models.base import BaseModel


class Wishlist(BaseModel):
    """One per user, keyed by the user id like Cart. Product ids are kept
    newest first so the wishlist page reads in the order things were saved."""

    user_id = ndb.IntegerProperty(required=True)
    product_ids = ndb.IntegerProperty(repeated=True, indexed=False)

    def __repr__(self):
        return f"<Wishlist {self.id} user={self.user_id} items={len(self.product_ids)}>"
