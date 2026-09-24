from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app.auth.forms import AddressForm
from app.cart.routes import BUY_NOW_SESSION_KEY
from app.checkout import checkout_bp
from app.checkout.services import CheckoutError, CheckoutService
from app.models import Address, OrderStatus, PaymentMethod, PaymentStatus
from app.services.order_service import OrderService, OrderTransitionError
from app.services.payment_settings_service import PaymentSettingsService

COUPON_SESSION_KEY = "checkout_coupon_code"


@checkout_bp.route("/checkout", methods=["GET"])
@login_required
def checkout():
    if request.args.get("cart"):
        session.pop(BUY_NOW_SESSION_KEY, None)
    addresses = Address.for_user(current_user.id)
    coupon_code = session.get(COUPON_SESSION_KEY)
    buy_now = session.get(BUY_NOW_SESSION_KEY)
    summary = CheckoutService.build_summary(current_user, coupon_code=coupon_code, buy_now=buy_now)

    if not summary["cart_items"]:
        if buy_now:
            session.pop(BUY_NOW_SESSION_KEY, None)
            for message in summary["adjustments"]:
                flash(message, "danger")
        else:
            flash("Your cart is empty.", "info")
        return redirect(url_for("cart.view_cart"))

    for message in summary["adjustments"]:
        flash(message, "warning")

    address_form = AddressForm()
    return render_template(
        "checkout.html",
        payment_methods=PaymentSettingsService.enabled_methods(),
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

    if payment_method not in PaymentSettingsService.enabled_methods():
        flash("Please select an available payment method.", "danger")
        return redirect(url_for("checkout.checkout"))

    try:
        order = CheckoutService.create_order(
            current_user, address, payment_method, coupon_code=coupon_code, buy_now=session.get(BUY_NOW_SESSION_KEY)
        )
    except CheckoutError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("checkout.checkout"))

    session.pop(COUPON_SESSION_KEY, None)
    session.pop(BUY_NOW_SESSION_KEY, None)

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
def cancel_order(order_id):
    order = OrderService.get_user_order_or_404(current_user, order_id)
    back = url_for("checkout.order_detail", order_id=order.id)
    if order.order_status not in OrderStatus.CUSTOMER_CANCELLABLE:
        flash("This order can no longer be cancelled. Please contact support.", "danger")
        return redirect(back)

    reason = request.form.get("reason", "").strip()
    if reason not in OrderStatus.CANCEL_REASONS:
        reason = OrderStatus.CANCEL_REASONS[0]
    details = request.form.get("reason_details", "").strip()[:300]
    if reason == OrderStatus.OTHER_REASON and not details:
        flash("Please tell us why you're cancelling.", "danger")
        return redirect(back)

    note = f"Cancelled by customer: {details if reason == OrderStatus.OTHER_REASON else reason}"
    if details and reason != OrderStatus.OTHER_REASON:
        note += f" ({details})"
    refund_due = order.payment_status == PaymentStatus.PAID
    if refund_due:
        note += " Refund due."
    try:
        OrderService.change_status(order, OrderStatus.CANCELLED, changed_by=current_user.email, note=note)
    except OrderTransitionError as exc:
        flash(str(exc), "danger")
        return redirect(back)
    flash("Order cancelled." + (" Your refund will be processed to the original payment method." if refund_due else ""), "info")
    return redirect(back)


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
    return render_template(
        "order_detail.html",
        order=order,
        cancellable_statuses=OrderStatus.CUSTOMER_CANCELLABLE,
        cancel_reasons=OrderStatus.CANCEL_REASONS,
        other_reason=OrderStatus.OTHER_REASON,
    )
