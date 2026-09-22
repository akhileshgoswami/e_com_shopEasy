from flask import Blueprint

cart_bp = Blueprint("cart", __name__, template_folder="../templates/shop")

from app.cart import routes  # noqa: E402,F401
