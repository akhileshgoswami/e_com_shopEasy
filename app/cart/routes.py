from flask import flash, jsonify, redirect, request, render_template, session, url_for
from flask_login import current_user, login_required

from app.cart import cart_bp
from app.cart.services import CartError, CartService

PENDING_CART_SESSION_KEY = "pending_cart_action"


def _wants_json():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json


@cart_bp.route("/cart/add", methods=["POST"])
def add_to_cart():
    product_id = request.form.get("product_id", type=int) or (request.get_json(silent=True) or {}).get("product_id")
    quantity = request.form.get("quantity", 1, type=int) or (request.get_json(silent=True) or {}).get("quantity", 1)

    if not product_id:
        if _wants_json():
            return jsonify({"success": False, "message": "Invalid product."}), 400
        flash("Invalid product.", "danger")
        return redirect(request.referrer or url_for("shop.home"))

    if not current_user.is_authenticated:
        session[PENDING_CART_SESSION_KEY] = {"product_id": int(product_id), "quantity": int(quantity)}
        next_url = url_for("cart.view_cart")
        if _wants_json():
            return jsonify({"success": False, "auth_required": True, "redirect": url_for("auth.login", next=next_url)}), 401
        flash("Please log in to add items to your cart.", "info")
        return redirect(url_for("auth.login", next=next_url))

    try:
        CartService.add_item(current_user, int(product_id), int(quantity))
    except CartError as exc:
        if _wants_json():
            return jsonify({"success": False, "message": str(exc)}), 400
        flash(str(exc), "danger")
        return redirect(request.referrer or url_for("shop.home"))

    item_count = CartService.get_item_count(current_user)
    if _wants_json():
        return jsonify({"success": True, "message": "Added to cart.", "item_count": item_count})
    flash("Added to cart.", "success")
    return redirect(request.referrer or url_for("cart.view_cart"))


@cart_bp.route("/cart")
@login_required
def view_cart():
    cart = CartService.get_or_create_cart(current_user)
    adjustments = CartService.sync_cart(cart)
    for message in adjustments:
        flash(message, "warning")
    totals = CartService.get_totals(cart)
    return render_template("cart.html", cart=cart, totals=totals)


@cart_bp.route("/cart/update/<int:item_id>", methods=["POST"])
@login_required
def update_item(item_id):
    quantity = request.form.get("quantity", type=int, default=1)
    try:
        CartService.update_quantity(current_user, item_id, quantity)
    except CartError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("cart.view_cart"))


@cart_bp.route("/cart/remove/<int:item_id>", methods=["POST"])
@login_required
def remove_item(item_id):
    try:
        CartService.remove_item(current_user, item_id)
        flash("Item removed from cart.", "info")
    except CartError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("cart.view_cart"))
