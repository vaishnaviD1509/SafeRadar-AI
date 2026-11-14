import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import IncidentReport, TrustedContact, User
from tests.helpers import make_user


def test_password_is_hashed_not_stored_plain(app):
    user = make_user(password="Password123")
    assert user.password_hash != "Password123"
    assert user.check_password("Password123")
    assert not user.check_password("WrongPassword1")


def test_duplicate_email_rejected(app):
    make_user("same@example.com")
    db.session.add(User(full_name="Other", email="same@example.com", password_hash="x"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_invalid_role_rejected(app):
    db.session.add(User(full_name="Bad", email="bad@example.com", password_hash="x", role="superuser"))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_deleting_user_deletes_contacts(app):
    user = make_user()
    db.session.add(TrustedContact(user_id=user.id, name="Mother", phone="9876543210"))
    db.session.commit()
    assert TrustedContact.query.count() == 1

    db.session.delete(user)
    db.session.commit()
    assert TrustedContact.query.count() == 0


def test_incident_report_defaults(app):
    report = IncidentReport(latitude=17.33, longitude=76.83, description="Test report")
    db.session.add(report)
    db.session.commit()
    assert report.status == "pending"
    assert report.is_synthetic is False
    assert report.category is None
    assert report.severity == 1