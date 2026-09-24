from flask import Blueprint

wishlist_bp = Blueprint("wishlist", __name__)

from app.wishlist import routes  # noqa: E402,F401
