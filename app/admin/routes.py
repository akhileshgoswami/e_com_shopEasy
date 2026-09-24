from functools import wraps

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.admin import admin_bp
from app.admin.forms import (
    AdminLoginForm,
    BrandingForm,
    HeroBannerForm,
    HomeSectionsForm,
    CategoryForm,
    CouponForm,
    OrderStatusForm,
    PaymentSettingsForm,
    ProductForm,
    ProductImageForm,
    SiteContentForm,
    StorefrontForm,
    StockUpdateForm,
    SubcategoryForm,
    UserEditForm,
)
from app.admin.services import (
    AdminCategoryService,
    AdminCouponService,
    AdminError,
    AdminProductService,
    AdminUserService,
    DashboardService,
)
from app.auth.services import AuthError, AuthenticationService
from app.extensions import limiter
from app.models import Category, Coupon, Order, OrderStatus, Payment, Product, ProductImage, Subcategory, User
from app.storage import UnsupportedFileError
from app.utils import Pagination, contains_text, newest_first

ADMIN_PER_PAGE = 20


def _by_name(entities):
    return sorted(entities, key=lambda e: e.name.lower())


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("admin.login", next=request.path))
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped


@admin_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("15 per 5 minutes")
def login():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for("admin.dashboard"))

    form = AdminLoginForm()
    if form.validate_on_submit():
        try:
            user = AuthenticationService.authenticate(form.email.data, form.password.data)
        except AuthError as exc:
            flash(str(exc), "danger")
        else:
            if not user.is_admin:
                flash("This account does not have admin access.", "danger")
            else:
                login_user(user)
                return redirect(request.args.get("next") or url_for("admin.dashboard"))

    return render_template("admin/login.html", form=form)


@admin_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("admin.login"))


@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    stats = DashboardService.get_stats()
    return render_template("admin/dashboard.html", stats=stats)


# ---------- Categories ----------

@admin_bp.route("/categories")
@admin_required
def categories():
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    categories = Category.all()
    if q:
        categories = [c for c in categories if contains_text(q, c.name)]
    categories = sorted(categories, key=lambda c: (c.sort_order, c.name))
    pagination = Pagination(categories, page, ADMIN_PER_PAGE)
    return render_template("admin/categories_list.html", pagination=pagination, categories=pagination.items, q=q)


@admin_bp.route("/categories/new", methods=["GET", "POST"])
@admin_required
def category_new():
    form = CategoryForm()
    if form.validate_on_submit():
        try:
            AdminCategoryService.create_category(form)
            flash("Category created.", "success")
            return redirect(url_for("admin.categories"))
        except UnsupportedFileError as exc:
            flash(str(exc), "danger")
    return render_template("admin/category_form.html", form=form, is_new=True)


@admin_bp.route("/categories/<int:category_id>/edit", methods=["GET", "POST"])
@admin_required
def category_edit(category_id):
    category = Category.find_or_404(category_id)
    form = CategoryForm(obj=category)
    if form.validate_on_submit():
        try:
            AdminCategoryService.update_category(category, form)
            flash("Category updated.", "success")
            return redirect(url_for("admin.categories"))
        except UnsupportedFileError as exc:
            flash(str(exc), "danger")
    return render_template("admin/category_form.html", form=form, is_new=False, category=category)


@admin_bp.route("/categories/<int:category_id>/delete", methods=["POST"])
@admin_required
def category_delete(category_id):
    category = Category.find_or_404(category_id)
    AdminCategoryService.delete_category(category)
    flash("Category deactivated.", "info")
    return redirect(url_for("admin.categories"))


# ---------- Subcategories ----------

@admin_bp.route("/subcategories")
@admin_required
def subcategories():
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    category_id = request.args.get("category_id", type=int)
    subcategories = Subcategory.all(Subcategory.category_id == category_id) if category_id else Subcategory.all()
    if q:
        subcategories = [s for s in subcategories if contains_text(q, s.name)]
    subcategories = sorted(subcategories, key=lambda s: (s.sort_order, s.name))
    pagination = Pagination(subcategories, page, ADMIN_PER_PAGE)
    all_categories = _by_name(Category.all())
    return render_template(
        "admin/subcategories_list.html",
        pagination=pagination,
        subcategories=pagination.items,
        q=q,
        categories=all_categories,
        selected_category_id=category_id,
    )


