from app.extensions import db
from app.models.base import TimestampMixin


class TrustedContact(TimestampMixin, db.Model):
    __tablename__ = "trusted_contacts"
    __table_args__ = (
        db.UniqueConstraint("user_id", "phone", name="uq_contact_user_phone"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    relationship_label = db.Column(db.String(50))

    user = db.relationship("User", back_populates="contacts")

    def __repr__(self):
        return f"<TrustedContact {self.name} of user {self.user_id}>"