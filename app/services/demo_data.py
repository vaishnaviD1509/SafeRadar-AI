"""Loads the SYNTHETIC incidents into the database so the maps have something to show.

Every row is marked is_synthetic = True and approved, so the pages label it
"Synthetic demo data". Real reports are never touched: only rows marked synthetic are
ever replaced or removed.
"""
from app.extensions import db
from app.models import IncidentReport
from app.models.base import utcnow
from app.utils.timeutils import to_utc


def remove_demo_incidents():
    """Delete synthetic incidents only. Returns how many were removed."""
    removed = IncidentReport.query.filter_by(is_synthetic=True).delete(synchronize_session=False)
    db.session.commit()
    return int(removed)


def load_demo_incidents(df, replace=True):
    """Save the rows of a cleaned incident table as approved synthetic reports.

    Raises ValueError (and saves nothing) unless every row is marked synthetic.
    """
    if not bool(df["is_synthetic"].all()):
        raise ValueError("Only rows marked is_synthetic can be loaded as demo data.")

    removed = remove_demo_incidents() if replace else 0
    now = utcnow()
    reports = [
        IncidentReport(
            user_id=None,
            latitude=float(row.latitude),
            longitude=float(row.longitude),
            description=str(row.description),
            category=row.category,
            severity=int(row.severity),
            incident_time=to_utc(row.incident_time.to_pydatetime()),  # file times are local
            status="approved",
            reviewed_at=now,
            is_synthetic=True,
        )
        for row in df.itertuples(index=False)
    ]
    db.session.add_all(reports)
    db.session.commit()
    return {"removed": removed, "added": len(reports)}