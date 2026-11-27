"""Opens every page that can be opened without choosing an id, as a visitor, a user and an admin.

It does not check what each page says (other tests do that). It checks that nothing crashes
and that no page becomes public by accident.
"""
from tests.helpers import make_user

ALLOWED = {200, 302, 400, 401, 403, 404, 503}      # never 500 (crash) or 502
PUBLIC_PAGES = {"/", "/health", "/login", "/register"}


def fresh(client, method, url, **kwargs):
    """Run one request in its own application context, as a real request would be."""
    with client.application.app_context():
        return getattr(client, method)(url, **kwargs)


def sign_in(app, email, role="user"):
    make_user(email, role=role, name="Smoke Tester")
    browser = app.test_client()
    assert fresh(browser, "post", "/login", data={"email": email, "password": "Password123"}).status_code == 302
    return browser


def pages_without_arguments(app):
    return sorted(
        rule.rule for rule in app.url_map.iter_rules()
        if "GET" in rule.methods and not rule.arguments and rule.endpoint != "static"
    )


def visit_all(app, browser):
    return {url: fresh(browser, "get", url).status_code for url in pages_without_arguments(app)}


def test_there_are_pages_to_check(app):
    pages = pages_without_arguments(app)
    assert len(pages) >= 15
    for expected in ("/dashboard", "/heatmap", "/routes", "/sos", "/admin/", "/api/route"):
        assert expected in pages


def test_visitors_see_only_the_public_pages(app):
    results = visit_all(app, app.test_client())
    assert set(results.values()) <= ALLOWED, results
    open_pages = {url for url, status in results.items() if status == 200}
    assert open_pages == PUBLIC_PAGES, open_pages


def test_a_user_can_open_their_pages_but_not_the_admin_pages(app):
    results = visit_all(app, sign_in(app, "user@example.com"))
    assert set(results.values()) <= ALLOWED, results
    for url in ("/dashboard", "/profile", "/report", "/my-reports", "/heatmap", "/routes", "/sos"):
        assert results[url] == 200, url
    for url in ("/admin/", "/admin/reports", "/admin/users"):
        assert results[url] == 403, url


def test_an_admin_can_open_everything(app):
    results = visit_all(app, sign_in(app, "admin@example.com", role="admin"))
    assert set(results.values()) <= ALLOWED, results
    for url in ("/admin/", "/admin/reports", "/admin/users", "/dashboard", "/sos"):
        assert results[url] == 200, url