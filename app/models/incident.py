from app.extensions import db
from app.models.base import TimestampMixin, utcnow

CATEGORIES = ("Harassment", "Stalking", "Threats", "Unsafe surroundings")
STATUSES = ("pending", "approved", "rejected")


class IncidentReport(TimestampMixin, db.Model):
    __tablename__ = "incident_reports"
    __table_args__ = (
        db.CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_incident_latitude"),
        db.CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_incident_longitude"),
        db.CheckConstraint("severity BETWEEN 1 AND 5", name="ck_incident_severity"),
        db.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')", name="ck_incident_status"
        ),
        db.CheckConstraint(
            "category IS NULL OR category IN "
            "('Harassment', 'Stalking', 'Threats', 'Unsafe surroundings')",
            name="ck_incident_category",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id", ondelete="SET NULL"))
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))

    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=False)

    # Assigned by the NLP model in Phase 7; NULL until then.
    category = db.Column(db.String(30), index=True)
    category_confidence = db.Column(db.Float)

    severity = db.Column(db.Integer, nullable=False, default=1)  # 1 (low) to 5 (high)
    incident_time = db.Column(db.DateTime, nullable=False, default=utcnow)
    status = db.Column(db.String(10), nullable=False, default="pending", index=True)
    reviewed_at = db.Column(db.DateTime)

    # True for generated development data. Synthetic rows must never be shown as real.
    is_synthetic = db.Column(db.Boolean, nullable=False, default=False)

    reporter = db.relationship(
        "User", foreign_keys=[user_id], back_populates="incident_reports"
    )
    reviewer = db.relationship("User", foreign_keys=[reviewed_by_id])
    location = db.relationship("Location", back_populates="incident_reports")

    def __repr__(self):
        return f"<IncidentReport {self.id} {self.category or 'uncategorised'}>"