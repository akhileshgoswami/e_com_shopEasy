from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app.auth.forms import AddressForm
from app.checkout import checkout_bp
from app.checkout.services import CheckoutError, CheckoutService
from app.models import Address, OrderStatus, PaymentMethod
from app.services.order_service import OrderService, OrderTransitionError

COUPON_SESSION_KEY = "checkout_coupon_code"


@checkout_bp.route("/checkout", methods=["GET"])
@login_required
def checkout():
    addresses = Address.for_user(current_user.id)
    coupon_code = session.get(COUPON_SESSION_KEY)
    summary = CheckoutService.build_summary(current_user, coupon_code=coupon_code)

    if not summary["items"]:
        flash("Your cart is empty.", "info")
        return redirect(url_for("cart.view_cart"))

    for message in summary["adjustments"]:
        flash(message, "warning")

    address_form = AddressForm()
    return render_template(
        "checkout.html",
        addresses=addresses,
        summary=summary,
        address_form=address_form,
        coupon_code=coupon_code or "",
    )


@checkout_bp.route("/checkout/coupon", methods=["POST"])
@login_required
def apply_coupon():
    code = request.form.get("coupon_code", "").strip()
    if code:
        session[COUPON_SESSION_KEY] = code
    else:
        session.pop(COUPON_SESSION_KEY, None)
    return redirect(url_for("checkout.checkout"))


@checkout_bp.route("/checkout/coupon/remove", methods=["POST"])
@login_required
def remove_coupon():
    session.pop(COUPON_SESSION_KEY, None)
    return redirect(url_for("checkout.checkout"))


@checkout_bp.route("/checkout/address", methods=["POST"])
@login_required
def add_checkout_address():
    form = AddressForm()
    if form.validate_on_submit():
        if form.is_default.data:
            Address.clear_default(current_user.id)
        address = Address(user_id=current_user.id)
        form.populate_obj(address)
        address.put()
        flash("Address added.", "success")
    else:
        for errors in form.errors.values():
            for error in errors:
                flash(error, "danger")
    return redirect(url_for("checkout.checkout"))


@checkout_bp.route("/checkout/place", methods=["POST"])
@login_required
def place_order():
    address_id = request.form.get("address_id", type=int)
    payment_method = request.form.get("payment_method")
    coupon_code = session.get(COUPON_SESSION_KEY)

    address = Address.owned_by(address_id, current_user.id)
    if address is None:
        flash("Please select a shipping address.", "danger")
        return redirect(url_for("checkout.checkout"))

    if payment_method not in PaymentMethod.CHOICES:
        flash("Please select a valid payment method.", "danger")
        return redirect(url_for("checkout.checkout"))

    try:
        order = CheckoutService.create_order(current_user, address, payment_method, coupon_code=coupon_code)
    except CheckoutError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("checkout.checkout"))

    session.pop(COUPON_SESSION_KEY, None)

    if payment_method == PaymentMethod.COD:
        return redirect(url_for("checkout.order_success", order_id=order.id))

    return redirect(url_for("payments.pay", order_id=order.id))


@checkout_bp.route("/checkout/success/<int:order_id>")
@login_required
def order_success(order_id):
    order = OrderService.get_user_order_or_404(current_user, order_id)
    return render_template("order_success.html", order=order)


@checkout_bp.route("/checkout/cancel/<int:order_id>", methods=["POST"])
@login_required
def cancel_pending_order(order_id):
    order = OrderService.get_user_order_or_404(current_user, order_id)
    if order.order_status != OrderStatus.PENDING_PAYMENT:
        flash("This order can no longer be cancelled here.", "danger")
        return redirect(url_for("checkout.my_orders"))
    try:
        OrderService.change_status(order, OrderStatus.CANCELLED, changed_by=current_user.email, note="Cancelled by customer.")
        flash("Order cancelled.", "info")
    except OrderTransitionError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("checkout.my_orders"))


@checkout_bp.route("/orders")
@login_required
def my_orders():
    page = request.args.get("page", 1, type=int)
    pagination = OrderService.list_user_orders(current_user, page=page)
    return render_template("orders.html", pagination=pagination, orders=pagination.items)


@checkout_bp.route("/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    order = OrderService.get_user_order_or_404(current_user, order_id)
    return render_template("order_detail.html", order=order)
