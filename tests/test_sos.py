from datetime import timedelta

import pytest

from app.extensions import db
from app.models import SOSAlert, TrustedContact
from app.models.base import utcnow
from app.services.sos import (
    AlertEnded, TooManyAlerts, end_alert, get_live_alert, is_live, public_view, share_message,
    start_alert, update_location, validate_position, whatsapp_number,
)
from tests.helpers import login, make_user

LAT, LON = 17.54321, 76.12345
GOOD = {"latitude": 17.33, "longitude": 76.83, "accuracy": 12.5}


@pytest.fixture
def owner(app):
    user = make_user("owner@example.com", name="Asha Patil")
    db.session.add_all([
        TrustedContact(user_id=user.id, name="Mother", phone="9876543210", relationship_label="Mother"),
        TrustedContact(user_id=user.id, name="Friend", phone="+919812345678"),
    ])
    db.session.commit()
    return user


@pytest.fixture
def other(app):
    user = make_user("other@example.com", name="Other Person")
    db.session.add(TrustedContact(user_id=user.id, name="Stranger Contact", phone="9000000000"))
    db.session.commit()
    return user


@pytest.fixture
def owner_client(client, owner):
    login(client, email=owner.email)
    return client


def normalised(page):
    """Page text with line breaks and repeated spaces removed, as a reader sees it."""
    return b" ".join(page.split())


def start_alert_for(user, lat=LAT, lon=LON, accuracy=12.0):
    alert, _ = start_alert(user, lat, lon, accuracy)
    return alert


# ---------- checking positions ----------

def test_a_good_position_is_accepted():
    assert validate_position(17.3, 76.8, 12) == (17.3, 76.8, 12.0)
    assert validate_position(17.3, 76.8) == (17.3, 76.8, None)


@pytest.mark.parametrize("latitude, longitude, accuracy", [
    (None, 76.8, None), ("17.3", 76.8, None), (True, 76.8, None), (91, 76.8, None),
    (-91, 76.8, None), (17.3, 181, None), (float("nan"), 76.8, None), (17.3, float("inf"), None),
    (17.3, 76.8, -1), (17.3, 76.8, "x"), (17.3, 76.8, 1e9),
])
def test_bad_positions_are_rejected(latitude, longitude, accuracy):
    with pytest.raises(ValueError):
        validate_position(latitude, longitude, accuracy)


# ---------- alert life cycle ----------

def test_starting_creates_a_live_alert_that_has_not_been_sent(owner):
    alert, created = start_alert(owner, LAT, LON, 12.0)
    assert created is True
    assert alert.status == "active"
    assert alert.delivery_status == "not_sent"        # the app can not send messages itself
    assert len(alert.share_token) >= 40
    assert abs((alert.expires_at - alert.created_at) - timedelta(minutes=240)) < timedelta(seconds=5)
    assert is_live(alert)


def test_each_alert_gets_its_own_token(owner):
    first = start_alert_for(owner)
    end_alert(first)
    second = start_alert_for(owner)
    assert first.share_token != second.share_token


def test_a_live_alert_is_reused_not_duplicated(owner):
    first, created_first = start_alert(owner, LAT, LON)
    second, created_second = start_alert(owner, 17.6, 76.2)
    assert (created_first, created_second) == (True, False)
    assert second.id == first.id
    assert SOSAlert.query.count() == 1
    assert second.latitude == 17.6


def test_too_many_alerts_in_an_hour_are_refused(app, owner):
    app.config["SOS_MAX_PER_HOUR"] = 2
    for _ in range(2):
        end_alert(start_alert_for(owner))
    with pytest.raises(TooManyAlerts):
        start_alert_for(owner)


def test_an_expired_alert_is_not_live_and_is_not_reused(owner):
    alert = start_alert_for(owner)
    alert.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()
    assert is_live(alert) is False
    assert get_live_alert(owner) is None
    fresh, created = start_alert(owner, LAT, LON)
    assert created is True and fresh.id != alert.id


def test_updating_moves_a_live_alert(owner):
    alert = start_alert_for(owner)
    alert.updated_at = utcnow() - timedelta(minutes=3)
    db.session.commit()
    before = alert.updated_at
    update_location(alert, 17.6, 76.2, 8.0)
    assert (alert.latitude, alert.longitude, alert.accuracy_m) == (17.6, 76.2, 8.0)
    assert alert.updated_at > before


