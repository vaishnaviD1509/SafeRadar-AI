import re

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField
from wtforms.validators import (
    DataRequired, Email, EqualTo, Length, Optional, Regexp, ValidationError,
)

from app.forms.common import PHONE_PATTERN, clean_phone, strip_text
from app.models import User


def password_has_letter_and_number(form, field):
    value = field.data or ""
    if not (re.search(r"[A-Za-z]", value) and re.search(r"\d", value)):
        raise ValidationError("Password must contain at least one letter and one number.")


class RegistrationForm(FlaskForm):
    full_name = StringField(
        "Full name", filters=[strip_text],
        validators=[DataRequired(), Length(min=2, max=100)],
    )
    email = StringField(
        "Email", filters=[strip_text],
        validators=[DataRequired(), Email(), Length(max=120)],
    )
    phone = StringField(
        "Phone (optional)", filters=[clean_phone],
        validators=[Optional(), Regexp(PHONE_PATTERN, message="Enter a valid phone number (10 to 15 digits).")],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=8, max=128), password_has_letter_and_number],
    )
    confirm_password = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )

    def validate_email(self, field):
        if User.query.filter_by(email=field.data.lower()).first():
            raise ValidationError("An account with this email already exists.")


class LoginForm(FlaskForm):
    email = StringField("Email", filters=[strip_text], validators=[DataRequired(), Length(max=120)])
    password = PasswordField("Password", validators=[DataRequired(), Length(max=128)])
    remember = BooleanField("Remember me")