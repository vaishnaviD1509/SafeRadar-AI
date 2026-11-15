from datetime import timedelta

from flask import current_app
from flask_wtf import FlaskForm
from wtforms import (
    BooleanField, DateTimeLocalField, HiddenField, IntegerField, StringField, TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError

from app.forms.common import strip_text
from app.utils.timeutils import local_now

SEVERITY_CHOICES = [
    (1, "1 - Minor concern"),
    (2, "2 - Uncomfortable"),
    (3, "3 - Serious"),
    (4, "4 - Very serious"),
    (5, "5 - Severe or immediate danger"),
]

SEVERITY_MESSAGE = "Please choose a severity from 1 to 5."
MAP_MESSAGE = "Please click the map (or use your current location) to mark where it happened."


def coordinate_validator(low, high):
    """Checks that a hidden map field holds a real number in a valid range."""

    def validate(form, field):
        try:
            value = float(field.data)
        except (TypeError, ValueError):
            raise ValidationError(MAP_MESSAGE)
        if not low <= value <= high:  # also rejects NaN and infinity
            raise ValidationError("That location is not valid. Please pick it on the map again.")

    return validate


class ReportForm(FlaskForm):
    description = TextAreaField(
        "What happened?", filters=[strip_text],
        validators=[
            DataRequired(message="Please describe what happened."),
            Length(min=20, max=2000, message="Please write between 20 and 2000 characters."),
        ],
    )
    # Rendered as a drop-down in the template (see SEVERITY_CHOICES). Checking it as a
    # number from 1 to 5 works on every WTForms version.
    severity = IntegerField(
        "How serious was it?", default=3,
        validators=[
            DataRequired(message=SEVERITY_MESSAGE),
            NumberRange(min=1, max=5, message=SEVERITY_MESSAGE),
        ],
    )
    incident_time = DateTimeLocalField(
        "When did it happen?", format="%Y-%m-%dT%H:%M",
        validators=[DataRequired(message="Please enter when it happened.")],
    )
    place_name = StringField(
        "Nearby landmark (optional)", filters=[strip_text],
        validators=[Optional(), Length(max=150)],
    )
    latitude = HiddenField(validators=[coordinate_validator(-90, 90)])
    longitude = HiddenField(validators=[coordinate_validator(-180, 180)])
    confirm = BooleanField(
        "I understand my report will be reviewed first and shown without my name.",
        validators=[DataRequired(message="Please tick this box to continue.")],
    )

    def validate_incident_time(self, field):
        if field.data is None:
            return
        now = local_now()
        if field.data > now + timedelta(minutes=5):
            raise ValidationError("The time cannot be in the future.")
        max_age = current_app.config["REPORT_MAX_AGE_DAYS"]
        if field.data < now - timedelta(days=max_age):
            raise ValidationError(f"Incidents older than {max_age} days cannot be reported.")