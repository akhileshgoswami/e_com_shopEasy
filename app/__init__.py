import logging
import sys

from flask import Flask, jsonify, render_template, request

from app.config import get_config
from app.extensions import csrf, limiter, login_manager, mail, ndb, oauth
from app.storage import init_storage


def create_app(config_name=None):
    app = Flask(__name__)
    config_class = get_config(config_name)
    app.config.from_object(config_class)
    config_class.init_app(app)

    _configure_logging(app)

    if app.config.get("TRUST_PROXY_HEADERS"):
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    ndb.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    mail.init_app(app)
    init_storage(app)
    _register_google_oauth(app)

    _register_login_manager(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_context_processors(app)
    _register_security_headers(app)
    _register_health_check(app)
    _register_seo_routes(app)
    _register_template_filters(app)
    _register_cli(app)

    return app


def _configure_logging(app):
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)
    app.logger.handlers = [handler]
    app.logger.setLevel(app.config.get("LOG_LEVEL", "INFO"))
    logging.getLogger("app").handlers = [handler]
    logging.getLogger("app").setLevel(app.config.get("LOG_LEVEL", "INFO"))
    logging.getLogger("app").propagate = False


def _register_google_oauth(app):
    oauth.init_app(app)
    app.config["GOOGLE_OAUTH_ENABLED"] = bool(
        app.config.get("GOOGLE_OAUTH_CLIENT_ID") and app.config.get("GOOGLE_OAUTH_CLIENT_SECRET")
    )
    if app.config["GOOGLE_OAUTH_ENABLED"]:
        oauth.register(
            name="google",
            client_id=app.config["GOOGLE_OAUTH_CLIENT_ID"],
            client_secret=app.config["GOOGLE_OAUTH_CLIENT_SECRET"],
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
    else:
        app.logger.info("Google OAuth not configured (GOOGLE_OAUTH_CLIENT_ID/SECRET unset) — button hidden.")


def _register_login_manager(app):
    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.find(user_id)

    from flask import session
    from flask_login import user_logged_in

    @user_logged_in.connect_via(app)
    def _keep_session_after_browser_closes(_sender, user, **_extra):
        # Every login path (email, Google, admin, register) goes through
        # login_user(), which fires this signal.
        session.permanent = True

    @login_manager.unauthorized_handler
    def unauthorized():
        from flask import flash, redirect, url_for

        if request.path.startswith("/admin"):
            return redirect(url_for("admin.login", next=request.path))
        flash("Please log in to continue.", "info")
        return redirect(url_for("auth.login", next=request.path))


def _register_blueprints(app):
    from app.admin import admin_bp
    from app.auth import auth_bp
    from app.cart import cart_bp
    from app.checkout import checkout_bp
    from app.payments import payments_bp
    from app.shop import shop_bp
    from app.wishlist import wishlist_bp

    app.register_blueprint(shop_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(wishlist_bp)
    app.register_blueprint(checkout_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(admin_bp)


def _register_error_handlers(app):
    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(429)
    def too_many_requests(_error):
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.exception("Unhandled server error: %s", error)
        return render_template("errors/500.html"), 500


def _register_context_processors(app):
    @app.context_processor
    def inject_globals():
        from datetime import datetime, timezone

        from flask_login import current_user

        from app.cart.services import CartService
        from app.wishlist.services import current_wishlist_ids
        from app.services.site_content_service import (
            BRANDING_DEFAULTS,
            BrandingService,
            SiteContentService,
            StorefrontService,
            build_font_theme,
            build_theme_palette,
        )
        from app.shop.services import CategoryService

        cart_item_count = 0
        wishlist_count = 0
        nav_categories = []
        footer_contact = {}
        branding = dict(BRANDING_DEFAULTS)
        store = None
        try:
            branding = BrandingService.get()
            store = StorefrontService.get()
            if current_user.is_authenticated:
                cart_item_count = CartService.get_item_count(current_user)
                wishlist_count = len(current_wishlist_ids())
            nav_categories = CategoryService.list_active_categories()
            footer_contact = SiteContentService.get_many(["contact_email", "contact_phone", "contact_address"])
        except Exception:
            app.logger.exception("Failed to load navigation context (database unavailable?)")
        if store is None:
            store = StorefrontService.get(use_db=False)

        return {
            "nav_categories": nav_categories,
            "cart_item_count": cart_item_count,
            "wishlist_count": wishlist_count,
            "site_name": branding["site_name"],
            "site_logo_url": branding["logo_url"],
            "show_site_name": not branding["logo_url"] or branding["show_name_with_logo"] == "1",
            "theme": build_theme_palette(branding["theme_color"]),
            "fonts": build_font_theme(branding["heading_font"], branding["body_font"]),
            "now_year": datetime.now(timezone.utc).year,
            "google_oauth_enabled": app.config.get("GOOGLE_OAUTH_ENABLED", False),
            "footer_contact": footer_contact,
            "store": store,
        }


def _register_security_headers(app):
    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://checkout.razorpay.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https: blob:; "
            "frame-src https://checkout.razorpay.com https://api.razorpay.com; "
            "connect-src 'self' https://api.razorpay.com; "
            "font-src 'self' https://cdn.jsdelivr.net",
        )
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


def _register_health_check(app):
    @app.route("/health")
    def health():
        from app.models import SiteContent

        try:
            SiteContent.query().fetch(1, keys_only=True)
            db_ok = True
        except Exception:
            app.logger.exception("Health check database ping failed")
            db_ok = False

        status = "ok" if db_ok else "degraded"
        code = 200 if db_ok else 503
        return jsonify({"status": status, "database": db_ok}), code


def _register_seo_routes(app):
    @app.route("/robots.txt")
    def robots_txt():
        from flask import Response

        lines = [
            "User-agent: *",
            "Allow: /",
            "Disallow: /admin/",
            "Disallow: /cart",
            "Disallow: /checkout",
            "Disallow: /profile",
            "Disallow: /orders",
            f"Sitemap: {app.config['BASE_URL'].rstrip('/')}/sitemap.xml",
        ]
        return Response("\n".join(lines), mimetype="text/plain")

    @app.route("/sitemap.xml")
    def sitemap_xml():
        from flask import Response, url_for

        from app.models import Category, Product, Subcategory

        base_url = app.config["BASE_URL"].rstrip("/")
        urls = [base_url + url_for("shop.home")]

        categories = Category.all(Category.is_active == True)  # noqa: E712
        slugs_by_id = {c.id: c.slug for c in categories}
        for category in categories:
            urls.append(base_url + url_for("shop.category_detail", category_slug=category.slug))
        for subcategory in Subcategory.all(Subcategory.is_active == True):  # noqa: E712
            if subcategory.category_id not in slugs_by_id:
                continue
            urls.append(
                base_url
                + url_for(
                    "shop.subcategory_detail",
                    category_slug=slugs_by_id[subcategory.category_id],
                    subcategory_slug=subcategory.slug,
                )
            )
        for product in Product.all(Product.is_active == True):  # noqa: E712
            urls.append(base_url + url_for("shop.product_detail", slug=product.slug))

        xml_items = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
        xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{xml_items}</urlset>'
        return Response(xml, mimetype="application/xml")


def _register_template_filters(app):
    from markupsafe import Markup, escape

    from app.wishlist.services import current_wishlist_ids

    # A global rather than a context variable so imported macros (product
    # cards) can ask without being imported "with context".
    app.jinja_env.globals["in_wishlist"] = lambda product_id: product_id in current_wishlist_ids()

    @app.template_filter("ist")
    def ist(value, fmt="%d %b %Y, %I:%M %p IST"):
        """Format a stored UTC datetime in India time; '-' when missing."""
        from app.utils import to_ist

        if value is None:
            return "-"
        return to_ist(value).strftime(fmt)

    @app.template_filter("nl2p")
    def nl2p(text):
        """Render admin-edited plain text as safe HTML paragraphs. Input is
        always escaped first, so this can never introduce XSS even though
        the output is marked safe."""
        if not text:
            return ""
        paragraphs = [p.strip() for p in text.replace("\r\n", "\n").split("\n\n") if p.strip()]
        parts = [f"<p>{str(escape(p)).replace(chr(10), '<br>')}</p>" for p in paragraphs]
        return Markup("".join(parts))


def _register_cli(app):
    import functools

    import click

    def with_ndb(command):
        """CLI commands run outside any request, so open an NDB context."""

        @functools.wraps(command)
        def wrapped(*args, **kwargs):
            with ndb.context():
                return command(*args, **kwargs)

        return wrapped

    @app.cli.command("seed-admin")
    @click.option("--email", required=True, help="Admin email address.")
    @click.option("--name", default="Administrator", help="Admin display name.")
    @click.option("--password", default=None, help="Admin password. If omitted, reads SEED_ADMIN_PASSWORD or prompts.")
    @with_ndb
    def seed_admin(email, name, password):
        """Create (or promote) an admin user. Never hardcodes a production password."""
        import os

        from app.models import Role, User

        password = password or os.environ.get("SEED_ADMIN_PASSWORD")
        if not password:
            password = click.prompt("Admin password", hide_input=True, confirmation_prompt=True)

        if len(password) < 8:
            click.echo("Error: password must be at least 8 characters.", err=True)
            sys.exit(1)

        email = email.strip().lower()
        user = User.by_email(email)
        if user:
            user.role = Role.ADMIN
            user.is_active = True
            user.set_password(password)
            user.put()
            click.echo(f"Existing user '{email}' promoted to admin and password updated.")
        else:
            user = User(name=name, email=email, role=Role.ADMIN, is_active=True)
            user.set_password(password)
            user.put()

            from app.models import Cart

            Cart(id=user.id, user_id=user.id).put()
            click.echo(f"Admin user '{email}' created.")

    @app.cli.command("seed-data")
    @with_ndb
    def seed_data():
        """Populate development seed data: categories, subcategories, products.
        Refuses to run when FLASK_ENV=production."""
        import os

        if os.environ.get("FLASK_ENV") == "production":
            click.echo("Refusing to seed demo data in production.", err=True)
            sys.exit(1)

        from app.seed import run_seed_data

        run_seed_data()
        click.echo("Seed data created.")