@admin_bp.route("/subcategories/new", methods=["GET", "POST"])
@admin_required
def subcategory_new():
    form = SubcategoryForm()
    form.category_id.choices = [(c.id, c.name) for c in _by_name(Category.all())]
    if form.validate_on_submit():
        try:
            AdminCategoryService.create_subcategory(form)
            flash("Subcategory created.", "success")
            return redirect(url_for("admin.subcategories"))
        except UnsupportedFileError as exc:
            flash(str(exc), "danger")
    return render_template("admin/subcategory_form.html", form=form, is_new=True)


@admin_bp.route("/subcategories/<int:subcategory_id>/edit", methods=["GET", "POST"])
@admin_required
def subcategory_edit(subcategory_id):
    subcategory = Subcategory.find_or_404(subcategory_id)
    form = SubcategoryForm(obj=subcategory)
    form.category_id.choices = [(c.id, c.name) for c in _by_name(Category.all())]
    if form.validate_on_submit():
        try:
            AdminCategoryService.update_subcategory(subcategory, form)
            flash("Subcategory updated.", "success")
            return redirect(url_for("admin.subcategories"))
        except UnsupportedFileError as exc:
            flash(str(exc), "danger")
    return render_template("admin/subcategory_form.html", form=form, is_new=False, subcategory=subcategory)


@admin_bp.route("/subcategories/<int:subcategory_id>/delete", methods=["POST"])
@admin_required
def subcategory_delete(subcategory_id):
    subcategory = Subcategory.find_or_404(subcategory_id)
    AdminCategoryService.delete_subcategory(subcategory)
    flash("Subcategory deactivated.", "info")
    return redirect(url_for("admin.subcategories"))


# ---------- Products ----------

@admin_bp.route("/products")
@admin_required
def products():
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    products = Product.all()
    if q:
        products = [p for p in products if contains_text(q, p.name, p.sku)]
    if status == "active":
        products = [p for p in products if p.is_active]
    elif status == "inactive":
        products = [p for p in products if not p.is_active]
    elif status == "out_of_stock":
        products = [p for p in products if p.stock_quantity == 0]
    elif status == "low_stock":
        products = [p for p in products if p.is_low_stock]

    pagination = Pagination(newest_first(products), page, ADMIN_PER_PAGE)
    return render_template("admin/products_list.html", pagination=pagination, products=pagination.items, q=q, status=status)


def _populate_product_choices(form):
    categories = _by_name(Category.all())
    names = {c.id: c.name for c in categories}
    form.category_id.choices = [(c.id, c.name) for c in categories]
    form.subcategory_id.choices = [(0, "-- none --")] + [
        (s.id, f"{names.get(s.category_id, '?')} / {s.name}") for s in _by_name(Subcategory.all())
    ]


@admin_bp.route("/products/new", methods=["GET", "POST"])
@admin_required
def product_new():
    form = ProductForm()
    _populate_product_choices(form)
    if form.validate_on_submit():
        try:
            product = AdminProductService.create_product(form)
            flash("Product created. You can now upload images.", "success")
            return redirect(url_for("admin.product_edit", product_id=product.id))
        except AdminError as exc:
            flash(str(exc), "danger")
    return render_template("admin/product_form.html", form=form, is_new=True)


@admin_bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def product_edit(product_id):
    product = Product.find_or_404(product_id)
    form = ProductForm(obj=product)
    _populate_product_choices(form)
    if request.method == "GET":
        form.subcategory_id.data = product.subcategory_id or 0

    if form.validate_on_submit():
        try:
            AdminProductService.update_product(product, form)
            flash("Product updated.", "success")
            return redirect(url_for("admin.product_edit", product_id=product.id))
        except AdminError as exc:
            flash(str(exc), "danger")

    image_form = ProductImageForm()
    return render_template("admin/product_form.html", form=form, is_new=False, product=product, image_form=image_form)


