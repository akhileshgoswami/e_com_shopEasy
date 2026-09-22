from urllib.parse import urlparse

from flask import current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.auth import auth_bp
from app.cart.routes import PENDING_CART_SESSION_KEY
from app.cart.services import CartError, CartService
from app.auth.forms import (
    AddressForm,
    ChangePasswordForm,
    ForgotPasswordForm,
    LoginForm,
    ProfileForm,
    RegisterForm,
    ResetPasswordForm,
)
from app.auth.services import AuthError, AuthenticationService
from app.extensions import db, limiter, oauth
from app.models import Address, Order
from app.services.email_service import EmailService

GOOGLE_OAUTH_NEXT_SESSION_KEY = "google_oauth_next"


def _apply_pending_cart_action():
    """After login/register, replay an add-to-cart action that was
    interrupted by the auth requirement, so the user's intent is preserved."""
    pending = session.pop(PENDING_CART_SESSION_KEY, None)
    if not pending:
        return None
    try:
        CartService.add_item(current_user, pending["product_id"], pending.get("quantity", 1))
        flash("Item added to your cart.", "success")
        return url_for("cart.view_cart")
    except CartError as exc:
        flash(str(exc), "warning")
        return None


def _safe_next_url(target):
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.netloc or parsed.scheme:
        return None
    if not target.startswith("/") or target.startswith("//"):
        return None
    return target


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("shop.home"))

    form = RegisterForm()
    if form.validate_on_submit():
        try:
            user = AuthenticationService.register_customer(
                name=form.name.data, email=form.email.data, password=form.password.data, phone=form.phone.data
            )
        except AuthError as exc:
            flash(str(exc), "danger")
        else:
            EmailService.send_registration_confirmation(user)
            login_user(user)
            flash("Welcome! Your account has been created.", "success")
            next_url = _safe_next_url(request.args.get("next"))
            pending_redirect = _apply_pending_cart_action()
            return redirect(pending_redirect or next_url or url_for("shop.home"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login/google")
@limiter.limit("20 per hour")
def google_login():
    if not current_app.config.get("GOOGLE_OAUTH_ENABLED"):
        flash("Google sign-in is not available right now.", "danger")
        return redirect(url_for("auth.login"))

    if current_user.is_authenticated:
        return redirect(url_for("shop.home"))

    session[GOOGLE_OAUTH_NEXT_SESSION_KEY] = _safe_next_url(request.args.get("next"))
    redirect_uri = url_for("auth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/login/google/callback")
def google_callback():
    if not current_app.config.get("GOOGLE_OAUTH_ENABLED"):
        return redirect(url_for("auth.login"))

    try:
        token = oauth.google.authorize_access_token()
        userinfo = token.get("userinfo") or oauth.google.userinfo()
    except Exception:
        current_app.logger.exception("Google OAuth callback failed")
        flash("Google sign-in failed. Please try again or use email/password.", "danger")
        return redirect(url_for("auth.login"))

    try:
        user = AuthenticationService.find_or_create_google_user(
            email=userinfo.get("email"),
            name=userinfo.get("name"),
            email_verified=bool(userinfo.get("email_verified")),
        )
    except AuthError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("auth.login"))

    login_user(user)
    flash(f"Welcome, {user.name}!", "success")

    next_url = session.pop(GOOGLE_OAUTH_NEXT_SESSION_KEY, None)
    pending_redirect = _apply_pending_cart_action()
    if pending_redirect:
        return redirect(pending_redirect)
    if user.is_admin and not next_url:
        return redirect(url_for("admin.dashboard"))
    return redirect(next_url or url_for("shop.home"))


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("15 per 5 minutes")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("shop.home"))

    form = LoginForm()
    next_url = _safe_next_url(request.args.get("next") or request.form.get("next"))

    if form.validate_on_submit():
        try:
            user = AuthenticationService.authenticate(form.email.data, form.password.data)
        except AuthError as exc:
            flash(str(exc), "danger")
        else:
            login_user(user, remember=form.remember_me.data)
            flash(f"Welcome back, {user.name}!", "success")
            pending_redirect = _apply_pending_cart_action()
            if pending_redirect:
                return redirect(pending_redirect)
            if user.is_admin and not next_url:
                return redirect(url_for("admin.dashboard"))
            return redirect(next_url or url_for("shop.home"))

    return render_template("auth/login.html", form=form, next=next_url)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("shop.home"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per hour")
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        from app.models import User

        user = User.query.filter_by(email=form.email.data.strip().lower()).first()
        if user:
            token = AuthenticationService.generate_reset_token(user)
            reset_url = url_for("auth.reset_password", token=token, _external=True)
            EmailService.send_password_reset(user, reset_url)
        flash("If that email exists, a reset link has been sent.", "info")
        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html", form=form)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def reset_password(token):
    try:
        user = AuthenticationService.verify_reset_token(token)
    except AuthError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("auth.forgot_password"))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        AuthenticationService.reset_password(user, form.password.data)
        flash("Your password has been reset. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", form=form)


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        current_user.name = form.name.data
        current_user.phone = form.phone.data
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("auth.profile"))

    password_form = ChangePasswordForm()
    recent_orders = (
        Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).limit(5).all()
    )
    return render_template("auth/profile.html", form=form, password_form=password_form, recent_orders=recent_orders)


