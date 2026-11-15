from datetime import timedelta

from app.extensions import db
from app.models import IncidentReport, Location
from app.utils.timeutils import local_now, to_local, to_utc
from tests.helpers import login, make_user

LONG_TEXT = "Someone followed me from the bus stand and kept shouting at me."


def local_text(delta=timedelta(hours=-1)):
    """A local time in the exact format the browser sends."""
    return (local_now() + delta).strftime("%Y-%m-%dT%H:%M")


def report_data(**overrides):
    data = {
        "description": LONG_TEXT,
        "severity": "3",
        "incident_time": local_text(),
        "place_name": "",
        "latitude": "17.329700",
        "longitude": "76.834300",
        "confirm": "y",
    }
    data.update(overrides)
    return data


def logged_in(client, email="user@example.com"):
    user = make_user(email)
    login(client, email=email)
    return user


# ---------- access ----------

def test_report_pages_require_login(client):
    for path in ("/report", "/my-reports"):
        response = client.get(path)
        assert response.status_code == 302, path
        assert "/login" in response.headers["Location"]


def test_report_form_page_opens(client):
    logged_in(client)
    response = client.get("/report")
    assert response.status_code == 200
    assert b'id="pick-map"' in response.data
    assert b"Where did it happen?" in response.data
    assert b"5 left today" in response.data
    assert b'<option value="3" selected>' in response.data     # default severity


def test_dashboard_links_to_report_pages(client):
    logged_in(client)
    page = client.get("/dashboard").data
    assert b'href="/report"' in page
    assert b'href="/my-reports"' in page


# ---------- successful submission ----------

def test_valid_report_is_saved_as_pending(client):
    user = logged_in(client)
    response = client.post("/report", data=report_data())
    assert response.status_code == 302
    assert "/my-reports" in response.headers["Location"]

    report = IncidentReport.query.one()
    assert report.user_id == user.id
    assert report.status == "pending"
    assert report.category is None          # the NLP model fills this in (Phase 7)
    assert report.is_synthetic is False
    assert report.severity == 3
    assert report.latitude == 17.3297
    assert report.description == LONG_TEXT


def test_local_time_is_stored_as_utc(client):
    logged_in(client)
    typed = local_now().replace(second=0, microsecond=0) - timedelta(hours=2)
    client.post("/report", data=report_data(incident_time=typed.strftime("%Y-%m-%dT%H:%M")))
    stored = IncidentReport.query.one().incident_time
    assert stored == typed - timedelta(minutes=330)


def test_pending_report_is_not_public(client):
    user = logged_in(client)
    client.post("/report", data=report_data())
    from app.services.stats import get_dashboard_stats, get_map_markers
    stats = get_dashboard_stats(user)
    assert stats["total_approved"] == 0
    assert stats["my_pending"] == 1
    assert get_map_markers() == []


def test_place_name_creates_and_reuses_location(client):
    logged_in(client)
    client.post("/report", data=report_data(place_name="Central Bus Stand"))
    client.post("/report", data=report_data(place_name="central bus stand"))
    assert Location.query.count() == 1
    reports = IncidentReport.query.all()
    assert reports[0].location_id == reports[1].location_id


# ---------- validation ----------

def assert_rejected(client, message, **overrides):
    response = client.post("/report", data=report_data(**overrides))
    assert response.status_code == 200
    assert message in response.data
    assert IncidentReport.query.count() == 0


def test_location_is_required(client):
    logged_in(client)
    assert_rejected(client, b"click the map", latitude="", longitude="")


def test_out_of_range_coordinates_rejected(client):
    logged_in(client)
    assert_rejected(client, b"not valid", latitude="91")
    assert_rejected(client, b"not valid", longitude="181")


def test_non_numeric_coordinates_rejected(client):
    logged_in(client)
    assert_rejected(client, b"click the map", latitude="abc")
    assert_rejected(client, b"not valid", latitude="nan")      # parses as a number, but is not usable
    assert_rejected(client, b"not valid", longitude="inf")