@admin_bp.route("/products/<int:product_id>/toggle-active", methods=["POST"])
@admin_required
def product_toggle_active(product_id):
    product = Product.find_or_404(product_id)
    AdminProductService.toggle_active(product)
    flash(f"Product {'activated' if product.is_active else 'deactivated'}.", "success")
    return redirect(url_for("admin.products"))


@admin_bp.route("/products/<int:product_id>/images", methods=["POST"])
@admin_required
def product_image_upload(product_id):
    product = Product.find_or_404(product_id)
    form = ProductImageForm()
    if form.validate_on_submit():
        try:
            AdminProductService.add_image(product, form.image.data)
            flash("Image uploaded.", "success")
        except UnsupportedFileError as exc:
            flash(str(exc), "danger")
    else:
        flash("Please choose a valid image file.", "danger")
    return redirect(url_for("admin.product_edit", product_id=product.id))


def _product_image_or_404(product, image_id):
    image = ProductImage.find(image_id)
    if image is None or image.product_id != product.id:
        abort(404)
    return image


@admin_bp.route("/products/<int:product_id>/images/<int:image_id>/set-main", methods=["POST"])
@admin_required
def product_image_set_main(product_id, image_id):
    product = Product.find_or_404(product_id)
    image = _product_image_or_404(product, image_id)
    AdminProductService.set_main_image(product, image)
    flash("Main image updated.", "success")
    return redirect(url_for("admin.product_edit", product_id=product.id))


@admin_bp.route("/products/<int:product_id>/images/<int:image_id>/delete", methods=["POST"])
@admin_required
def product_image_delete(product_id, image_id):
    product = Product.find_or_404(product_id)
    image = _product_image_or_404(product, image_id)
    AdminProductService.delete_image(product, image)
    flash("Image deleted.", "info")
    return redirect(url_for("admin.product_edit", product_id=product.id))


# ---------- Inventory ----------

@admin_bp.route("/inventory")
@admin_required
def inventory():
    page = request.args.get("page", 1, type=int)
    filter_type = request.args.get("filter", "")
    products = Product.all()
    if filter_type == "out_of_stock":
        products = [p for p in products if p.stock_quantity == 0]
    elif filter_type == "low_stock":
        products = [p for p in products if p.is_low_stock]
    pagination = Pagination(sorted(products, key=lambda p: p.stock_quantity), page, ADMIN_PER_PAGE)
    return render_template("admin/inventory_list.html", pagination=pagination, products=pagination.items, filter_type=filter_type)


@admin_bp.route("/inventory/<int:product_id>/update", methods=["POST"])
@admin_required
def inventory_update(product_id):
    product = Product.find_or_404(product_id)
    form = StockUpdateForm()
    if form.validate_on_submit():
        AdminProductService.update_stock(product, form.stock_quantity.data, form.low_stock_threshold.data)
        flash("Stock updated.", "success")
    else:
        flash("Invalid stock values.", "danger")
    return redirect(url_for("admin.inventory"))


# ---------- Orders ----------

@admin_bp.route("/orders")
@admin_required
def orders():
    page = request.args.get("page", 1, type=int)
    status = request.args.get("status", "")
    payment_method = request.args.get("payment_method", "")
    q = request.args.get("q", "").strip()

    filters = []
    if status:
        filters.append(Order.order_status == status)
    if payment_method:
        filters.append(Order.payment_method == payment_method)
    orders = Order.all(*filters)
    if q:
        users = User.find_many({o.user_id for o in orders})

        def matches(order):
            user = users.get(order.user_id)
            return contains_text(q, order.order_number, user.email if user else "", user.name if user else "")

        orders = [o for o in orders if matches(o)]

    pagination = Pagination(newest_first(orders), page, ADMIN_PER_PAGE)
    return render_template(
        "admin/orders_list.html",
        pagination=pagination,
        orders=pagination.items,
        status=status,
        payment_method=payment_method,
        q=q,
        statuses=OrderStatus.CHOICES,
    )


