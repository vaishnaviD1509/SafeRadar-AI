"""Small helpers shared by all forms."""
import re

PHONE_PATTERN = r"^\+?[0-9]{10,15}$"


def strip_text(value):
    """Remove leading and trailing spaces from text input."""
    return value.strip() if isinstance(value, str) else value


def clean_phone(value):
    """'+91 98765-43210' becomes '+919876543210'."""
    return re.sub(r"[\s\-()]", "", value) if value else value