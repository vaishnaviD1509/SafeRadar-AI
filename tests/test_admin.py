from datetime import timedelta

import pytest

from app.extensions import db
from app.models import IncidentReport, SOSAlert
from app.models.base import utcnow
from app.services.admin import (
    ReviewError, get_admin_stats, list_reports, list_users, review_report,
)
from app.services.stats import get_dashboard_stats, get_map_markers
from tests.helpers import login, make_user

TEXT = "A person described what happened near the market, in their own words."


@pytest.fixture
def admin(app):
    return make_user("admin@example.com", role="admin", name="Admin One")


@pytest.fixture
def member(app):
    return make_user("member@example.com", name="Member Person")


@pytest.fixture
def admin_client(client, admin):
    login(client, email=admin.email)
    return client


@pytest.fixture
def member_client(client, member):
    login(client, email=member.email)
    return client


def add_report(**overrides):
    values = dict(latitude=17.33, longitude=76.83, description=TEXT, severity=3, status="pending")
    values.update(overrides)
    report = IncidentReport(**values)
    db.session.add(report)
    db.session.commit()
    return report


def normalised(page):
    """Page text with line breaks and repeated spaces removed, as a reader sees it."""
    return b" ".join(page.split())


def post_review(client, report, decision, category=""):
    return client.post(f"/admin/reports/{report.id}", data={"category": category, "decision": decision})


# ---------- who may open the admin pages ----------

URLS = ["/admin/", "/admin/reports", "/admin/reports/1", "/admin/users"]


@pytest.mark.parametrize("url", URLS)
def test_admin_pages_need_login(client, url):
    response = client.get(url)
    assert response.status_code == 302 and "/login" in response.headers["Location"]


@pytest.mark.parametrize("url", URLS)
def test_regular_users_are_refused(member_client, url):
    assert member_client.get(url).status_code == 403


def test_regular_users_can_not_change_anything(member_client, member):
    report = add_report(user_id=member.id)
    assert post_review(member_client, report, "approved", "Stalking").status_code == 403
    assert member_client.post(f"/admin/users/{member.id}/active", data={"active": "0"}).status_code == 403
    db.session.refresh(report)
    assert report.status == "pending"


def test_logged_out_visitors_can_not_post(client):
    assert "/login" in client.post("/admin/users/1/active", data={"active": "0"}).headers["Location"]
    assert "/login" in client.post("/admin/reports/1", data={"decision": "approved"}).headers["Location"]


def test_admins_can_open_every_page(admin_client, member):
    report = add_report(user_id=member.id)
    for url in ("/admin/", "/admin/reports", "/admin/users", f"/admin/reports/{report.id}"):
        assert admin_client.get(url).status_code == 200, url


# ---------- the overview ----------

def build_stats_data(member):
    gone = make_user("gone@example.com")
    gone.is_active = False
    now = utcnow()
    add_report(user_id=member.id)                                         # pending, no category
    add_report(user_id=member.id, category="Stalking")                    # pending, with category
    add_report(user_id=member.id, status="approved", category="Harassment", reviewed_at=now)
    add_report(user_id=member.id, status="approved", category="Harassment", reviewed_at=now)
    add_report(user_id=member.id, status="rejected", reviewed_at=now)
    for _ in range(3):                                                    # demo data
        add_report(status="approved", category="Threats", is_synthetic=True)
    db.session.add_all([
        SOSAlert(user_id=member.id, latitude=17.54321, longitude=76.12345,
                 expires_at=now + timedelta(hours=1)),                     # live
        SOSAlert(user_id=member.id, latitude=17.5, longitude=76.1, status="resolved"),
        SOSAlert(user_id=member.id, latitude=17.5, longitude=76.1,
                 expires_at=now - timedelta(minutes=5)),                   # expired
    ])
    db.session.commit()