def test_short_description_rejected(client):
    logged_in(client)
    assert_rejected(client, b"between 20 and 2000", description="too short")


def test_overlong_description_rejected(client):
    logged_in(client)
    assert_rejected(client, b"between 20 and 2000", description="x" * 2001)


def test_future_time_rejected(client):
    logged_in(client)
    assert_rejected(client, b"cannot be in the future", incident_time=local_text(timedelta(days=1)))


def test_too_old_time_rejected(client):
    logged_in(client)
    assert_rejected(client, b"cannot be reported", incident_time=local_text(timedelta(days=-400)))


def test_invalid_severity_rejected(client):
    logged_in(client)
    assert_rejected(client, b"severity from 1 to 5", severity="9")
    assert_rejected(client, b"severity from 1 to 5", severity="0")
    assert_rejected(client, b"severity from 1 to 5", severity="abc")


def test_consent_is_required(client):
    logged_in(client)
    response = client.post("/report", data=report_data(confirm=""))
    assert response.status_code == 200
    assert b"tick this box" in response.data
    assert IncidentReport.query.count() == 0


def test_form_keeps_pin_after_an_error(client):
    logged_in(client)
    response = client.post("/report", data=report_data(description="short"))
    assert b'data-lat="17.329700"' in response.data


# ---------- daily limit ----------

def test_daily_limit_blocks_extra_reports(client, app):
    logged_in(client)
    limit = app.config["MAX_REPORTS_PER_DAY"]
    for _ in range(limit):
        assert client.post("/report", data=report_data()).status_code == 302
    assert IncidentReport.query.count() == limit

    response = client.post("/report", data=report_data())
    assert response.status_code == 302
    assert IncidentReport.query.count() == limit
    page = client.get("/my-reports").data
    assert b"up to 5 reports per day" in page


# ---------- my reports ----------

def test_my_reports_shows_only_own_reports(client):
    other = make_user("other@example.com")
    db.session.add(IncidentReport(
        user_id=other.id, latitude=17.3, longitude=76.8,
        description="Somebody else's private report", status="pending",
    ))
    db.session.commit()

    logged_in(client)
    client.post("/report", data=report_data())
    page = client.get("/my-reports").data
    assert LONG_TEXT.encode() in page
    assert b"Pending review" in page
    assert b"Awaiting classification" in page
    assert b"Somebody else" not in page


def test_my_reports_empty_state(client):
    logged_in(client)
    assert b"not submitted any reports yet" in client.get("/my-reports").data


def test_report_text_is_escaped(client):
    logged_in(client)
    text = "<script>alert('x')</script> followed me for ten minutes"
    client.post("/report", data=report_data(description=text))
    page = client.get("/my-reports").data
    assert b"<script>alert" not in page
    assert b"&lt;script&gt;" in page


# ---------- time helpers ----------

def test_time_conversion_round_trip(app):
    moment = local_now().replace(microsecond=0)
    assert to_local(to_utc(moment)) == moment
    assert to_local(to_utc(moment)) - to_utc(moment) == timedelta(minutes=330)


# ---------- review command ----------

def test_review_command_changes_status(app):
    user = make_user()
    report = IncidentReport(user_id=user.id, latitude=17.3, longitude=76.8,
                            description="A report that needs review", status="pending")
    db.session.add(report)
    db.session.commit()

    runner = app.test_cli_runner()
    result = runner.invoke(args=["review-report", str(report.id), "approved"])
    assert result.exit_code == 0, result.output
    assert "is now approved" in result.output
    db.session.refresh(report)
    assert report.status == "approved"
    assert report.reviewed_at is not None


def test_review_command_unknown_report(app):
    result = app.test_cli_runner().invoke(args=["review-report", "999", "approved"])
    assert result.exit_code != 0
    assert "No report with id 999" in result.output


def test_location_error_is_shown_once(client):
    logged_in(client)
    response = client.post("/report", data=report_data(latitude="", longitude=""))
    assert response.data.count(b"click the map") == 1