@admin_bp.route("/orders/<int:order_id>")
@admin_required
def order_detail(order_id):
    order = Order.find_or_404(order_id)
    form = OrderStatusForm()
    allowed = OrderStatus.TRANSITIONS.get(order.order_status, ())
    form.new_status.choices = [(s, s.replace("_", " ").title()) for s in allowed]
    return render_template("admin/order_detail.html", order=order, form=form)


@admin_bp.route("/orders/<int:order_id>/status", methods=["POST"])
@admin_required
def order_status_update(order_id):
    from app.services.order_service import OrderService, OrderTransitionError

    order = Order.find_or_404(order_id)
    form = OrderStatusForm()
    allowed = OrderStatus.TRANSITIONS.get(order.order_status, ())
    form.new_status.choices = [(s, s.replace("_", " ").title()) for s in allowed]

    if form.validate_on_submit():
        try:
            OrderService.change_status(order, form.new_status.data, changed_by=current_user.email, note=form.note.data)
            flash("Order status updated.", "success")
        except OrderTransitionError as exc:
            flash(str(exc), "danger")
    else:
        flash("Invalid status selection.", "danger")
    return redirect(url_for("admin.order_detail", order_id=order.id))


@admin_bp.route("/orders/<int:order_id>/collect-payment", methods=["POST"])
@admin_required
def order_collect_payment(order_id):
    from app.services.order_service import OrderService, PaymentCollectionError

    order = Order.find_or_404(order_id)
    try:
        OrderService.mark_cod_payment_collected(order, changed_by=current_user.email)
        flash("Payment marked as collected.", "success")
    except PaymentCollectionError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin.order_detail", order_id=order.id))


# ---------- Payments ----------

@admin_bp.route("/payments")
@admin_required
def payments():
    page = request.args.get("page", 1, type=int)
    status = request.args.get("status", "")
    payments = Payment.all(Payment.status == status) if status else Payment.all()
    pagination = Pagination(newest_first(payments), page, ADMIN_PER_PAGE)
    return render_template("admin/payments_list.html", pagination=pagination, payments=pagination.items, status=status)


@admin_bp.route("/payments/settings", methods=["GET", "POST"])
@admin_required
def payment_settings():
    from app.services.payment_settings_service import PaymentSettingsError, PaymentSettingsService, mask

    settings = PaymentSettingsService.get()
    form = PaymentSettingsForm()
    if request.method == "GET":
        form.cod_enabled.data = settings["cod_enabled"]
        form.razorpay_enabled.data = settings["razorpay_enabled"]
        form.razorpay_key_id.data = settings["razorpay_key_id"] if settings["razorpay_key_id_source"] == "admin" else ""

    if form.validate_on_submit():
        try:
            _settings, warning = PaymentSettingsService.update(
                razorpay_enabled=form.razorpay_enabled.data,
                cod_enabled=form.cod_enabled.data,
                key_id=form.razorpay_key_id.data,
                key_secret=form.razorpay_key_secret.data,
                webhook_secret=form.razorpay_webhook_secret.data,
                clear_secrets=form.clear_saved_keys.data,
            )
        except PaymentSettingsError as exc:
            flash(str(exc), "danger")
        else:
            flash("Payment settings saved.", "success")
            if warning:
                flash(warning, "warning")
            return redirect(url_for("admin.payment_settings"))

    return render_template(
        "admin/payment_settings.html",
        form=form,
        settings=settings,
        masked={
            "key_id": settings["razorpay_key_id"],
            "key_secret": mask(settings["razorpay_key_secret"]),
            "webhook_secret": mask(settings["razorpay_webhook_secret"]),
        },
        webhook_url=url_for("payments.razorpay_webhook", _external=True),
    )


# ---------- Users ----------

@admin_bp.route("/users")
@admin_required
def users():
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    users = User.all()
    if q:
        users = [u for u in users if contains_text(q, u.name, u.email)]
    pagination = Pagination(newest_first(users), page, ADMIN_PER_PAGE)
    return render_template("admin/users_list.html", pagination=pagination, users=pagination.items, q=q)


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def user_edit(user_id):
    user = User.find_or_404(user_id)
    form = UserEditForm(obj=user)
    if form.validate_on_submit():
        if user.id == current_user.id and form.role.data != "admin":
            flash("You cannot remove your own admin role.", "danger")
        else:
            AdminUserService.update_user(user, form)
            flash("User updated.", "success")
            return redirect(url_for("admin.users"))
    return render_template("admin/user_form.html", form=form, user=user)