def test_overview_numbers(admin, member):
    build_stats_data(member)
    stats = get_admin_stats()
    assert stats["users"] == {"regular": 2, "active": 1, "inactive": 1, "admins": 1}
    assert stats["reports"]["pending"] == 2
    assert stats["reports"]["approved"] == 2
    assert stats["reports"]["rejected"] == 1
    assert stats["reports"]["synthetic"] == 3
    assert stats["reports"]["new_7d"] == 5
    assert stats["reports"]["reviewed_7d"] == 3
    assert stats["pending_uncategorised"] == 1
    assert stats["by_category"]["Harassment"] == 2
    assert stats["by_category"]["Threats"] == 0                # demo data is never mixed in
    assert stats["categorised_total"] == 2
    assert stats["sos"] == {"total": 3, "live": 1}


def test_overview_page_shows_the_numbers_and_never_a_sos_location(admin_client, member):
    build_stats_data(member)
    page = admin_client.get("/admin/").data
    assert b"Awaiting review" in page
    assert b"Synthetic demo reports: 3" in normalised(page)
    assert b"17.54321" not in page and b"76.12345" not in page


def test_overview_works_with_no_data(admin_client):
    page = admin_client.get("/admin/").data
    assert b"Approved reports by category" in page


# ---------- the queue ----------

def test_queue_shows_pending_real_reports_by_default(admin_client, member):
    add_report(user_id=member.id, description="Pending real report that needs a look today.")
    add_report(user_id=member.id, status="approved", description="Approved real report already done.")
    add_report(is_synthetic=True, description="Synthetic pending report for the demo only.")
    page = admin_client.get("/admin/reports").data
    assert b"Pending real report" in page
    assert b"Approved real report" not in page
    assert b"Synthetic pending report" not in page


def test_queue_filters(admin_client, member):
    add_report(user_id=member.id, description="Uncategorised pending report text here.")
    add_report(user_id=member.id, category="Threats", description="Categorised pending report text here.")
    add_report(user_id=member.id, status="approved", description="Approved report text goes here.")
    add_report(is_synthetic=True, status="approved", description="Synthetic approved report text goes here.")

    assert b"Approved report text" in admin_client.get("/admin/reports?status=approved").data
    everything = admin_client.get("/admin/reports?status=all&source=all").data
    assert b"Synthetic approved" in everything and b"Uncategorised pending" in everything
    only_synthetic = admin_client.get("/admin/reports?status=all&source=synthetic").data
    assert b"Synthetic approved" in only_synthetic and b"Approved report text" not in only_synthetic
    needs = admin_client.get("/admin/reports?needs_category=1").data
    assert b"Uncategorised pending" in needs and b"Categorised pending" not in needs


@pytest.mark.parametrize("query", ["?status=banana", "?source=x", "?page=abc", "?page=-4", "?page=999"])
def test_bad_filters_never_break_the_page(admin_client, query):
    assert admin_client.get("/admin/reports" + query).status_code == 200


def test_the_queue_is_paged(app, member):
    for _ in range(25):
        add_report(user_id=member.id)
    first = list_reports(page=1)
    second = list_reports(page=2)
    assert (len(first.items), len(second.items), first.pages) == (20, 5, 2)
    assert list_reports(page=3).items == []


def test_the_queue_page_links_to_the_next_page(admin_client, member):
    for _ in range(21):
        add_report(user_id=member.id)
    assert b"Next" in admin_client.get("/admin/reports").data
    assert b"Previous" in admin_client.get("/admin/reports?page=2").data


def test_pending_reports_come_oldest_first(app, member):
    now = utcnow()
    newer = add_report(user_id=member.id, created_at=now - timedelta(hours=1))
    older = add_report(user_id=member.id, created_at=now - timedelta(hours=5))
    assert [r.id for r in list_reports("pending").items] == [older.id, newer.id]
    newest_first = list_reports("all")
    assert [r.id for r in newest_first.items] == [newer.id, older.id]


