from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import AnyOf, Optional

from app.models import CATEGORIES


class ReviewForm(FlaskForm):
    """The category an administrator confirms or changes while reviewing a report.

    The decision itself (approve, reject, return to pending) comes from the button that was
    pressed. This form checks the category and carries the CSRF token. An empty category is
    allowed (it means "not set"); anything else must be one of the four known categories.
    The drop-down is drawn by the template from `categories`.
    """

    categories = CATEGORIES          # used by the template; not a form field

    category = StringField(
        "Category",
        validators=[Optional(), AnyOf(CATEGORIES, message="That category is not valid.")],
    )