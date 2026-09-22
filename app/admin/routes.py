from functools import wraps

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.admin import admin_bp
from app.admin.forms import (
    AdminLoginForm,
    CategoryForm,
    CouponForm,
    OrderStatusForm,
    ProductForm,
    ProductImageForm,
    SiteContentForm,
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
from app.extensions import db, limiter
from app.models import Category, Coupon, Order, OrderStatus, Payment, Product, ProductImage, Subcategory, User
from app.storage import UnsupportedFileError


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
    query = Category.query
    if q:
        query = query.filter(Category.name.ilike(f"%{q}%"))
    pagination = query.order_by(Category.sort_order, Category.name).paginate(page=page, per_page=20, error_out=False)
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
    category = Category.query.get_or_404(category_id)
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
    category = Category.query.get_or_404(category_id)
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
    query = Subcategory.query
    if q:
        query = query.filter(Subcategory.name.ilike(f"%{q}%"))
    if category_id:
        query = query.filter(Subcategory.category_id == category_id)
    pagination = query.order_by(Subcategory.sort_order, Subcategory.name).paginate(page=page, per_page=20, error_out=False)
    all_categories = Category.query.order_by(Category.name).all()
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
    form.category_id.choices = [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]
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
    subcategory = Subcategory.query.get_or_404(subcategory_id)
    form = SubcategoryForm(obj=subcategory)
    form.category_id.choices = [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]
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
    subcategory = Subcategory.query.get_or_404(subcategory_id)
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
    query = Product.query
    if q:
        query = query.filter(db.or_(Product.name.ilike(f"%{q}%"), Product.sku.ilike(f"%{q}%")))
    if status == "active":
        query = query.filter(Product.is_active.is_(True))
    elif status == "inactive":
        query = query.filter(Product.is_active.is_(False))
    elif status == "out_of_stock":
        query = query.filter(Product.stock_quantity == 0)
    elif status == "low_stock":
        query = query.filter(Product.stock_quantity > 0, Product.stock_quantity <= Product.low_stock_threshold)

    pagination = query.order_by(Product.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template("admin/products_list.html", pagination=pagination, products=pagination.items, q=q, status=status)


def _populate_product_choices(form):
    form.category_id.choices = [(c.id, c.name) for c in Category.query.order_by(Category.name).all()]
    form.subcategory_id.choices = [(0, "-- none --")] + [
        (s.id, f"{s.category.name} / {s.name}") for s in Subcategory.query.order_by(Subcategory.name).all()
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
    product = Product.query.get_or_404(product_id)
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
    product = Product.query.get_or_404(product_id)
    AdminProductService.toggle_active(product)
    flash(f"Product {'activated' if product.is_active else 'deactivated'}.", "success")
    return redirect(url_for("admin.products"))


@admin_bp.route("/products/<int:product_id>/images", methods=["POST"])
@admin_required
def product_image_upload(product_id):
    product = Product.query.get_or_404(product_id)
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


@admin_bp.route("/products/<int:product_id>/images/<int:image_id>/set-main", methods=["POST"])
@admin_required
def product_image_set_main(product_id, image_id):
    product = Product.query.get_or_404(product_id)
    image = ProductImage.query.filter_by(id=image_id, product_id=product.id).first_or_404()
    AdminProductService.set_main_image(product, image)
    flash("Main image updated.", "success")
    return redirect(url_for("admin.product_edit", product_id=product.id))


@admin_bp.route("/products/<int:product_id>/images/<int:image_id>/delete", methods=["POST"])
@admin_required
def product_image_delete(product_id, image_id):
    product = Product.query.get_or_404(product_id)
    image = ProductImage.query.filter_by(id=image_id, product_id=product.id).first_or_404()
    AdminProductService.delete_image(product, image)
    flash("Image deleted.", "info")
    return redirect(url_for("admin.product_edit", product_id=product.id))


# ---------- Inventory ----------

@admin_bp.route("/inventory")
@admin_required
def inventory():
    page = request.args.get("page", 1, type=int)
    filter_type = request.args.get("filter", "")
    query = Product.query
    if filter_type == "out_of_stock":
        query = query.filter(Product.stock_quantity == 0)
    elif filter_type == "low_stock":
        query = query.filter(Product.stock_quantity > 0, Product.stock_quantity <= Product.low_stock_threshold)
    pagination = query.order_by(Product.stock_quantity).paginate(page=page, per_page=20, error_out=False)
    return render_template("admin/inventory_list.html", pagination=pagination, products=pagination.items, filter_type=filter_type)


@admin_bp.route("/inventory/<int:product_id>/update", methods=["POST"])
@admin_required
def inventory_update(product_id):
    product = Product.query.get_or_404(product_id)
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

    query = Order.query
    if status:
        query = query.filter(Order.order_status == status)
    if payment_method:
        query = query.filter(Order.payment_method == payment_method)
    if q:
        query = query.join(User).filter(
            db.or_(Order.order_number.ilike(f"%{q}%"), User.email.ilike(f"%{q}%"), User.name.ilike(f"%{q}%"))
        )

    pagination = query.order_by(Order.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
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
    order = Order.query.get_or_404(order_id)
    form = OrderStatusForm()
    allowed = OrderStatus.TRANSITIONS.get(order.order_status, ())
    form.new_status.choices = [(s, s.replace("_", " ").title()) for s in allowed]
    return render_template("admin/order_detail.html", order=order, form=form)


@admin_bp.route("/orders/<int:order_id>/status", methods=["POST"])
@admin_required
def order_status_update(order_id):
    from app.services.order_service import OrderService, OrderTransitionError

    order = Order.query.get_or_404(order_id)
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

    order = Order.query.get_or_404(order_id)
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
    query = Payment.query
    if status:
        query = query.filter(Payment.status == status)
    pagination = query.order_by(Payment.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template("admin/payments_list.html", pagination=pagination, payments=pagination.items, status=status)


# ---------- Users ----------

@admin_bp.route("/users")
@admin_required
def users():
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip()
    query = User.query
    if q:
        query = query.filter(db.or_(User.name.ilike(f"%{q}%"), User.email.ilike(f"%{q}%")))
    pagination = query.order_by(User.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template("admin/users_list.html", pagination=pagination, users=pagination.items, q=q)


@admin_bp.route("/users/<int:user_id>/edit", methods=["GET", "POST"])
@admin_required
def user_edit(user_id):
    user = User.query.get_or_404(user_id)
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
    pagination = Coupon.query.order_by(Coupon.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
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
    coupon = Coupon.query.get_or_404(coupon_id)
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

@admin_bp.route("/settings")
@admin_required
def settings():
    from flask import current_app

    overview = {
        "Environment": current_app.config.get("FLASK_ENV", "development"),
        "Storage backend": "Google Cloud Storage" if current_app.config.get("GCS_ENABLED") else "Local filesystem",
        "GCS bucket": current_app.config.get("GCS_BUCKET_NAME") or "-",
        "Email delivery": "Enabled" if current_app.config.get("MAIL_ENABLED") else "Disabled (logged only)",
        "Razorpay configured": bool(current_app.config.get("RAZORPAY_KEY_ID")),
        "Free shipping threshold": current_app.config.get("FREE_SHIPPING_THRESHOLD"),
        "Default shipping charge": current_app.config.get("DEFAULT_SHIPPING_CHARGE"),
        "Tax rate (%)": current_app.config.get("TAX_RATE_PERCENT"),
    }
    return render_template("admin/settings.html", overview=overview)


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