def test_an_ended_alert_can_not_be_updated(owner):
    alert = start_alert_for(owner)
    end_alert(alert)
    with pytest.raises(AlertEnded):
        update_location(alert, 17.6, 76.2)


def test_updating_with_a_bad_position_is_refused(owner):
    alert = start_alert_for(owner)
    with pytest.raises(ValueError):
        update_location(alert, 99, 76.2)
    assert alert.latitude == LAT


def test_ending_records_the_status_and_time(owner):
    alert = start_alert_for(owner)
    end_alert(alert, "cancelled")
    assert alert.status == "cancelled" and alert.resolved_at is not None
    assert is_live(alert) is False


def test_an_ended_alert_is_left_as_it_was(owner):
    alert = start_alert_for(owner)
    end_alert(alert, "resolved")
    stamp = alert.resolved_at
    end_alert(alert, "cancelled")
    assert alert.status == "resolved" and alert.resolved_at == stamp


def test_ending_with_an_unknown_status_is_refused(owner):
    with pytest.raises(ValueError):
        end_alert(start_alert_for(owner), "deleted")


# ---------- what the public may see ----------

def test_live_view_has_first_name_and_a_rounded_location(owner):
    view = public_view(start_alert_for(owner, 17.5432149, 76.1234551, 12.0))
    assert view["live"] is True and view["state"] == "live"
    assert view["name"] == "Asha"                              # never the surname
    assert (view["latitude"], view["longitude"]) == (17.54321, 76.12346)
    assert view["stale"] is False


def test_an_old_position_is_marked_stale(owner):
    alert = start_alert_for(owner)
    alert.updated_at = utcnow() - timedelta(minutes=10)
    db.session.commit()
    view = public_view(alert)
    assert view["stale"] is True and view["seconds_ago"] >= 600


@pytest.mark.parametrize("how, state", [("resolved", "resolved"), ("cancelled", "cancelled")])
def test_ended_view_has_no_location(owner, how, state):
    alert = start_alert_for(owner)
    end_alert(alert, how)
    view = public_view(alert)
    assert view == {"name": "Asha", "live": False, "state": state}


def test_expired_view_has_no_location(owner):
    alert = start_alert_for(owner)
    alert.expires_at = utcnow() - timedelta(seconds=1)
    db.session.commit()
    assert public_view(alert) == {"name": "Asha", "live": False, "state": "expired"}


# ---------- links and messages ----------

@pytest.mark.parametrize("phone, expected", [
    ("9876543210", "919876543210"),
    ("+919876543210", "919876543210"),
    ("09876543210", "919876543210"),
    ("+14155550123", "14155550123"),
])
def test_whatsapp_numbers_get_a_country_code(phone, expected):
    assert whatsapp_number(phone) == expected


def test_the_message_has_the_link_and_the_emergency_number(owner):
    text = share_message(owner, "https://example.test/share/abc")
    assert "Asha Patil" in text and "https://example.test/share/abc" in text and "112" in text


# ---------- the SOS page ----------

def test_sos_page_needs_login(client):
    response = client.get("/sos")
    assert response.status_code == 302 and "/login" in response.headers["Location"]


def test_sos_page_is_honest_about_what_it_can_do(owner_client):
    page = owner_client.get("/sos").data
    text = normalised(page)
    assert b'href="tel:112"' in page
    assert b"cannot send SMS or WhatsApp messages by itself" in text
    assert b"does not contact the police" in text
    assert b"Mother" in page and b"Friend" in page
    assert b"outside your own network" in text          # the test server is on localhost


def test_sos_page_warns_when_there_are_no_contacts(client):
    user = make_user("nocontacts@example.com")
    login(client, email=user.email)
    assert b"no trusted contacts yet" in normalised(client.get("/sos").data)


def test_no_local_warning_when_a_public_address_is_set(app, owner_client):
    app.config["PUBLIC_BASE_URL"] = "https://sos.example.test"
    assert b"outside your own network" not in normalised(owner_client.get("/sos").data)


def test_page_restores_a_live_alert(owner_client, owner):
    token = start_alert_for(owner).share_token
    assert token.encode() in owner_client.get("/sos").data


# ---------- starting through the API ----------

