from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, TelField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, Regexp


class RegisterForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(min=2, max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    phone = TelField(
        "Phone",
        validators=[Optional(), Regexp(r"^[0-9+\-\s()]{7,20}$", message="Enter a valid phone number.")],
    )
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Remember me")


class ForgotPasswordForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])


class ResetPasswordForm(FlaskForm):
    password = PasswordField("New password", validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    new_password = PasswordField("New password", validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("new_password", message="Passwords must match.")],
    )


class ProfileForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(min=2, max=120)])
    phone = TelField(
        "Phone",
        validators=[Optional(), Regexp(r"^[0-9+\-\s()]{7,20}$", message="Enter a valid phone number.")],
    )


class AddressForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), Length(max=120)])
    phone = TelField("Phone", validators=[DataRequired(), Regexp(r"^[0-9+\-\s()]{7,20}$", message="Enter a valid phone number.")])
    address_line_1 = StringField("Address line 1", validators=[DataRequired(), Length(max=255)])
    address_line_2 = StringField("Address line 2", validators=[Optional(), Length(max=255)])
    city = StringField("City", validators=[DataRequired(), Length(max=100)])
    state = StringField("State", validators=[DataRequired(), Length(max=100)])
    postal_code = StringField("Postal code", validators=[DataRequired(), Length(max=20)])
    country = StringField("Country", validators=[DataRequired(), Length(max=100)], default="India")
    is_default = BooleanField("Set as default address")