# ---------- Coupons ----------

@admin_bp.route("/coupons")
@admin_required
def coupons():
    page = request.args.get("page", 1, type=int)
    pagination = Pagination(newest_first(Coupon.all()), page, ADMIN_PER_PAGE)
    return render_template("admin/coupons_list.html", pagination=pagination, coupons=pagination.items)


@admin_bp.route("/coupons/new", methods=["GET", "POST"])
@admin_required
def coupon_new():
    form = CouponForm()
    if form.validate_on_submit():
        try:
            AdminCouponService.create_coupon(form)
            flash("Coupon created.", "success")
            return redirect(url_for("admin.coupons"))
        except AdminError as exc:
            flash(str(exc), "danger")
    return render_template("admin/coupon_form.html", form=form, is_new=True)


@admin_bp.route("/coupons/<int:coupon_id>/edit", methods=["GET", "POST"])
@admin_required
def coupon_edit(coupon_id):
    coupon = Coupon.find_or_404(coupon_id)
    form = CouponForm(obj=coupon)
    if form.validate_on_submit():
        try:
            AdminCouponService.update_coupon(coupon, form)
            flash("Coupon updated.", "success")
            return redirect(url_for("admin.coupons"))
        except AdminError as exc:
            flash(str(exc), "danger")
    return render_template("admin/coupon_form.html", form=form, is_new=False, coupon=coupon)


# ---------- Settings ----------

@admin_bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    from flask import current_app

    from app.services.site_content_service import (
        FONT_CHOICES,
        THEME_PRESETS,
        BrandingService,
        HeroBannerService,
        font_stack,
        font_stylesheet_urls,
    )

    form = BrandingForm()
    if request.method == "GET":
        branding = BrandingService.get()
        form.site_name.data = branding["site_name"]
        form.theme_color.data = branding["theme_color"]
        form.show_name_with_logo.data = branding["show_name_with_logo"] == "1"
        form.heading_font.data = branding["heading_font"]
        form.body_font.data = branding["body_font"]

    if form.validate_on_submit():
        try:
            BrandingService.update(
                form.site_name.data,
                form.theme_color.data,
                logo=form.logo.data or None,
                remove_logo=form.remove_logo.data,
                show_name_with_logo=form.show_name_with_logo.data,
                heading_font=form.heading_font.data,
                body_font=form.body_font.data,
            )
            flash("Branding updated.", "success")
            return redirect(url_for("admin.settings"))
        except UnsupportedFileError as exc:
            flash(str(exc), "danger")

    overview = {
        "Environment": current_app.config.get("FLASK_ENV", "development"),
        "Storage backend": "Google Cloud Storage" if current_app.config.get("GCS_ENABLED") else "Local filesystem",
        "GCS bucket": current_app.config.get("GCS_BUCKET_NAME") or "-",
        "Email delivery": "Enabled" if current_app.config.get("MAIL_ENABLED") else "Disabled (logged only)",
    }
    banner = HeroBannerService.get()
    banner_form = HeroBannerForm(prefix="banner")
    banner_form.eyebrow.data = banner["hero_eyebrow"]
    banner_form.title.data = banner["hero_title"]
    banner_form.subtitle.data = banner["hero_subtitle"]
    banner_form.button_text.data = banner["hero_button_text"]

    return render_template(
        "admin/settings.html",
        overview=overview,
        form=form,
        presets=THEME_PRESETS,
        banner_form=banner_form,
        banner=banner,
        logo_url=BrandingService.get()["logo_url"],
        font_previews={
            key: {"stack": font_stack(key), "url": font_stylesheet_urls(key, (700,))[0]} for key in FONT_CHOICES
        },
    )


