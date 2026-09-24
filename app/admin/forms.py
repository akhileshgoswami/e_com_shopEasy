from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    BooleanField,
    DecimalField,
    HiddenField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, InputRequired, Length, NumberRange, Optional, Regexp


class AdminLoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])


class CategoryForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    description = TextAreaField("Description", validators=[Optional()])
    image = FileField("Image", validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only.")])
    is_active = BooleanField("Active", default=True)
    sort_order = IntegerField("Sort order", validators=[Optional(), NumberRange(min=0)], default=0)


class SubcategoryForm(FlaskForm):
    category_id = SelectField("Category", coerce=int, validators=[DataRequired()])
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    description = TextAreaField("Description", validators=[Optional()])
    image = FileField("Image", validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only.")])
    is_active = BooleanField("Active", default=True)
    sort_order = IntegerField("Sort order", validators=[Optional(), NumberRange(min=0)], default=0)


class ProductTypeForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=80)])
    size_label = StringField("Size label", validators=[Optional(), Length(max=40)], default="Size")
    # One size per line or comma separated; parsed by AdminProductTypeService.
    sizes = TextAreaField("Sizes", validators=[Optional(), Length(max=2000)])
    is_active = BooleanField("Active", default=True)
    sort_order = IntegerField("Sort order", validators=[Optional(), NumberRange(min=0)], default=0)


class ProductForm(FlaskForm):
    category_id = SelectField("Category", coerce=int, validators=[DataRequired()])
    subcategory_id = SelectField("Subcategory", coerce=int, validators=[Optional()])
    # 0 = no type (not sold by size). Per-size stock arrives as plain
    # size_on / size_stock__<name> inputs rendered from the chosen type.
    product_type_id = SelectField("Product type", coerce=int, validators=[Optional()])
    name = StringField("Name", validators=[DataRequired(), Length(max=200)])
    sku = StringField("SKU", validators=[DataRequired(), Length(max=64)])
    short_description = StringField("Short description", validators=[Optional(), Length(max=500)])
    description = TextAreaField("Description", validators=[Optional()])
    price = DecimalField("Price", places=2, validators=[InputRequired(), NumberRange(min=0)])
    sale_price = DecimalField("Sale price", places=2, validators=[Optional(), NumberRange(min=0)])
    # Ignored (derived from the sizes) when the product is sold by size.
    stock_quantity = IntegerField("Stock quantity", validators=[Optional(), NumberRange(min=0)], default=0)
    low_stock_threshold = IntegerField("Low stock threshold", validators=[InputRequired(), NumberRange(min=0)], default=5)
    is_active = BooleanField("Active", default=True)


