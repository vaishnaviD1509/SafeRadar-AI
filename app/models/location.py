from app.extensions import db
from app.models.base import TimestampMixin

RISK_LEVELS = ("Low", "Moderate", "High")


class Location(TimestampMixin, db.Model):
    """A named place. risk_level stays NULL until the ML model (Phase 6)
    has produced an estimate. NULL means 'unknown', not 'safe'."""

    __tablename__ = "locations"
    __table_args__ = (
        db.CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_location_latitude"),
        db.CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_location_longitude"),
        db.CheckConstraint(
            "risk_level IS NULL OR risk_level IN ('Low', 'Moderate', 'High')",
            name="ck_location_risk_level",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    latitude = db.Column(db.Float, nullable=False, index=True)
    longitude = db.Column(db.Float, nullable=False, index=True)
    area_type = db.Column(db.String(50))  # e.g. market, bus stand, residential
    risk_level = db.Column(db.String(10))

    incident_reports = db.relationship(
        "IncidentReport", back_populates="location", passive_deletes=True,
    )

    def __repr__(self):
        return f"<Location {self.name} ({self.latitude}, {self.longitude})>"