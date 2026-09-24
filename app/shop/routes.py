from flask import render_template, request
from flask_login import current_user

from app.models import CartItem
from app.services.home_sections_service import HomeSectionsService
from app.services.site_content_service import HeroBannerService, SiteContentService
from app.shop import shop_bp
from app.shop.services import CategoryService, ProductService


@shop_bp.route("/")
def home():
    categories = CategoryService.list_active_categories()[:8]
    return render_template(
        "home.html",
        hero=HeroBannerService.get(),
        categories=categories,
        sections=HomeSectionsService.homepage_sections(),
    )


@shop_bp.route("/category/<category_slug>")
def category_detail(category_slug):
    category = CategoryService.get_by_slug_or_404(category_slug)
    subcategories = CategoryService.list_active_subcategories(category.id)

    page = request.args.get("page", 1, type=int)
    sort = request.args.get("sort", "newest")
    pagination = ProductService.search_and_filter(category_slug=category_slug, sort=sort, page=page, per_page=12)

    return render_template(
        "category.html",
        category=category,
        subcategories=subcategories,
        pagination=pagination,
        products=pagination.items,
        sort=sort,
    )


@shop_bp.route("/category/<category_slug>/<subcategory_slug>")
def subcategory_detail(category_slug, subcategory_slug):
    category = CategoryService.get_by_slug_or_404(category_slug)
    subcategory = CategoryService.get_subcategory_by_slug_or_404(category, subcategory_slug)

    page = request.args.get("page", 1, type=int)
    sort = request.args.get("sort", "newest")
    pagination = ProductService.search_and_filter(
        category_slug=category_slug, subcategory_slug=subcategory_slug, sort=sort, page=page, per_page=12
    )

    return render_template(
        "subcategory.html",
        category=category,
        subcategory=subcategory,
        pagination=pagination,
        products=pagination.items,
        sort=sort,
    )


@shop_bp.route("/products")
def product_list():
    page = request.args.get("page", 1, type=int)
    q = request.args.get("q", "").strip() or None
    category_slug = request.args.get("category") or None
    subcategory_slug = request.args.get("subcategory") or None
    min_price = request.args.get("min_price", type=float)
    max_price = request.args.get("max_price", type=float)
    in_stock_only = request.args.get("in_stock") == "1"
    on_sale_only = request.args.get("on_sale") == "1"
    sort = request.args.get("sort", "newest")

    pagination = ProductService.search_and_filter(
        q=q,
        category_slug=category_slug,
        subcategory_slug=subcategory_slug,
        min_price=min_price,
        max_price=max_price,
        in_stock_only=in_stock_only,
        on_sale_only=on_sale_only,
        sort=sort,
        page=page,
        per_page=12,
    )

    categories = CategoryService.list_active_categories()

    return render_template(
        "product_list.html",
        pagination=pagination,
        products=pagination.items,
        categories=categories,
        q=q or "",
        sort=sort,
        filters={
            "category": category_slug or "",
            "subcategory": subcategory_slug or "",
            "min_price": request.args.get("min_price", ""),
            "max_price": request.args.get("max_price", ""),
            "in_stock": in_stock_only,
            "on_sale": on_sale_only,
        },
    )


@shop_bp.route("/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return render_template("search.html", pagination=None, products=[], q="")

    page = request.args.get("page", 1, type=int)
    sort = request.args.get("sort", "newest")
    pagination = ProductService.search_and_filter(q=q, sort=sort, page=page, per_page=12)
    return render_template("search.html", pagination=pagination, products=pagination.items, q=q, sort=sort)


@shop_bp.route("/product/<slug>")
def product_detail(slug):
    product = ProductService.get_by_slug_or_404(slug)
    related = ProductService.related_products(product, limit=4)

    in_cart_quantity = 0
    if current_user.is_authenticated:
        # The cart id is the user id.
        # Several lines when the product is in the cart in more than one size.
        items = CartItem.all(CartItem.cart_id == current_user.id, CartItem.product_id == product.id)
        in_cart_quantity = sum(item.quantity for item in items)

    return render_template("product_detail.html", product=product, related=related, in_cart_quantity=in_cart_quantity)


@shop_bp.route("/contact")
def contact():
    info = SiteContentService.get_many(["contact_email", "contact_phone", "contact_address", "contact_hours"])
    return render_template("contact.html", info=info)


@shop_bp.route("/about")
def about():
    body = SiteContentService.get("about_body")
    return render_template("about.html", body=body)


@shop_bp.route("/privacy-policy")
def privacy_policy():
    body = SiteContentService.get("privacy_policy_body")
    return render_template("privacy_policy.html", body=body)


@shop_bp.route("/terms-and-conditions")
def terms():
    body = SiteContentService.get("terms_body")
    return render_template("terms.html", body=body)
