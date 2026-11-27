"""One walk through the whole application, the way real people use it.

A member registers, adds a trusted contact and reports an incident. An administrator approves
it. The report reaches the maps. The member plans a route and uses SOS; a contact opens the
link without logging in; the member stops sharing and the location is erased. Finally the
administrator deactivates the account.

Nothing here uses the internet: the routing service is replaced by a fake one.
"""
from datetime import timedelta

import requests

from app.extensions import db
from app.models import IncidentReport, SOSAlert, TrustedContact, User
from app.services.admin import get_admin_stats
from app.utils.timeutils import local_now
from tests.helpers import make_user

PASSWORD = "Password123"
DESCRIPTION = "Someone followed me from the bus stand and kept shouting at me."


def fresh(client, method, url, **kwargs):
    """Run one request in its own application context, as a real request would be.

    Several people are logged in at once in this test, so no two requests may share the
    context that Flask-Login uses to remember the current user.
    """
    with client.application.app_context():
        return getattr(client, method)(url, **kwargs)


def normalised(page):
    return b" ".join(page.split())


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


def use_a_fake_routing_service(monkeypatch):
    def route(distance, duration, points):
        return {"distance": distance, "duration": duration,
                "geometry": {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in points]}}

    payload = {"code": "Ok", "routes": [
        route(1500, 420, [(17.3297, 76.8343), (17.335, 76.836), (17.34, 76.84)]),
        route(1800, 400, [(17.3297, 76.8343), (17.333, 76.842), (17.34, 76.84)]),
    ]}
    monkeypatch.setattr(requests, "get", lambda url, params=None, timeout=None, headers=None: FakeResponse(payload))


def test_the_whole_journey(app, monkeypatch):
    use_a_fake_routing_service(monkeypatch)
    member, admin_browser, contact_browser = app.test_client(), app.test_client(), app.test_client()

    # 1. A member registers, logs in and adds a trusted contact.
    registered = fresh(member, "post", "/register", data={
        "full_name": "Priya Nair", "email": "priya@example.com", "phone": "+91 98765 43210",
        "password": PASSWORD, "confirm_password": PASSWORD,
    })
    assert registered.status_code == 302
    assert fresh(member, "post", "/login", data={"email": "priya@example.com", "password": PASSWORD}).status_code == 302
    fresh(member, "post", "/contacts/add", data={
        "contact_name": "Mother", "contact_phone": "9876543210", "contact_relation": "Mother"})
    assert TrustedContact.query.count() == 1
    member_id = User.query.filter_by(email="priya@example.com").one().id

    # 2. She reports an incident. It waits for review and is not public.
    when = (local_now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    submitted = fresh(member, "post", "/report", data={
        "description": DESCRIPTION, "severity": "3", "incident_time": when,
        "place_name": "", "latitude": "17.329700", "longitude": "76.834300", "confirm": "y"})
    assert submitted.status_code == 302
    report = IncidentReport.query.one()
    assert report.status == "pending" and report.user_id == member_id
    assert b"No approved reports yet" in normalised(fresh(member, "get", "/heatmap").data)

    # 3. An administrator reviews it in the browser.
    make_user("admin@example.com", role="admin", name="Admin One")
    assert fresh(admin_browser, "post", "/login", data={"email": "admin@example.com", "password": PASSWORD}).status_code == 302
    queue = fresh(admin_browser, "get", "/admin/reports").data
    assert b"Someone followed me" in queue and b"priya@example.com" not in queue
    detail = fresh(admin_browser, "get", f"/admin/reports/{report.id}").data
    assert f"User #{member_id}".encode() in detail and b"priya@example.com" not in detail and b"Priya" not in detail
    approved = fresh(admin_browser, "post", f"/admin/reports/{report.id}",
                     data={"category": "Stalking", "decision": "approved"})
    assert approved.status_code == 302
    db.session.refresh(report)
    assert report.status == "approved" and report.category == "Stalking" and report.reviewed_by_id is not None

    # 4. The approved report now reaches the maps, labelled as a real report.
    assert b"Showing 1 approved report" in normalised(fresh(member, "get", "/heatmap").data)
    assert fresh(member, "get", "/dashboard").status_code == 200

    # 5. She plans a route (risk numbers are absent because no risk model is loaded in the tests).
    route = fresh(member, "get", "/api/route?from_lat=17.3297&from_lon=76.8343&to_lat=17.34&to_lon=76.84")
    assert route.status_code == 200
    body = route.get_json()
    assert len(body["routes"]) == 2 and body["risk_model"] is False
    assert body["recommendation"]["lowest_risk_id"] is None

    # 6. She starts an SOS. Her contact opens the link without logging in.
    started = fresh(member, "post", "/sos/start", json={"latitude": 17.54321, "longitude": 76.12345, "accuracy": 10})
    assert started.status_code == 201
    alert = SOSAlert.query.one()
    assert alert.delivery_status == "not_sent"                   # the app never claims a message was sent
    shared = fresh(contact_browser, "get", f"/share/{alert.share_token}")
    assert shared.status_code == 200
    page = shared.get_data(as_text=True)
    assert "Priya started an SOS" in page and "17.54321" in page
    assert "Nair" not in page and "priya@example.com" not in page and "9876543210" not in page
    moved = fresh(member, "post", f"/sos/{alert.id}/update", json={"latitude": 17.55, "longitude": 76.13})
    assert moved.status_code == 200

    # 7. The administrator sees counts only, never a live location.
    overview = fresh(admin_browser, "get", "/admin/").data
    assert b"17.55" not in overview and b"76.13" not in overview
    assert get_admin_stats()["sos"] == {"total": 1, "live": 1}

    # 8. She stops sharing: the link shows nothing and the saved location is erased.
    assert fresh(member, "post", f"/sos/{alert.id}/end", json={"status": "resolved"}).status_code == 200
    ended = fresh(contact_browser, "get", f"/share/{alert.share_token}").data
    assert b"This SOS has ended" in ended and b"17.55" not in ended
    db.session.refresh(alert)
    assert (alert.latitude, alert.longitude) == (0.0, 0.0)
    assert get_admin_stats()["sos"] == {"total": 1, "live": 0}

    # 9. The administrator deactivates the account: she is logged out at once.
    assert fresh(admin_browser, "post", f"/admin/users/{member_id}/active", data={"active": "0"}).status_code == 302
    assert fresh(member, "get", "/dashboard").status_code == 302
    blocked = fresh(app.test_client(), "post", "/login", data={"email": "priya@example.com", "password": PASSWORD})
    assert b"Invalid email or password" in blocked.data