@auth_bp.route("/profile/password", methods=["POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        try:
            AuthenticationService.change_password(current_user, form.current_password.data, form.new_password.data)
        except AuthError as exc:
            flash(str(exc), "danger")
        else:
            flash("Password changed successfully.", "success")
    else:
        for errors in form.errors.values():
            for error in errors:
                flash(error, "danger")
    return redirect(url_for("auth.profile"))


@auth_bp.route("/addresses")
@login_required
def addresses():
    user_addresses = Address.query.filter_by(user_id=current_user.id).order_by(Address.is_default.desc(), Address.id.desc()).all()
    return render_template("auth/addresses.html", addresses=user_addresses)


@auth_bp.route("/addresses/new", methods=["GET", "POST"])
@login_required
def address_new():
    form = AddressForm()
    if form.validate_on_submit():
        if form.is_default.data:
            Address.query.filter_by(user_id=current_user.id, is_default=True).update({"is_default": False})
        address = Address(user_id=current_user.id)
        form.populate_obj(address)
        db.session.add(address)
        db.session.commit()
        flash("Address added.", "success")
        return redirect(url_for("auth.addresses"))
    return render_template("auth/address_form.html", form=form, is_new=True)


@auth_bp.route("/addresses/<int:address_id>/edit", methods=["GET", "POST"])
@login_required
def address_edit(address_id):
    address = Address.query.filter_by(id=address_id, user_id=current_user.id).first_or_404()
    form = AddressForm(obj=address)
    if form.validate_on_submit():
        if form.is_default.data:
            Address.query.filter(
                Address.user_id == current_user.id, Address.id != address.id
            ).update({"is_default": False})
        form.populate_obj(address)
        db.session.commit()
        flash("Address updated.", "success")
        return redirect(url_for("auth.addresses"))
    return render_template("auth/address_form.html", form=form, is_new=False, address=address)


@auth_bp.route("/addresses/<int:address_id>/delete", methods=["POST"])
@login_required
def address_delete(address_id):
    address = Address.query.filter_by(id=address_id, user_id=current_user.id).first_or_404()
    db.session.delete(address)
    db.session.commit()
    flash("Address removed.", "info")
    return redirect(url_for("auth.addresses"))


@auth_bp.route("/addresses/<int:address_id>/set-default", methods=["POST"])
@login_required
def address_set_default(address_id):
    address = Address.query.filter_by(id=address_id, user_id=current_user.id).first_or_404()
    Address.query.filter_by(user_id=current_user.id).update({"is_default": False})
    address.is_default = True
    db.session.commit()
    flash("Default address updated.", "success")
    return redirect(url_for("auth.addresses"))
