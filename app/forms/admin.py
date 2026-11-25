from flask_wtf import FlaskForm
from wtforms import SelectField

from app.models import CATEGORIES

CATEGORY_CHOICES = [("", "Not set")] + [(name, name) for name in CATEGORIES]


class ReviewForm(FlaskForm):
    """The category an administrator confirms or changes while reviewing a report.

    The decision itself (approve, reject, return to pending) comes from the button that was
    pressed. This form exists to check the category and to carry the CSRF token.
    """
    category = SelectField("Category", choices=CATEGORY_CHOICES)