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


class ProductForm(FlaskForm):
    category_id = SelectField("Category", coerce=int, validators=[DataRequired()])
    subcategory_id = SelectField("Subcategory", coerce=int, validators=[Optional()])
    name = StringField("Name", validators=[DataRequired(), Length(max=200)])
    sku = StringField("SKU", validators=[DataRequired(), Length(max=64)])
    short_description = StringField("Short description", validators=[Optional(), Length(max=500)])
    description = TextAreaField("Description", validators=[Optional()])
    price = DecimalField("Price", places=2, validators=[InputRequired(), NumberRange(min=0)])
    sale_price = DecimalField("Sale price", places=2, validators=[Optional(), NumberRange(min=0)])
    stock_quantity = IntegerField("Stock quantity", validators=[InputRequired(), NumberRange(min=0)])
    low_stock_threshold = IntegerField("Low stock threshold", validators=[InputRequired(), NumberRange(min=0)], default=5)
    is_active = BooleanField("Active", default=True)


class ProductImageForm(FlaskForm):
    image = FileField("Image", validators=[DataRequired(), FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only.")])


class StockUpdateForm(FlaskForm):
    stock_quantity = IntegerField("Stock quantity", validators=[InputRequired(), NumberRange(min=0)])
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