class ProductImageForm(FlaskForm):
    image = FileField("Image", validators=[DataRequired(), FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only.")])


class StockUpdateForm(FlaskForm):
    # Sized products send size_stock__<name> inputs instead.
    stock_quantity = IntegerField("Stock quantity", validators=[Optional(), NumberRange(min=0)])
    low_stock_threshold = IntegerField("Low stock threshold", validators=[InputRequired(), NumberRange(min=0)])


class OrderStatusForm(FlaskForm):
    new_status = SelectField("New status", validators=[DataRequired()])
    note = StringField("Note", validators=[Optional(), Length(max=500)])


class UserEditForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    role = SelectField("Role", choices=[("customer", "Customer"), ("admin", "Admin")], validators=[DataRequired()])
    is_active = BooleanField("Active", default=True)


class CouponForm(FlaskForm):
    code = StringField("Code", validators=[DataRequired(), Length(max=50)])
    discount_type = SelectField("Discount type", choices=[("percent", "Percent"), ("flat", "Flat amount")], validators=[DataRequired()])
    discount_value = DecimalField("Discount value", places=2, validators=[InputRequired(), NumberRange(min=0)])
    minimum_order_value = DecimalField("Minimum order value", places=2, validators=[Optional(), NumberRange(min=0)], default=0)
    maximum_discount = DecimalField("Maximum discount", places=2, validators=[Optional(), NumberRange(min=0)])
    usage_limit = IntegerField("Usage limit", validators=[Optional(), NumberRange(min=1)])
    is_active = BooleanField("Active", default=True)


class SiteContentForm(FlaskForm):
    value = TextAreaField("Content", validators=[DataRequired(), Length(max=20000)])


class BrandingForm(FlaskForm):
    site_name = StringField("Website name", validators=[DataRequired(), Length(max=60)])
    theme_color = StringField(
        "Theme color",
        validators=[DataRequired(), Regexp(r"^#[0-9a-fA-F]{6}$", message="Use a hex color like #b8873f.")],
    )
    logo = FileField("Logo", validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only.")])
    remove_logo = BooleanField("Remove current logo")
    show_name_with_logo = BooleanField("Show website name next to logo", default=True)
    # Choice validation is done by BrandingService against FONT_CHOICES, so an
    # unknown or missing value just keeps the current font.
    heading_font = SelectField("Heading font", validators=[Optional()], validate_choice=False)
    body_font = SelectField("Body font", validators=[Optional()], validate_choice=False)

    def __init__(self, *args, **kwargs):
        from app.services.site_content_service import FONT_CHOICES

        super().__init__(*args, **kwargs)
        choices = [(key, label) for key, (label, *_rest) in FONT_CHOICES.items()]
        self.heading_font.choices = choices
        self.body_font.choices = choices


class HeroBannerForm(FlaskForm):
    eyebrow = StringField("Small heading", validators=[Optional(), Length(max=60)])
    title = StringField("Title", validators=[Optional(), Length(max=120)])
    subtitle = TextAreaField("Subtitle", validators=[Optional(), Length(max=300)])
    button_text = StringField("Button text", validators=[Optional(), Length(max=40)])
    image = FileField("Background image", validators=[Optional(), FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only.")])
    remove_image = BooleanField("Remove current image")


class HomeSectionsForm(FlaskForm):
    # Serialized by the admin page's JS; normalized server-side by
    # HomeSectionsService, so malformed input can't break the homepage.
    sections_json = HiddenField("Sections", validators=[DataRequired()])


class StorefrontForm(FlaskForm):
    """Customer-facing copy, toggles, CTA colour and shipping/tax rules.
    Field names match StorefrontService keys. Text may use {free_delivery}."""

    accent_color = StringField(
        "Call-to-action color",
        validators=[DataRequired(), Regexp(r"^#[0-9a-fA-F]{6}$", message="Use a hex color like #ff5a5f.")],
    )

    free_shipping_threshold = DecimalField("Free delivery above (₹)", places=2, validators=[InputRequired(), NumberRange(min=0)])
    shipping_charge = DecimalField("Shipping charge (₹)", places=2, validators=[InputRequired(), NumberRange(min=0)])
    tax_rate_percent = DecimalField("Tax rate (%)", places=2, validators=[InputRequired(), NumberRange(min=0, max=100)])

    topbar_enabled = BooleanField("Show top bar")
    topbar_perk_1 = StringField("Top bar item 1", validators=[Optional(), Length(max=60)])
    topbar_perk_2 = StringField("Top bar item 2", validators=[Optional(), Length(max=60)])
    topbar_perk_3 = StringField("Top bar item 3", validators=[Optional(), Length(max=60)])

    hero_secondary_text = StringField("Second button text", validators=[Optional(), Length(max=40)])
    hero_perk_1 = StringField("Perk 1", validators=[Optional(), Length(max=60)])
    hero_perk_2 = StringField("Perk 2", validators=[Optional(), Length(max=60)])
    hero_perk_3 = StringField("Perk 3", validators=[Optional(), Length(max=60)])
    hero_sticker = StringField("Sticker text", validators=[Optional(), Length(max=40)])
    hero_collage_enabled = BooleanField("Show category tiles next to the banner")

    finder_enabled = BooleanField("Show product finder")
    finder_title = StringField("Finder heading", validators=[Optional(), Length(max=60)])
    finder_placeholder = StringField("Search placeholder", validators=[Optional(), Length(max=80)])
    finder_button = StringField("Search button text", validators=[Optional(), Length(max=30)])
    finder_deals_label = StringField("Deals switch label", validators=[Optional(), Length(max=30)])
    coupon_enabled = BooleanField("Show offer strip")
    coupon_text = StringField("Offer strip text", validators=[Optional(), Length(max=160)])
    coupon_link_text = StringField("Offer strip link text", validators=[Optional(), Length(max=30)])


class PaymentSettingsForm(FlaskForm):
    """Secrets are write-only: blank means "keep the current value"."""

    cod_enabled = BooleanField("Cash on delivery")
    razorpay_enabled = BooleanField("Razorpay (UPI, cards, netbanking)")
    razorpay_key_id = StringField("Key ID", validators=[Optional(), Length(max=64)])
    razorpay_key_secret = PasswordField("Key Secret", validators=[Optional(), Length(max=128)])
    razorpay_webhook_secret = PasswordField("Webhook Secret", validators=[Optional(), Length(max=128)])
    clear_saved_keys = BooleanField("Remove the keys saved here and use the server's default keys")
