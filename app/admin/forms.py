from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import (
    BooleanField,
    DecimalField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, InputRequired, Length, NumberRange, Optional


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