def test_start_needs_login(client):
    response = client.post("/sos/start", json=GOOD)
    assert response.status_code == 401


@pytest.mark.parametrize("body", [
    {},
    {"latitude": "17", "longitude": 76},
    {"latitude": 91, "longitude": 76},
    {"latitude": 17, "longitude": 181},
    {"latitude": 17, "longitude": 76, "accuracy": -5},
])
def test_start_rejects_bad_positions(owner_client, body):
    response = owner_client.post("/sos/start", json=body)
    assert response.status_code == 400 and "error" in response.get_json()
    assert SOSAlert.query.count() == 0


def test_start_rejects_a_body_that_is_not_json(owner_client):
    assert owner_client.post("/sos/start", data="latitude=17").status_code == 400


def test_start_creates_an_alert_with_a_link_and_contact_buttons(owner_client, owner, other):
    response = owner_client.post("/sos/start", json=GOOD)
    assert response.status_code == 201
    assert response.headers["Cache-Control"] == "no-store"
    body = response.get_json()
    alert = SOSAlert.query.one()
    assert body["created"] is True
    assert body["alert"]["share_url"].endswith(f"/share/{alert.share_token}")
    assert alert.share_token in body["alert"]["message"] and "112" in body["alert"]["message"]
    assert alert.delivery_status == "not_sent"

    contacts = body["alert"]["contacts"]
    assert [c["name"] for c in contacts] == ["Mother", "Friend"]
    assert contacts[0]["sms"].startswith("sms:9876543210?body=")
    assert contacts[0]["whatsapp"].startswith("https://wa.me/919876543210?text=")
    assert "Stranger Contact" not in response.get_data(as_text=True)     # never another user's contacts


def test_the_link_uses_the_public_address_when_one_is_set(app, owner_client):
    app.config["PUBLIC_BASE_URL"] = "https://sos.example.test/"
    url = owner_client.post("/sos/start", json=GOOD).get_json()["alert"]["share_url"]
    assert url.startswith("https://sos.example.test/share/")


def test_starting_twice_reuses_the_alert(owner_client):
    first = owner_client.post("/sos/start", json=GOOD)
    second = owner_client.post("/sos/start", json={**GOOD, "latitude": 17.4})
    assert (first.status_code, second.status_code) == (201, 200)
    assert second.get_json()["created"] is False
    assert SOSAlert.query.count() == 1


def test_too_many_starts_give_a_429(app, owner_client):
    app.config["SOS_MAX_PER_HOUR"] = 1
    alert_id = owner_client.post("/sos/start", json=GOOD).get_json()["alert"]["id"]
    owner_client.post(f"/sos/{alert_id}/end", json={})
    response = owner_client.post("/sos/start", json=GOOD)
    assert response.status_code == 429
    assert "112" in response.get_json()["error"]


# ---------- updating and ending through the API ----------

def test_update_and_end_need_login(client, owner):
    alert = start_alert_for(owner)
    assert client.post(f"/sos/{alert.id}/update", json=GOOD).status_code == 401
    assert client.post(f"/sos/{alert.id}/end", json={}).status_code == 401


def test_update_moves_the_alert(owner_client, owner):
    alert = start_alert_for(owner)
    response = owner_client.post(f"/sos/{alert.id}/update", json={"latitude": 17.7, "longitude": 76.3})
    assert response.status_code == 200 and "updated" in response.get_json()
    db.session.refresh(alert)
    assert (alert.latitude, alert.longitude) == (17.7, 76.3)


def test_update_rejects_bad_input(owner_client, owner):
    alert = start_alert_for(owner)
    assert owner_client.post(f"/sos/{alert.id}/update", json={"latitude": 99, "longitude": 76}).status_code == 400
    assert owner_client.post(f"/sos/{alert.id}/update", data="x").status_code == 400


def test_update_after_the_end_gives_a_409(owner_client, owner):
    alert = start_alert_for(owner)
    end_alert(alert, "resolved")
    response = owner_client.post(f"/sos/{alert.id}/update", json=GOOD)
    assert response.status_code == 409 and response.get_json()["state"] == "resolved"