def test_the_queue_never_shows_the_reporter_or_a_percentage(admin_client, member):
    add_report(user_id=member.id, category="Stalking", category_confidence=0.83)
    page = admin_client.get("/admin/reports").data
    assert b"member@example.com" not in page and b"Member Person" not in page
    assert b"83%" not in page and b"% sure" not in page
    assert b"Suggested by the model" in page


# ---------- the review page ----------

def test_review_page_shows_the_report_and_only_a_reporter_number(admin_client, member):
    report = add_report(user_id=member.id)
    page = admin_client.get(f"/admin/reports/{report.id}").data
    text = normalised(page)
    assert TEXT.encode() in text
    assert f"User #{member.id}".encode() in page
    assert b"member@example.com" not in page and b"Member Person" not in page
    assert b"17.33000, 76.83000" in page
    assert b'id="review-map"' in page


def test_review_page_escapes_the_report_text(admin_client, member):
    report = add_report(user_id=member.id, description="<script>alert(1)</script> followed me home")
    page = admin_client.get(f"/admin/reports/{report.id}").data
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in page
    assert b"<script>alert(1)</script>" not in page


def test_unknown_report_is_a_404(admin_client):
    assert admin_client.get("/admin/reports/9999").status_code == 404
    response = admin_client.post("/admin/reports/9999", data={"category": "Threats", "decision": "approved"})
    assert response.status_code == 404


def test_approving_saves_the_decision_the_category_and_who_decided(admin_client, admin, member):
    report = add_report(user_id=member.id)
    response = post_review(admin_client, report, "approved", "Stalking")
    assert response.status_code == 302 and "/admin/reports" in response.headers["Location"]
    db.session.refresh(report)
    assert report.status == "approved" and report.category == "Stalking"
    assert report.reviewed_by_id == admin.id and report.reviewed_at is not None
    assert report.category_confidence is None


def test_confirming_the_models_category_keeps_its_confidence(admin_client, member):
    report = add_report(user_id=member.id, category="Stalking", category_confidence=0.8)
    post_review(admin_client, report, "approved", "Stalking")
    db.session.refresh(report)
    assert report.category == "Stalking" and report.category_confidence == 0.8


def test_changing_the_category_clears_the_models_confidence(admin_client, member):
    report = add_report(user_id=member.id, category="Stalking", category_confidence=0.8)
    post_review(admin_client, report, "approved", "Threats")
    db.session.refresh(report)
    assert report.category == "Threats" and report.category_confidence is None


def test_approving_without_a_category_is_refused(admin_client, member):
    report = add_report(user_id=member.id)
    response = post_review(admin_client, report, "approved", "")
    assert response.status_code == 302
    page = admin_client.get(f"/admin/reports/{report.id}").data
    assert b"Choose a category before approving" in page
    db.session.refresh(report)
    assert report.status == "pending" and report.reviewed_by_id is None


def test_rejecting_needs_no_category(admin_client, admin, member):
    report = add_report(user_id=member.id)
    post_review(admin_client, report, "rejected", "")
    db.session.refresh(report)
    assert report.status == "rejected" and report.reviewed_by_id == admin.id


def test_returning_to_pending_clears_the_review(admin_client, admin, member):
    report = add_report(user_id=member.id, status="approved", category="Threats",
                        reviewed_by_id=admin.id, reviewed_at=utcnow())
    response = post_review(admin_client, report, "pending", "Threats")
    assert f"/admin/reports/{report.id}" in response.headers["Location"]
    db.session.refresh(report)
    assert report.status == "pending" and report.reviewed_by_id is None and report.reviewed_at is None


def test_bad_category_or_decision_changes_nothing(admin_client, member):
    report = add_report(user_id=member.id, category="Threats")
    assert post_review(admin_client, report, "approved", "Nonsense").status_code == 302
    assert post_review(admin_client, report, "deleted", "Threats").status_code == 302
    assert post_review(admin_client, report, "", "Threats").status_code == 302
    db.session.refresh(report)
    assert report.status == "pending" and report.category == "Threats"


