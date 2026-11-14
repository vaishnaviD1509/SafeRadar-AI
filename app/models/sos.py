import secrets

from app.extensions import db
from app.models.base import TimestampMixin


def generate_share_token():
    """Long random token for the live-location link. Unguessable by design."""
    return secrets.token_urlsafe(32)


class SOSAlert(TimestampMixin, db.Model):
    __tablename__ = "sos_alerts"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('active', 'resolved', 'cancelled')", name="ck_sos_status"
        ),
        db.CheckConstraint(
            "delivery_status IN ('not_sent', 'sent', 'delivered', 'failed')",
            name="ck_sos_delivery_status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    accuracy_m = db.Column(db.Float)
    share_token = db.Column(
        db.String(64), unique=True, nullable=False, default=generate_share_token
    )
    status = db.Column(db.String(10), nullable=False, default="active")

    # 'delivered' may only be set when a real messaging service confirms it.
    delivery_status = db.Column(db.String(10), nullable=False, default="not_sent")
    resolved_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)

    user = db.relationship("User", back_populates="sos_alerts")

    def __repr__(self):
        return f"<SOSAlert {self.id} user={self.user_id} {self.status}>"