from flask import flash, jsonify, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app.extensions import limiter
from app.wishlist import wishlist_bp
from app.wishlist.services import WishlistError, WishlistService

# Product id a guest tried to save; added to their wishlist once they log in.
PENDING_WISHLIST_SESSION_KEY = "pending_wishlist_product"


def _wants_json():
    return request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json


@wishlist_bp.route("/wishlist")
@login_required
def view_wishlist():
    return render_template("wishlist.html", products=WishlistService.products(current_user))


@wishlist_bp.route("/wishlist/toggle", methods=["POST"])
@limiter.limit("120 per hour")
def toggle():
    product_id = request.form.get("product_id", type=int) or (request.get_json(silent=True) or {}).get("product_id")
    if not product_id:
        if _wants_json():
            return jsonify({"success": False, "message": "Invalid product."}), 400
        flash("Invalid product.", "danger")
        return redirect(request.referrer or url_for("shop.home"))

    if not current_user.is_authenticated:
        session[PENDING_WISHLIST_SESSION_KEY] = int(product_id)
        login_url = url_for("auth.login", next=url_for("wishlist.view_wishlist"))
        if _wants_json():
            return jsonify({"success": False, "auth_required": True, "redirect": login_url}), 401
        flash("Please log in to save items to your wishlist.", "info")
        return redirect(login_url)

    try:
        added = WishlistService.toggle(current_user, int(product_id))
    except WishlistError as exc:
        if _wants_json():
            return jsonify({"success": False, "message": str(exc)}), 400
        flash(str(exc), "danger")
        return redirect(request.referrer or url_for("shop.home"))

    message = "Saved to your wishlist." if added else "Removed from your wishlist."
    count = len(WishlistService.product_ids(current_user))
    if _wants_json():
        return jsonify({"success": True, "in_wishlist": added, "count": count, "message": message})
    flash(message, "success" if added else "info")
    return redirect(request.referrer or url_for("wishlist.view_wishlist"))