def test_the_review_form_offers_pending_return_only_for_decided_reports(admin_client, member):
    pending = add_report(user_id=member.id)
    decided = add_report(user_id=member.id, status="rejected")
    assert b"Return to pending" not in admin_client.get(f"/admin/reports/{pending.id}").data
    assert b"Return to pending" in admin_client.get(f"/admin/reports/{decided.id}").data


def test_an_approved_report_reaches_the_public_pages(admin_client, member):
    report = add_report(user_id=member.id)
    assert get_dashboard_stats(member)["total_approved"] == 0 and get_map_markers() == []
    post_review(admin_client, report, "approved", "Harassment")
    assert get_dashboard_stats(member)["total_approved"] == 1
    assert len(get_map_markers()) == 1


def test_review_service_rejects_bad_input(app, admin, member):
    report = add_report(user_id=member.id)
    with pytest.raises(ReviewError):
        review_report(report, admin, "maybe", "Threats")
    with pytest.raises(ReviewError):
        review_report(report, admin, "approved", "")
    with pytest.raises(ReviewError):
        review_report(report, admin, "rejected", "Not a category")
    assert report.status == "pending"


# ---------- users ----------

def fresh(client, method, url, **kwargs):
    """Run one request in its own application context, as a real request would be.

    In these tests one application context stays open for the whole test, so Flask-Login
    would otherwise remember the first logged-in user for every browser. Two people logged in
    at the same time need a fresh context per request.
    """
    with client.application.app_context():
        return getattr(client, method)(url, **kwargs)


def login_separately(client, email, password="Password123"):
    return fresh(client, "post", "/login", data={"email": email, "password": password})


def test_user_list_shows_accounts_and_report_counts(admin_client, admin, member):
    add_report(user_id=member.id)
    add_report(user_id=member.id)
    rows, total = list_users()
    by_email = {row["user"].email: row["reports"] for row in rows}
    assert total == 2 and by_email == {"admin@example.com": 0, "member@example.com": 2}
    page = admin_client.get("/admin/users").get_data(as_text=True)
    assert "member@example.com" in page
    assert member.password_hash not in page


def test_deactivating_a_user_logs_them_out_and_reactivating_restores_them(app, admin, member):
    admin_browser = app.test_client()
    member_browser = app.test_client()
    assert login_separately(admin_browser, admin.email).status_code == 302
    assert login_separately(member_browser, member.email).status_code == 302
    assert fresh(member_browser, "get", "/dashboard").status_code == 200

    fresh(admin_browser, "post", f"/admin/users/{member.id}/active", data={"active": "0"})
    db.session.refresh(member)
    assert member.is_active is False
    assert fresh(member_browser, "get", "/dashboard").status_code == 302          # logged out at once
    blocked = login_separately(app.test_client(), member.email)
    assert blocked.status_code == 200 and b"Invalid email or password" in blocked.data

    fresh(admin_browser, "post", f"/admin/users/{member.id}/active", data={"active": "1"})
    db.session.refresh(member)
    assert member.is_active is True
    assert login_separately(app.test_client(), member.email).status_code == 302
    assert fresh(member_browser, "get", "/dashboard").status_code == 200          # the old session works again


def test_an_admin_can_not_deactivate_themselves(admin_client, admin):
    response = admin_client.post(f"/admin/users/{admin.id}/active", data={"active": "0"}, follow_redirects=True)
    assert b"cannot change your own account" in normalised(response.data)
    db.session.refresh(admin)
    assert admin.is_active is True


def test_an_admin_can_not_deactivate_another_admin(admin_client):
    second = make_user("admin2@example.com", role="admin", name="Admin Two")
    response = admin_client.post(f"/admin/users/{second.id}/active", data={"active": "0"}, follow_redirects=True)
    assert b"managed from the command line" in normalised(response.data)
    db.session.refresh(second)
    assert second.is_active is True


def test_unknown_user_is_a_404(admin_client):
    assert admin_client.post("/admin/users/9999/active", data={"active": "0"}).status_code == 404