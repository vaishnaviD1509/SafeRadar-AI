"""Read-only queries that feed the user dashboard.

Privacy rules applied here:
  * Only APPROVED reports are ever shown to other users.
  * The reporter's identity and the free-text description are never returned.
  * Map coordinates are rounded to 3 decimals (about 110 m), so a marker shows
    the general area and not an exact doorstep.
"""
from sqlalchemy import func

from app.extensions import db
from app.models import CATEGORIES, IncidentReport, TrustedContact
from app.utils.timeutils import to_local


def _approved():
    return IncidentReport.query.filter_by(status="approved")


def get_dashboard_stats(user):
    """Numbers for the statistic cards and the category breakdown."""
    total_approved = _approved().count()

    rows = (
        db.session.query(IncidentReport.category, func.count(IncidentReport.id))
        .filter(IncidentReport.status == "approved", IncidentReport.category.isnot(None))
        .group_by(IncidentReport.category)
        .all()
    )
    by_category = {name: 0 for name in CATEGORIES}
    by_category.update({name: count for name, count in rows})

    return {
        "total_approved": total_approved,
        "my_reports": IncidentReport.query.filter_by(user_id=user.id).count(),
        "my_pending": IncidentReport.query.filter_by(user_id=user.id, status="pending").count(),
        "contacts": TrustedContact.query.filter_by(user_id=user.id).count(),
        "by_category": by_category,
        "categorised_total": sum(by_category.values()),
    }


def get_recent_incidents(limit=5):
    """Newest approved reports, without description or reporter details."""
    reports = _approved().order_by(IncidentReport.incident_time.desc()).limit(limit).all()
    return [
        {
            "category": report.category or "Uncategorised",
            "severity": report.severity,
            "when": to_local(report.incident_time),
            "place": report.location.name if report.location else None,
            "is_synthetic": report.is_synthetic,
        }
        for report in reports
    ]


def get_map_markers(limit=200):
    """Approved reports as rounded map points for the dashboard map preview."""
    reports = _approved().order_by(IncidentReport.incident_time.desc()).limit(limit).all()
    return [
        {
            "lat": round(report.latitude, 3),
            "lng": round(report.longitude, 3),
            "category": report.category or "Uncategorised",
            "severity": report.severity,
            "date": to_local(report.incident_time).strftime("%d %b %Y"),
            "synthetic": report.is_synthetic,
        }
        for report in reports
    ]


def get_current_risk():
    """Current risk estimate for the user's area.

    Returns None until the ML model exists (Phase 6). 'None' means UNKNOWN,
    never 'safe': the dashboard says so instead of inventing a number.
    """
    return None