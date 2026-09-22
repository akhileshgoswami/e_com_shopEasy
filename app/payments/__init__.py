from flask import Blueprint

payments_bp = Blueprint("payments", __name__, template_folder="../templates/shop")

from app.payments import routes  # noqa: E402,F401
from app.payments import webhook  # noqa: E402,F401
