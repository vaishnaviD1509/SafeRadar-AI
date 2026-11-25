"""Admin dashboard: statistics, the report review queue and user management (Phase 11).

Privacy choices
---------------
* Admins read report text (they must, to review it) but see the reporter only as "User #id".
* Live SOS locations are never shown to admins, only counts of alerts.
* Every review records who decided and when (reviewed_by_id, reviewed_at).
* Synthetic demo reports are kept apart from real ones, so demo data never hides real work.
"""
from datetime import timedelta

from sqlalchemy import func, or_

from app.extensions import db
from app.models import CATEGORIES, STATUSES, IncidentReport, SOSAlert, User
from app.models.base import utcnow
from app.utils.timeutils import to_local

STATUS_FILTERS = ("pending", "approved", "rejected", "all")
SOURCE_FILTERS = ("real", "synthetic", "all")
DECISIONS = ("approved", "rejected", "pending")
PER_PAGE = 20


class ReviewError(ValueError):
    """A review that can not be saved, with a message that is safe to show an administrator."""


# ---------- overview ----------

def get_admin_stats():
    """Numbers for the overview page. Reports are counted as REAL reports unless stated."""
    now = utcnow()
    week_ago = now - timedelta(days=7)
    real = IncidentReport.query.filter(IncidentReport.is_synthetic.is_(False))

    by_status = {status: real.filter(IncidentReport.status == status).count() for status in STATUSES}

    rows = (
        db.session.query(IncidentReport.category, func.count(IncidentReport.id))
        .filter(IncidentReport.is_synthetic.is_(False), IncidentReport.status == "approved",
                IncidentReport.category.isnot(None))
        .group_by(IncidentReport.category)
        .all()
    )
    by_category = {name: 0 for name in CATEGORIES}
    by_category.update(dict(rows))

    regular = User.query.filter_by(role="user")
    live_alerts = SOSAlert.query.filter(
        SOSAlert.status == "active",
        or_(SOSAlert.expires_at.is_(None), SOSAlert.expires_at > now),
    ).count()

    return {
        "users": {
            "regular": regular.count(),
            "active": regular.filter(User.is_active.is_(True)).count(),
            "inactive": regular.filter(User.is_active.is_(False)).count(),
            "admins": User.query.filter_by(role="admin").count(),
        },
        "reports": {
            "pending": by_status["pending"],
            "approved": by_status["approved"],
            "rejected": by_status["rejected"],
            "synthetic": IncidentReport.query.filter(IncidentReport.is_synthetic.is_(True)).count(),
            "new_7d": real.filter(IncidentReport.created_at >= week_ago).count(),
            "reviewed_7d": real.filter(IncidentReport.reviewed_at >= week_ago).count(),
        },
        "pending_uncategorised": real.filter(
            IncidentReport.status == "pending", IncidentReport.category.is_(None)).count(),
        "by_category": by_category,
        "categorised_total": sum(by_category.values()),
        "sos": {"total": SOSAlert.query.count(), "live": live_alerts},
    }


# ---------- the review queue ----------

def normalise_filters(status, source):
    """Unknown filter values fall back to the defaults instead of breaking the page."""
    return (status if status in STATUS_FILTERS else "pending",
            source if source in SOURCE_FILTERS else "real")


def list_reports(status="pending", source="real", needs_category=False, page=1, per_page=PER_PAGE):
    """A page of reports. Pending ones come oldest first, so nothing waits forever."""
    status, source = normalise_filters(status, source)
    query = IncidentReport.query
    if status != "all":
        query = query.filter(IncidentReport.status == status)
    if source == "real":
        query = query.filter(IncidentReport.is_synthetic.is_(False))
    elif source == "synthetic":
        query = query.filter(IncidentReport.is_synthetic.is_(True))
    if needs_category:
        query = query.filter(IncidentReport.category.is_(None))

    if status == "pending":
        query = query.order_by(IncidentReport.created_at.asc(), IncidentReport.id.asc())
    else:
        query = query.order_by(IncidentReport.created_at.desc(), IncidentReport.id.desc())
    return query.paginate(page=max(int(page), 1), per_page=per_page, error_out=False)


def report_view(report):
    """What the admin pages show about a report. The reporter is only ever a number."""
    if report.is_synthetic:
        category_source = "Synthetic demo data"
    elif report.category and report.category_confidence is not None:
        category_source = "Suggested by the model"
    elif report.category:
        category_source = "Set by an administrator"
    else:
        category_source = None

    return {
        "id": report.id,
        "description": report.description,
        "category": report.category,
        "category_source": category_source,
        "severity": report.severity,
        "status": report.status,
        "synthetic": report.is_synthetic,
        "when": to_local(report.incident_time),
        "submitted": to_local(report.created_at),
        "place": report.location.name if report.location else None,
        "latitude": report.latitude,
        "longitude": report.longitude,
        "reporter_id": report.user_id,
        "reviewed_by_id": report.reviewed_by_id,
        "reviewed_at": to_local(report.reviewed_at) if report.reviewed_at else None,
    }


def review_report(report, admin, decision, category=None):
    """Save an administrator's decision. Raises ReviewError with a readable message.

    * Approving needs a category (an approved report with none would distort the maps and
      the statistics). Rejecting and returning to pending do not.
    * Changing the category clears the model's confidence: the model no longer made the choice.
    * The reviewer and the time are recorded; returning to pending clears both.
    """
    if decision not in DECISIONS:
        raise ReviewError("Choose Approve, Reject or Return to pending.")
    category = category or None
    if category is not None and category not in CATEGORIES:
        raise ReviewError("That category is not valid.")
    if decision == "approved" and category is None:
        raise ReviewError("Choose a category before approving.")

    if category != report.category:
        report.category = category
        report.category_confidence = None

    report.status = decision
    if decision == "pending":
        report.reviewed_by_id = None
        report.reviewed_at = None
    else:
        report.reviewed_by_id = admin.id
        report.reviewed_at = utcnow()
    db.session.commit()
    return report


# ---------- users ----------

def list_users(limit=200):
    """(rows, total): the newest accounts with their number of reports."""
    users = User.query.order_by(User.created_at.desc(), User.id.desc()).limit(limit).all()
    counts = dict(
        db.session.query(IncidentReport.user_id, func.count(IncidentReport.id))
        .filter(IncidentReport.user_id.isnot(None))
        .group_by(IncidentReport.user_id)
        .all()
    )
    rows = [{"user": user, "reports": counts.get(user.id, 0)} for user in users]
    return rows, User.query.count()


def set_user_active(admin, user, active):
    """Deactivate or reactivate a regular user. Raises ValueError with a readable message."""
    if user.id == admin.id:
        raise ValueError("You cannot change your own account here.")
    if user.is_admin:
        raise ValueError("Administrator accounts are managed from the command line.")
    user.is_active = bool(active)
    db.session.commit()
    return user