@admin_bp.route("/settings/banner", methods=["POST"])
@admin_required
def settings_banner():
    from app.services.site_content_service import HeroBannerService

    form = HeroBannerForm(prefix="banner")
    if not form.validate_on_submit():
        for errors in form.errors.values():
            for error in errors:
                flash(error, "danger")
        return redirect(url_for("admin.settings"))

    try:
        HeroBannerService.update(
            eyebrow=form.eyebrow.data or "",
            title=form.title.data or "",
            subtitle=form.subtitle.data or "",
            button_text=form.button_text.data or "",
            image=form.image.data or None,
            remove_image=form.remove_image.data,
        )
        flash("Homepage banner updated.", "success")
    except UnsupportedFileError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("admin.settings"))


# ---------- Storefront (CTA colour, homepage copy/toggles, shipping & tax) ----------

@admin_bp.route("/storefront", methods=["GET", "POST"])
@admin_required
def storefront():
    from decimal import Decimal

    from app.services.site_content_service import STOREFRONT_DEFAULTS, StorefrontService

    form = StorefrontForm()
    if request.method == "GET":
        raw = StorefrontService.raw()
        for key in STOREFRONT_DEFAULTS:
            field = getattr(form, key)
            if field.type == "BooleanField":
                field.data = raw[key] == "1"
            elif field.type == "DecimalField":
                field.data = Decimal(raw[key])
            else:
                field.data = raw[key]

    if form.validate_on_submit():
        StorefrontService.update({key: getattr(form, key).data for key in STOREFRONT_DEFAULTS})
        flash("Storefront updated.", "success")
        return redirect(url_for("admin.storefront"))

    return render_template("admin/storefront.html", form=form)


# ---------- Homepage sections (Featured / Trending / On sale / New arrivals) ----------

@admin_bp.route("/homepage", methods=["GET", "POST"])
@admin_required
def homepage_sections():
    import json

    from app.services.home_sections_service import SECTION_DEFAULTS, HomeSectionsService, order_stats

    form = HomeSectionsForm()
    if form.validate_on_submit():
        try:
            sections = json.loads(form.sections_json.data)
        except ValueError:
            flash("Could not read the section settings. Please try again.", "danger")
        else:
            HomeSectionsService.save_layout(sections if isinstance(sections, list) else [])
            flash("Homepage sections updated.", "success")
            return redirect(url_for("admin.homepage_sections"))

    layout = HomeSectionsService.get_layout()
    stats = order_stats()
    products = _by_name(Product.all(Product.is_active == True))  # noqa: E712
    catalog = [
        {
            "id": p.id,
            "name": p.name,
            "sku": p.sku,
            "price": float(p.effective_price),
            "on_sale": p.is_on_sale,
            "discount": p.discount_percent,
            "in_stock": p.in_stock,
            "image": p.image_url or url_for("static", filename="images/placeholder.svg"),
            "units": stats.get(p.id, {}).get("units", 0),
            "orders": stats.get(p.id, {}).get("orders", 0),
        }
        for p in products
    ]
    auto_preview = {
        s["key"]: [p.id for p in HomeSectionsService.auto_products(s["key"], s["limit"])] for s in layout
    }
    top_sellers = sorted((c for c in catalog if c["units"]), key=lambda c: (-c["units"], c["name"]))[:10]

    return render_template(
        "admin/homepage_sections.html",
        form=form,
        layout=layout,
        catalog=catalog,
        auto_preview=auto_preview,
        rules={s["key"]: s["rule"] for s in SECTION_DEFAULTS},
        top_sellers=top_sellers,
    )


# ---------- Site content (About / Privacy Policy / Terms / contact info) ----------

@admin_bp.route("/content")
@admin_required
def content_list():
    from app.services.site_content_service import SiteContentService

    return render_template("admin/content_list.html", items=SiteContentService.list_all())


@admin_bp.route("/content/<key>/edit", methods=["GET", "POST"])
@admin_required
def content_edit(key):
    from app.services.site_content_service import SiteContentService

    item = SiteContentService.get_or_404(key)
    if item is None:
        abort(404)

    form = SiteContentForm()
    if request.method == "GET":
        form.value.data = item["value"]

    if form.validate_on_submit():
        SiteContentService.update(key, form.value.data)
        flash(f"{item['label']} updated.", "success")
        return redirect(url_for("admin.content_list"))

    return render_template("admin/content_form.html", form=form, item=item)
