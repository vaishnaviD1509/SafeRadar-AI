"""Importing every model here makes sure db.create_all() sees all tables."""
from app.models.contact import TrustedContact
from app.models.incident import CATEGORIES, STATUSES, IncidentReport
from app.models.location import Location
from app.models.sos import SOSAlert
from app.models.user import Admin, User

__all__ = [
    "Admin",
    "CATEGORIES",
    "IncidentReport",
    "Location",
    "SOSAlert",
    "STATUSES",
    "TrustedContact",
    "User",
]