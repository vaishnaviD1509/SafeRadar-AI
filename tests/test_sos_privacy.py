from datetime import timedelta

import pytest

from app.extensions import db
from app.models import SOSAlert
from app.models.base import utcnow
from app.services.sos import end_alert, purge_old_alerts, start_alert
from tests.helpers import make_user


@pytest.fixture
def user(app):
    return make_user("sos@example.com", name="Asha Patil")


def make_alert(user, lat=17.54321, lon=76.12345):
    alert, _ = start_alert(user, lat, lon, 12.0)
    return alert


def erased(alert):
    return (alert.latitude, alert.longitude, alert.accuracy_m) == (0.0, 0.0, None)


@pytest.mark.parametrize("how", ["resolved", "cancelled"])
def test_ending_erases_the_saved_location(user, how):
    alert = make_alert(user)
    end_alert(alert, how)
    assert erased(alert)
    db.session.refresh(alert)
    assert erased(alert) and alert.status == how


def test_a_live_alert_keeps_its_location(user):
    alert = make_alert(user)
    assert not erased(alert)
    assert (alert.latitude, alert.longitude) == (17.54321, 76.12345)


def test_purge_erases_expired_alerts_but_never_live_ones(user):
    expired = make_alert(user)
    expired.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()
    live = make_alert(user, 17.6, 76.2)                     # a fresh alert, because the first expired
    assert live.id != expired.id

    assert purge_old_alerts() == (1, 0)
    db.session.refresh(expired)
    db.session.refresh(live)
    assert erased(expired)
    assert not erased(live) and (live.latitude, live.longitude) == (17.6, 76.2)


def test_purge_deletes_old_alerts_that_are_no_longer_live(user):
    old = make_alert(user)
    end_alert(old)
    old.created_at = utcnow() - timedelta(days=40)
    db.session.commit()
    recent = make_alert(user)
    end_alert(recent)
    live = make_alert(user)

    assert purge_old_alerts(30) == (0, 1)                   # both ended alerts were erased when they ended
    remaining = {alert.id for alert in SOSAlert.query.all()}
    assert remaining == {recent.id, live.id}


def test_purging_twice_changes_nothing_more(user):
    alert = make_alert(user)
    alert.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()
    assert purge_old_alerts() == (1, 0)
    assert purge_old_alerts() == (0, 0)


def test_purge_refuses_a_keep_period_under_one_day(app):
    with pytest.raises(ValueError):
        purge_old_alerts(0)


def test_purge_command_erases_expired_locations(app, user):
    alert = make_alert(user)
    alert.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()
    result = app.test_cli_runner().invoke(args=["purge-sos"])
    assert result.exit_code == 0, result.output
    assert "Erased the location of 1 alerts" in result.output
    db.session.refresh(alert)
    assert erased(alert)


def test_purge_command_deletes_old_alerts_with_a_chosen_period(app, user):
    alert = make_alert(user)
    end_alert(alert)
    alert.created_at = utcnow() - timedelta(days=10)
    db.session.commit()
    result = app.test_cli_runner().invoke(args=["purge-sos", "--keep-days", "7"])
    assert result.exit_code == 0, result.output
    assert "deleted 1 alerts older than 7 days" in result.output
    assert SOSAlert.query.count() == 0


def test_purge_command_refuses_a_bad_period(app):
    result = app.test_cli_runner().invoke(args=["purge-sos", "--keep-days", "0"])
    assert result.exit_code != 0
    assert "at least 1" in result.output