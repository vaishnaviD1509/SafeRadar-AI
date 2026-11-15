import pytest

from app.ml.risk_dataset import RISK_LEVELS
from app.ml.risk_model import save_artifact
from tests.helpers import login, make_user
from tests.risk_helpers import trained


@pytest.fixture
def cell():
    """Centre of a place the test model has enough reports for."""
    return next(iter(trained()["artifact"]["profile"].values()))


@pytest.fixture
def with_model(app, tmp_path):
    """Save the test model where the app looks for it."""
    path = tmp_path / "risk_model.joblib"
    save_artifact(trained()["artifact"], path)
    app.config["RISK_MODEL_PATH"] = str(path)
    return path


@pytest.fixture
def user_client(client):
    user = make_user()
    login(client, email=user.email)
    return client


def risk_url(lat, lon, when=None):
    url = f"/api/risk?lat={lat}&lon={lon}"
    return url + (f"&when={when}" if when else "")


# ---------- API: access and validation ----------

def test_api_needs_login(client):
    response = client.get(risk_url(17.33, 76.83))
    assert response.status_code == 401
    assert response.get_json()["error"] == "Please log in."


@pytest.mark.parametrize("query", [
    "", "?lat=17.3", "?lat=abc&lon=76.8", "?lat=nan&lon=76.8", "?lat=inf&lon=76.8",
    "?lat=95&lon=76.8", "?lat=17.3&lon=181",
])
def test_api_rejects_bad_coordinates(user_client, with_model, query):
    response = user_client.get("/api/risk" + query)
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_api_rejects_bad_time(user_client, with_model, cell):
    response = user_client.get(risk_url(cell["cell_lat"], cell["cell_lon"], "tomorrow evening"))
    assert response.status_code == 400
    assert "when" in response.get_json()["error"]


# ---------- API: results ----------

def test_api_without_a_model_says_unavailable(user_client):
    response = user_client.get(risk_url(17.33, 76.83))
    assert response.status_code == 503
    body = response.get_json()
    assert body["status"] == "unavailable"
    assert "level" not in body                          # no invented estimate


def test_api_returns_an_estimate(user_client, with_model, cell):
    response = user_client.get(risk_url(cell["cell_lat"], cell["cell_lon"], "2026-11-20T22:30"))
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "estimate"
    assert body["level"] in RISK_LEVELS
    assert body["slot"] == "Night"
    assert body["synthetic"] is True
    assert "not a guarantee" in body["disclaimer"]
    assert response.headers["Cache-Control"] == "no-store"


def test_api_time_changes_the_slot(user_client, with_model, cell):
    morning = user_client.get(risk_url(cell["cell_lat"], cell["cell_lon"], "2026-11-20T09:00"))
    assert morning.get_json()["slot"] == "Morning"


def test_api_reports_unknown_not_safe(user_client, with_model):
    for lat, lon in ((17.55, 77.05), (20.0, 80.0)):
        body = user_client.get(risk_url(lat, lon)).get_json()
        assert body["status"] == "unknown"
        assert body["level"] is None


def test_api_exposes_no_personal_data(user_client, with_model, cell):
    body = user_client.get(risk_url(cell["cell_lat"], cell["cell_lon"])).get_json()
    assert set(body) <= {"status", "level", "probabilities", "slot", "slot_hours",
                         "synthetic", "disclaimer", "message"}


def test_api_stops_when_the_model_file_is_removed(user_client, with_model, cell):
    assert user_client.get(risk_url(cell["cell_lat"], cell["cell_lon"])).status_code == 200
    with_model.unlink()
    assert user_client.get(risk_url(cell["cell_lat"], cell["cell_lon"])).status_code == 503


def test_a_damaged_model_file_is_handled(user_client, app, tmp_path, cell):
    broken = tmp_path / "broken.joblib"
    broken.write_bytes(b"this is not a model")
    app.config["RISK_MODEL_PATH"] = str(broken)
    assert user_client.get(risk_url(cell["cell_lat"], cell["cell_lon"])).status_code == 503
    assert b"No estimate yet" in user_client.get("/dashboard").data


# ---------- dashboard card ----------

def test_dashboard_without_a_model(user_client):
    page = user_client.get("/dashboard").data
    assert b"No estimate yet" in page
    assert b"Unknown does not mean safe" in page


def test_dashboard_shows_a_labelled_estimate(user_client, app, with_model, cell):
    app.config["DEFAULT_MAP_CENTER"] = (cell["cell_lat"], cell["cell_lon"])
    page = user_client.get("/dashboard").data
    assert b" risk</span>" in page
    assert b"Model trained on synthetic demo data" in page
    assert b"Low does not mean safe" in page
    assert b"No estimate yet" not in page


def test_dashboard_says_unknown_when_the_area_has_no_data(user_client, app, with_model):
    app.config["DEFAULT_MAP_CENTER"] = (17.55, 77.05)
    page = user_client.get("/dashboard").data
    assert b"No estimate here" in page
    assert b"Unknown does not mean safe" in page
    assert b" risk</span>" not in page