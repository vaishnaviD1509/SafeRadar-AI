from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired, Length, Optional, Regexp

from app.forms.common import PHONE_PATTERN, clean_phone, strip_text

PHONE_MESSAGE = "Enter a valid phone number (10 to 15 digits)."


class ProfileForm(FlaskForm):
    full_name = StringField(
        "Full name", filters=[strip_text],
        validators=[DataRequired(), Length(min=2, max=100)],
    )
    phone = StringField(
        "Phone", filters=[clean_phone],
        validators=[Optional(), Regexp(PHONE_PATTERN, message=PHONE_MESSAGE)],
    )


class ContactForm(FlaskForm):
    # Field names differ from ProfileForm so both forms can sit on one page.
    contact_name = StringField(
        "Name", filters=[strip_text],
        validators=[DataRequired(message="Contact name is required."), Length(max=100)],
    )
    contact_phone = StringField(
        "Phone", filters=[clean_phone],
        validators=[
            DataRequired(message="Contact phone number is required."),
            Regexp(PHONE_PATTERN, message=PHONE_MESSAGE),
        ],
    )
    contact_relation = StringField(
        "Relationship (optional)", filters=[strip_text],
        validators=[Optional(), Length(max=50)],
    )