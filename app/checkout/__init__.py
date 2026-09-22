from flask import Blueprint

checkout_bp = Blueprint("checkout", __name__, template_folder="../templates/shop")

from app.checkout import routes  # noqa: E402,F401
