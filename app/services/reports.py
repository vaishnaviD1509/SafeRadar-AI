"""Creating and listing incident reports."""
from datetime import timedelta

from sqlalchemy import func

from app.extensions import db
from app.models import IncidentReport, Location
from app.models.base import utcnow
from app.utils.timeutils import to_local, to_utc


def count_recent_reports(user, hours=24):
    """How many reports this user submitted in the last `hours` hours."""
    since = utcnow() - timedelta(hours=hours)
    return IncidentReport.query.filter(
        IncidentReport.user_id == user.id, IncidentReport.created_at >= since
    ).count()


def get_or_create_location(name, latitude, longitude):
    """Find a named place (ignoring upper/lower case) or create it."""
    if not name:
        return None
    place = Location.query.filter(func.lower(Location.name) == name.lower()).first()
    if place is None:
        place = Location(name=name, latitude=latitude, longitude=longitude)
        db.session.add(place)
        db.session.flush()
    return place


def create_report(user, *, description, severity, local_time, latitude, longitude, place_name=None):
    """Save a new report.

    It starts as 'pending' with no category. The NLP model (Phase 7) adds the
    category, and an administrator approves or rejects it before anyone else sees it.
    """
    place = get_or_create_location(place_name, latitude, longitude)
    report = IncidentReport(
        user_id=user.id,
        location_id=place.id if place else None,
        latitude=latitude,
        longitude=longitude,
        description=description,
        severity=severity,
        incident_time=to_utc(local_time),
        status="pending",
        is_synthetic=False,
    )
    db.session.add(report)
    db.session.commit()
    return report


def list_user_reports(user, limit=50):
    """The user's own reports, newest first, with times converted to local time."""
    reports = (
        IncidentReport.query.filter_by(user_id=user.id)
        .order_by(IncidentReport.created_at.desc(), IncidentReport.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": report.id,
            "description": report.description,
            "category": report.category,
            "severity": report.severity,
            "status": report.status,
            "when": to_local(report.incident_time),
            "submitted": to_local(report.created_at),
            "place": report.location.name if report.location else None,
        }
        for report in reports
    ]