import re

from flask_wtf import FlaskForm
from wtforms import BooleanField, EmailField, PasswordField, StringField, TelField
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, Regexp, ValidationError

PASSWORD_MIN_LENGTH = 8
PASSWORD_HINT = f"At least {PASSWORD_MIN_LENGTH} characters, with at least one letter and one number."


class StrongPassword:
    """Letters and digits, and not just the account's email. Length is
    checked separately by Length() so its message stays specific."""

    def __init__(self, email_field=None):
        self.email_field = email_field

    def __call__(self, form, field):
        password = field.data or ""
        if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            raise ValidationError("Password must contain at least one letter and one number.")
        email = getattr(form, "account_email", None)
        if self.email_field and getattr(form, self.email_field, None) is not None:
            email = getattr(form, self.email_field).data
        if email and password.lower() == email.strip().lower():
            raise ValidationError("Password must not be the same as your email address.")


def _password_validators(email_field=None):
    return [
        DataRequired(),
        Length(min=PASSWORD_MIN_LENGTH, max=128, message=f"Password must be at least {PASSWORD_MIN_LENGTH} characters (max 128)."),
        StrongPassword(email_field),
    ]


class RegisterForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(min=2, max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    phone = TelField(
        "Phone",
        validators=[Optional(), Regexp(r"^[0-9+\-\s()]{7,20}$", message="Enter a valid phone number.")],
    )
    password = PasswordField("Password", validators=_password_validators("email"))
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Remember me")


class ForgotPasswordForm(FlaskForm):
    email = EmailField(
        "Email",
        validators=[DataRequired(message="Please enter your email address."), Email(message="Enter a valid email address."), Length(max=255)],
    )


class ResetPasswordForm(FlaskForm):
    """Set account_email on the instance so the password can't equal it."""

    account_email = None
    password = PasswordField("New password", validators=_password_validators())
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )


class ChangePasswordForm(FlaskForm):
    current_password = PasswordField("Current password", validators=[DataRequired()])
    account_email = None
    new_password = PasswordField("New password", validators=_password_validators())
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
