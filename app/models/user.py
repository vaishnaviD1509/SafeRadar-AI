"""User and Admin models, plus the Flask-Login user loader."""
from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager
from app.models.base import TimestampMixin

ROLES = ("user", "admin")


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"
    __table_args__ = (
        db.CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
    )

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(10), nullable=False, default="user")
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    admin_profile = db.relationship(
        "Admin", back_populates="user", uselist=False,
        cascade="all, delete-orphan", passive_deletes=True,
    )
    contacts = db.relationship(
        "TrustedContact", back_populates="user",
        cascade="all, delete-orphan", passive_deletes=True,
        order_by="TrustedContact.created_at",
    )
    sos_alerts = db.relationship(
        "SOSAlert", back_populates="user",
        cascade="all, delete-orphan", passive_deletes=True,
    )
    # Reports are kept (reporter set to NULL) if the account is deleted.
    incident_reports = db.relationship(
        "IncidentReport", foreign_keys="IncidentReport.user_id",
        back_populates="reporter", passive_deletes=True,
    )

    def set_password(self, password):
        """Store only a salted hash, never the password itself."""
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"


class Admin(TimestampMixin, db.Model):
    """Extra details for users whose role is 'admin' (one-to-one with users)."""

    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False,
    )
    designation = db.Column(db.String(100), nullable=False, default="Administrator")

    user = db.relationship("User", back_populates="admin_profile")

    def __repr__(self):
        return f"<Admin user_id={self.user_id}>"


@login_manager.user_loader
def load_user(user_id):
    """Called by Flask-Login on every request to turn the session's user id
    back into a User. Deactivated accounts are treated as logged out."""
    user = db.session.get(User, int(user_id))
    if user is not None and user.is_active:
        return user
    return None