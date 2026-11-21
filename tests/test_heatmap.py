from datetime import timedelta

import pandas as pd
import pytest

from app.extensions import db
from app.ml.risk_dataset import RISK_LEVELS
from app.ml.risk_model import predict_risk, save_artifact
from app.models import IncidentReport
from app.services.demo_data import load_demo_incidents, remove_demo_incidents
from app.services.heatmap import build_risk_grid
from tests.helpers import login, make_user
from tests.risk_helpers import clean_data, trained

MONDAY_EVENING = pd.Timestamp("2026-11-16 19:00").to_pydatetime()
SATURDAY_EVENING = pd.Timestamp("2026-11-21 19:00").to_pydatetime()


@pytest.fixture
def with_model(app, tmp_path):
    """Save the test model where the app looks for it."""
    path = tmp_path / "risk_model.joblib"
    save_artifact(trained()["artifact"], path)
    app.config["RISK_MODEL_PATH"] = str(path)
    return path


@pytest.fixture
def user(app):
    return make_user()


@pytest.fixture
def user_client(client, user):
    login(client, email=user.email)
    return client


# ---------- the page ----------

def test_heatmap_needs_login(client):
    response = client.get("/heatmap")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_page_without_a_model_still_loads(user_client):
    response = user_client.get("/heatmap")
    assert response.status_code == 200
    assert b"has not been trained yet" in response.data
    assert b"Unknown does not mean safe" in response.data


def test_page_with_a_model_has_map_and_warnings(user_client, with_model):
    page = user_client.get("/heatmap").data
    assert b'id="heatmap"' in page
    assert b"has not been trained yet" not in page
    assert b"Low does not mean safe" in page
    assert b"unknown does not mean safe" in page


# ---------- the grid API ----------

def test_grid_api_needs_login(client):
    response = client.get("/api/risk-grid")
    assert response.status_code == 401
    assert response.get_json()["error"] == "Please log in."


def test_grid_api_without_a_model_says_unavailable(user_client):
    response = user_client.get("/api/risk-grid")
    assert response.status_code == 503
    body = response.get_json()
    assert body["status"] == "unavailable"
    assert "cells" not in body                          # nothing invented


def test_grid_api_returns_cells(user_client, with_model):
    response = user_client.get("/api/risk-grid?slot=2&weekend=0")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    body = response.get_json()
    profile = trained()["artifact"]["profile"]
    assert body["status"] == "ok"
    assert body["synthetic"] is True
    assert "not a guarantee" in body["disclaimer"]
    assert len(body["cells"]) == len(profile)
    assert sum(body["counts"].values()) == len(body["cells"])
    for cell in body["cells"]:
        assert cell["level"] in RISK_LEVELS
        assert cell["north"] > cell["south"] and cell["east"] > cell["west"]
        assert cell["north"] - cell["south"] == pytest.approx(0.005, abs=1e-4)
        assert sum(cell["probabilities"].values()) == pytest.approx(1.0, abs=0.01)


@pytest.mark.parametrize("query", [
    "?slot=4", "?slot=-1", "?slot=abc", "?slot=1.5", "?weekend=2", "?weekend=yes",
])
def test_grid_api_rejects_bad_parameters(user_client, with_model, query):
    response = user_client.get("/api/risk-grid" + query)
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_grid_slot_and_day_are_respected(user_client, with_model):
    body = user_client.get("/api/risk-grid?slot=3&weekend=1").get_json()
    assert body["slot"] == "Night"
    assert body["slot_index"] == 3
    assert body["is_weekend"] is True
    body = user_client.get("/api/risk-grid?slot=0&weekend=0").get_json()
    assert body["slot"] == "Morning"
    assert body["is_weekend"] is False


def test_grid_matches_the_single_place_estimates(with_model):
    """The map and /api/risk must never disagree about the same place and time."""
    artifact = trained()["artifact"]
    for when, weekend in ((MONDAY_EVENING, 0), (SATURDAY_EVENING, 1)):
        grid = build_risk_grid(slot=2, is_weekend=weekend)
        by_id = {cell["id"]: cell for cell in grid["cells"]}
        for cid, entry in list(artifact["profile"].items())[:12]:
            single = predict_risk(artifact, entry["cell_lat"], entry["cell_lon"], when)
            assert by_id[cid]["level"] == single["level"], cid


def test_grid_never_colours_unknown_places(with_model):
    profile = trained()["artifact"]["profile"]
    grid = build_risk_grid(slot=0, is_weekend=0)
    assert {cell["id"] for cell in grid["cells"]} == set(profile)   # only modelled cells
    assert all(cell["level"] in RISK_LEVELS for cell in grid["cells"])  # never None or "safe"


def test_grid_exposes_only_area_data(user_client, with_model):
    body = user_client.get("/api/risk-grid?slot=1&weekend=0").get_json()
    assert set(body) <= {"status", "slot", "slot_index", "slot_hours", "is_weekend",
                         "synthetic", "disclaimer", "counts", "cells"}
    for cell in body["cells"]:
        assert set(cell) == {"id", "south", "west", "north", "east", "level", "probabilities"}


def test_grid_function_rejects_bad_values(with_model):
    with pytest.raises(ValueError):
        build_risk_grid(slot=7)
    with pytest.raises(ValueError):
        build_risk_grid(slot=1, is_weekend=2)


# ---------- demo data in the database ----------

def test_demo_data_loads_as_approved_synthetic(app):
    result = load_demo_incidents(clean_data().head(40))
    assert result == {"removed": 0, "added": 40}
    rows = IncidentReport.query.all()
    assert len(rows) == 40
    assert all(r.is_synthetic and r.status == "approved" and r.user_id is None for r in rows)


def test_demo_data_reload_does_not_duplicate(app):
    load_demo_incidents(clean_data().head(40))
    result = load_demo_incidents(clean_data().head(40))
    assert result == {"removed": 40, "added": 40}
    assert IncidentReport.query.count() == 40


def test_demo_data_removal_keeps_real_reports(app, user):
    real = IncidentReport(user_id=user.id, latitude=17.33, longitude=76.83,
                          description="A real report written by a person.",
                          severity=2, status="approved", is_synthetic=False)
    db.session.add(real)
    db.session.commit()
    load_demo_incidents(clean_data().head(20))
    assert IncidentReport.query.count() == 21
    assert remove_demo_incidents() == 20
    assert IncidentReport.query.count() == 1
    assert IncidentReport.query.first().is_synthetic is False


def test_demo_data_rejects_rows_not_marked_synthetic(app):
    df = clean_data().head(3).copy()
    df["is_synthetic"] = False
    with pytest.raises(ValueError):
        load_demo_incidents(df)
    assert IncidentReport.query.count() == 0


def test_demo_times_are_stored_in_utc(app):
    df = clean_data().head(30)
    load_demo_incidents(df)
    first = IncidentReport.query.order_by(IncidentReport.incident_time).first()
    expected = df["incident_time"].min().to_pydatetime() - timedelta(minutes=330)
    assert first.incident_time == expected


def test_page_shows_only_approved_markers_without_text(user_client, user):
    load_demo_incidents(clean_data().head(40))
    db.session.add(IncidentReport(user_id=user.id, latitude=17.4, longitude=76.9,
                                  description="A pending report that nobody has approved yet.",
                                  severity=3, status="pending"))
    db.session.commit()

    page = user_client.get("/heatmap").data
    assert b"Showing 40 approved reports" in page
    assert b"pending report that nobody" not in page
    assert clean_data().iloc[0]["description"].encode() not in page