def test_nobody_can_touch_another_users_alert(owner_client, other):
    alert = start_alert_for(other)
    assert owner_client.post(f"/sos/{alert.id}/update", json=GOOD).status_code == 404
    assert owner_client.post(f"/sos/{alert.id}/end", json={}).status_code == 404
    assert owner_client.post("/sos/9999/update", json=GOOD).status_code == 404
    db.session.refresh(alert)
    assert alert.status == "active"


def test_end_stops_sharing_and_allows_a_new_alert(owner_client, owner):
    alert = start_alert_for(owner)
    response = owner_client.post(f"/sos/{alert.id}/end", json={"status": "cancelled"})
    assert response.status_code == 200 and response.get_json()["state"] == "cancelled"
    db.session.refresh(alert)
    assert alert.status == "cancelled"
    assert owner_client.post("/sos/start", json=GOOD).status_code == 201     # a fresh alert


def test_end_defaults_to_resolved_and_is_repeatable(owner_client, owner):
    alert = start_alert_for(owner)
    assert owner_client.post(f"/sos/{alert.id}/end", json={}).get_json()["state"] == "resolved"
    assert owner_client.post(f"/sos/{alert.id}/end", json={}).status_code == 200


def test_end_rejects_an_unknown_status(owner_client, owner):
    alert = start_alert_for(owner)
    assert owner_client.post(f"/sos/{alert.id}/end", json={"status": "deleted"}).status_code == 400
    db.session.refresh(alert)
    assert alert.status == "active"


# ---------- the public share page ----------

def test_share_page_works_without_logging_in_and_is_private(client, owner):
    token = start_alert_for(owner).share_token
    response = client.get(f"/share/{token}")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    page = response.data
    assert b"Asha started an SOS" in page
    assert b"17.54321" in page and b"76.12345" in page
    assert b"cannot tell you whether anyone is safe" in normalised(page)


def test_share_page_never_leaks_personal_details(client, owner):
    token = start_alert_for(owner).share_token
    page = client.get(f"/share/{token}").get_data(as_text=True)
    assert "Asha started an SOS" in page                 # the page really rendered
    for secret in ("Patil", "owner@example.com", "9876543210", "9812345678", "Mother", "Friend"):
        assert secret not in page, secret


def test_a_name_with_html_is_escaped(client, app):
    user = make_user("html@example.com", name="<script>alert(1)</script> Rao")
    token = start_alert_for(user).share_token
    page = client.get(f"/share/{token}").data
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in page      # shown as harmless text
    assert b"<script>alert(1)</script>" not in page               # never as a real script

def test_an_unknown_link_is_a_404(client):
    assert client.get("/share/not-a-real-token").status_code == 404
    assert client.get("/share/not-a-real-token/location").status_code == 404


@pytest.mark.parametrize("how", ["resolved", "cancelled"])
def test_an_ended_share_page_shows_no_location(client, owner, how):
    alert = start_alert_for(owner)
    end_alert(alert, how)
    page = client.get(f"/share/{alert.share_token}").data
    assert b"17.54321" not in page and b"76.12345" not in page
    assert b"no longer shows any location" in normalised(page)
    assert b"This SOS has ended" in page


def test_an_expired_share_page_shows_no_location(client, owner):
    alert = start_alert_for(owner)
    alert.expires_at = utcnow() - timedelta(minutes=1)
    db.session.commit()
    page = client.get(f"/share/{alert.share_token}").data
    assert b"17.54321" not in page
    assert b"has expired" in normalised(page)


def test_share_json_for_a_live_alert(client, owner):
    token = start_alert_for(owner).share_token
    response = client.get(f"/share/{token}/location")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
    body = response.get_json()
    assert set(body) == {"status", "name", "live", "state", "latitude", "longitude", "accuracy_m",
                         "updated_text", "seconds_ago", "stale"}
    assert body["live"] is True and body["name"] == "Asha"


def test_share_json_for_an_ended_alert_has_no_location(client, owner):
    alert = start_alert_for(owner)
    end_alert(alert)
    body = client.get(f"/share/{alert.share_token}/location").get_json()
    assert body == {"status": "ok", "name": "Asha", "live": False, "state": "resolved"}


def test_share_page_follows_the_alert_as_it_moves(client, owner):
    alert = start_alert_for(owner)
    update_location(alert, 17.6, 76.2, 5.0)
    body = client.get(f"/share/{alert.share_token}/location").get_json()
    assert (body["latitude"], body["longitude"]) == (17.6, 76.2)