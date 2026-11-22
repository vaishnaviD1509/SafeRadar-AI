from datetime import datetime

from app.extensions import db
from app.models import IncidentReport, Location, TrustedContact
from tests.helpers import login, make_user


def add_report(**overrides):
    values = dict(
        latitude=17.33349, longitude=76.83451, description="Secret private details",
        category="Harassment", severity=3, status="approved",
        incident_time=datetime(2026, 5, 10, 18, 30),
    )
    values.update(overrides)
    report = IncidentReport(**values)
    db.session.add(report)
    db.session.commit()
    return report


def logged_in_client(client, **kwargs):
    user = make_user(**kwargs)
    login(client, email=user.email)
    return user


# ---------- landing page ----------

def test_landing_page_for_visitor(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Create a free account" in response.data
    assert b"Safety heatmap" in response.data
    assert b"unknown" in response.data


def test_landing_page_for_logged_in_user(client):
    logged_in_client(client)
    response = client.get("/")
    assert b"Open your dashboard" in response.data
    assert b"Create a free account" not in response.data


# ---------- dashboard ----------

def test_dashboard_empty_state(client):
    logged_in_client(client)
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"Welcome, Test User" in response.data
    assert b"No estimate yet" in response.data          # no invented risk value
    assert b"No approved incidents to show yet" in response.data
    assert b"no trusted contacts yet" in response.data


def test_dashboard_stats_count_correctly(client):
    user = logged_in_client(client)
    db.session.add(TrustedContact(user_id=user.id, name="Mum", phone="9876543210"))
    add_report(user_id=user.id)
    add_report(user_id=user.id, status="pending")
    add_report(status="rejected")
    db.session.commit()

    from app.services.stats import get_dashboard_stats
    stats = get_dashboard_stats(user)
    assert stats["total_approved"] == 1
    assert stats["my_reports"] == 2
    assert stats["my_pending"] == 1
    assert stats["contacts"] == 1
    assert stats["by_category"]["Harassment"] == 1


def test_dashboard_hides_pending_and_private_details(client):
    reporter = make_user("reporter@example.com", name="Private Reporter")
    shown = Location(name="Visible Market", latitude=17.33, longitude=76.83)
    hidden = Location(name="Hidden Pending Place", latitude=17.34, longitude=76.84)
    db.session.add_all([shown, hidden])
    db.session.commit()

    add_report(user_id=reporter.id, location_id=shown.id, description="Secret private details")
    add_report(location_id=hidden.id, status="pending")
    login(client, email="reporter@example.com")

    page = client.get("/dashboard").data
    assert b"Visible Market" in page                   # approved report is shown
    assert b"Hidden Pending Place" not in page         # pending report is not shown
    assert b"Secret private details" not in page       # description never exposed
    assert b"reporter@example.com" not in page         # reporter email never exposed
    assert b"Private Reporter" not in page.replace(b"Welcome, Private Reporter", b"")


def test_map_marker_coordinates_are_rounded(client):
    logged_in_client(client)
    add_report()
    page = client.get("/dashboard").data
    assert b"17.333" in page
    assert b"17.33349" not in page
    assert b"76.83451" not in page


def test_synthetic_reports_are_labelled(client):
    logged_in_client(client)
    add_report(is_synthetic=True)
    assert b"Synthetic demo data" in client.get("/dashboard").data


def test_dashboard_shows_location_name(client):
    logged_in_client(client)
    place = Location(name="Central Bus Stand", latitude=17.33, longitude=76.83)
    db.session.add(place)
    db.session.commit()
    add_report(location_id=place.id)
    assert b"Central Bus Stand" in client.get("/dashboard").data


# ---------- feature pages ----------

def test_placeholder_pages_require_login(client):
    for path in ("/heatmap", "/routes", "/sos"):
        response = client.get(path)
        assert response.status_code == 302, path
        assert "/login" in response.headers["Location"]


def test_remaining_placeholder_page_opens_when_logged_in(client):
    logged_in_client(client)
    response = client.get("/sos")
    assert response.status_code == 200
    assert b"Phase 10" in response.data


def test_heatmap_is_a_real_page(client):
    logged_in_client(client)
    response = client.get("/heatmap")
    assert response.status_code == 200
    assert b'id="heatmap"' in response.data
    assert b"Coming in Phase" not in response.data


def test_route_planner_is_a_real_page(client):
    logged_in_client(client)
    response = client.get("/routes")
    assert response.status_code == 200
    assert b'id="route-map"' in response.data
    assert b"Coming in Phase" not in response.data