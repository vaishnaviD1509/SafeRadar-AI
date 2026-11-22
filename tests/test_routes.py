import logging

import pytest
import requests

from app.ml.risk_dataset import cell_center, cell_id, cell_of
from app.ml.risk_model import save_artifact
from app.ml.zones import CENTER_LAT, CENTER_LON
from app.services.route_risk import recommend, score_route
from app.services.routing import (
    NoRouteError, RoutingError, build_url, fetch_routes, haversine_m, sample_along, thin,
)
from tests.helpers import login, make_user
from tests.risk_helpers import trained

START = (17.33, 76.83)
END = (17.34, 76.84)
PATH = [(17.33, 76.83), (17.335, 76.83), (17.34, 76.84)]

QUERY = "from_lat=17.33&from_lon=76.83&to_lat=17.34&to_lon=76.84"
LOW = {"Low": 1.0, "Moderate": 0.0, "High": 0.0}
MODERATE = {"Low": 0.0, "Moderate": 1.0, "High": 0.0}
HIGH = {"Low": 0.0, "Moderate": 0.0, "High": 1.0}


# ---------- a fake routing server (no internet in the tests) ----------

class FakeResponse:
    def __init__(self, payload=None, status=200, json_error=False):
        self._payload = payload
        self.status_code = status
        self._json_error = json_error

    def json(self):
        if self._json_error:
            raise ValueError("not json")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def osrm_ok(*routes):
    """routes: (distance in m, duration in s, [(lat, lon), ...]). OSRM sends longitude first."""
    return {"code": "Ok", "routes": [
        {"distance": distance, "duration": duration,
         "geometry": {"type": "LineString", "coordinates": [[lon, lat] for lat, lon in points]}}
        for distance, duration, points in routes
    ]}


def fake_osrm(monkeypatch, response=None, error=None):
    """Replace requests.get. Returns the list that records every call."""
    calls = []

    def fake_get(url, params=None, timeout=None, headers=None):
        calls.append({"url": url, "params": params, "timeout": timeout})
        if error is not None:
            raise error
        return response

    monkeypatch.setattr(requests, "get", fake_get)
    return calls


def route_url(extra=""):
    return "/api/route?" + QUERY + extra


@pytest.fixture
def with_model(app, tmp_path):
    path = tmp_path / "risk_model.joblib"
    save_artifact(trained()["artifact"], path)
    app.config["RISK_MODEL_PATH"] = str(path)
    return path


@pytest.fixture
def user_client(client):
    user = make_user()
    login(client, email=user.email)
    return client


def modelled_cell():
    return next(iter(trained()["artifact"]["profile"].values()))


def inside_cell(entry):
    """A short route that stays inside one modelled grid square."""
    return [(entry["cell_lat"], entry["cell_lon"]), (entry["cell_lat"] + 0.001, entry["cell_lon"] + 0.001)]


# ---------- distance, sampling and thinning ----------

def test_haversine_one_degree_of_latitude():
    assert haversine_m(17.0, 76.0, 18.0, 76.0) == pytest.approx(111195, rel=1e-3)
    assert haversine_m(17.3, 76.8, 17.3, 76.8) == 0


def test_samples_are_spaced_and_keep_both_ends():
    line = [(17.0, 76.0), (17.009, 76.0)]            # about 1 km due north
    samples = sample_along(line, spacing_m=100)
    assert samples[0] == line[0] and samples[-1] == line[-1]
    assert 11 <= len(samples) <= 13
    gaps = [haversine_m(*samples[i], *samples[i + 1]) for i in range(len(samples) - 1)]
    assert all(abs(gap - 100) < 1 for gap in gaps[:-1])


def test_long_routes_never_give_too_many_samples():
    line = [(17.0, 76.0), (17.5, 76.0)]               # about 55 km
    samples = sample_along(line, spacing_m=100, max_samples=50)
    assert len(samples) <= 51
    assert samples[-1] == line[-1]


def test_sampling_edge_cases():
    assert sample_along([]) == []
    assert sample_along([(17.0, 76.0)]) == [(17.0, 76.0)]
    assert sample_along([(17.0, 76.0), (17.0, 76.0)]) == [(17.0, 76.0)]


def test_thin_keeps_first_and_last():
    points = [(17.0 + i * 0.0001, 76.0) for i in range(1000)]
    thinned = thin(points, 100)
    assert len(thinned) <= 100
    assert thinned[0] == points[0] and thinned[-1] == points[-1]
    assert thin(points[:5], 100) == points[:5]


# ---------- talking to the routing service ----------

def test_url_puts_longitude_first_and_uses_the_configured_server(app):
    app.config["OSRM_BASE_URL"] = "https://osrm.example.test/"
    app.config["OSRM_PROFILE"] = "foot"
    assert build_url(START, END) == (
        "https://osrm.example.test/route/v1/foot/76.830000,17.330000;76.840000,17.340000")


def test_request_asks_for_alternatives_and_full_geometry(app, monkeypatch):
    calls = fake_osrm(monkeypatch, FakeResponse(osrm_ok((1000, 600, PATH))))
    fetch_routes(START, END)
    assert len(calls) == 1
    assert calls[0]["params"] == {"alternatives": "3", "overview": "full",
                                  "geometries": "geojson", "steps": "false"}
    assert calls[0]["timeout"] == app.config["OSRM_TIMEOUT_SECONDS"]


def test_a_server_that_only_knows_one_alternative_is_asked_again(app, monkeypatch):
    asked = []

    def fake_get(url, params=None, timeout=None, headers=None):
        asked.append(params["alternatives"])
        if params["alternatives"] == "3":
            return FakeResponse({"code": "InvalidQuery"}, status=400)
        return FakeResponse(osrm_ok((1000, 600, PATH)))

    monkeypatch.setattr(requests, "get", fake_get)
    routes = fetch_routes(START, END)
    assert asked == ["3", "true"]
    assert len(routes) == 1


def test_a_network_problem_is_not_retried(app, monkeypatch):
    calls = fake_osrm(monkeypatch, error=requests.ConnectionError("down"))
    with pytest.raises(RoutingError):
        fetch_routes(START, END)
    assert len(calls) == 1


def test_routes_are_parsed_to_latitude_then_longitude(app, monkeypatch):
    fake_osrm(monkeypatch, FakeResponse(osrm_ok((1000, 600, PATH), (1200, 540, PATH))))
    routes = fetch_routes(START, END)
    assert len(routes) == 2
    assert routes[0]["points"][0] == (17.33, 76.83)
    assert routes[0]["distance_m"] == 1000.0 and routes[0]["duration_s"] == 600.0


def test_at_most_three_routes_are_used(app, monkeypatch):
    fake_osrm(monkeypatch, FakeResponse(osrm_ok(*[(1000 + i, 600, PATH) for i in range(4)])))
    assert len(fetch_routes(START, END)) == 3


@pytest.mark.parametrize("response", [
    FakeResponse({"code": "NoRoute"}, status=400),
    FakeResponse({"code": "NoRoute"}, status=200),
    FakeResponse({"code": "NoSegment"}, status=400),
])
def test_no_route_is_reported_as_such(app, monkeypatch, response):
    fake_osrm(monkeypatch, response)
    with pytest.raises(NoRouteError):
        fetch_routes(START, END)


@pytest.mark.parametrize("response", [
    FakeResponse(json_error=True, status=500),
    FakeResponse(json_error=True, status=200),
    FakeResponse({"code": "InvalidQuery"}, status=200),
    FakeResponse({"code": "Ok", "routes": []}),
    FakeResponse({"code": "Ok", "routes": [{"distance": 1, "duration": 1}]}),
    FakeResponse({"code": "Ok", "routes": [{"distance": 1, "duration": 1,
                                            "geometry": {"coordinates": [["a", "b"]]}}]}),
    FakeResponse({"code": "Ok", "routes": [{"distance": 1, "duration": 1,
                                            "geometry": {"coordinates": [[76.8, 95.0], [76.9, 17.3]]}}]}),
    FakeResponse({"code": "Ok", "routes": [{"distance": 1, "duration": 1,
                                            "geometry": {"coordinates": [[76.8, 17.3]]}}]}),
])
def test_unusable_answers_are_routing_errors(app, monkeypatch, response):
    fake_osrm(monkeypatch, response)
    with pytest.raises(RoutingError) as problem:
        fetch_routes(START, END)
    assert not isinstance(problem.value, NoRouteError)


@pytest.mark.parametrize("error", [
    requests.ConnectionError("could not connect to 17.33,76.83"),
    requests.Timeout("timed out for 17.33,76.83"),
])
def test_network_problems_are_routing_errors_without_details(app, monkeypatch, error):
    fake_osrm(monkeypatch, error=error)
    with pytest.raises(RoutingError) as problem:
        fetch_routes(START, END)
    assert "17.33" not in str(problem.value)


# ---------- scoring ----------

def cells():
    row, col = cell_of(CENTER_LAT, CENTER_LON)
    return {
        "a": (cell_center(row, col), cell_id(row, col)),
        "b": (cell_center(row, col + 1), cell_id(row, col + 1)),
        "c": (cell_center(row, col + 2), cell_id(row, col + 2)),
    }


def inside(centre):
    """A short route that stays inside the grid square around `centre`."""
    return [centre, (centre[0] + 0.001, centre[1] + 0.001)]


def test_score_averages_the_expected_level():
    grid = cells()
    lookup = {grid["a"][1]: HIGH, grid["b"][1]: LOW}
    samples = [grid["a"][0], grid["a"][0], grid["b"][0], grid["b"][0]]
    score = score_route(samples, lookup)
    assert score["risk_index"] == 50.0
    assert score["coverage_pct"] == 100 and score["unknown_pct"] == 0
    assert score["high_pct"] == 50.0 and score["low_pct"] == 50.0 and score["moderate_pct"] == 0.0


def test_a_high_route_scores_above_a_low_route():
    grid = cells()
    lookup = {grid["a"][1]: HIGH, grid["b"][1]: LOW}
    high = score_route([grid["a"][0]] * 4, lookup)
    low = score_route([grid["b"][0]] * 4, lookup)
    assert high["risk_index"] == 100.0
    assert low["risk_index"] == 0.0


def test_unknown_parts_are_never_counted_as_low():
    grid = cells()
    lookup = {grid["a"][1]: HIGH}
    score = score_route([grid["a"][0]] * 3 + [grid["c"][0]], lookup)
    assert score["coverage_pct"] == 75 and score["unknown_pct"] == 25
    assert score["risk_index"] == 100.0                  # the unknown quarter did not dilute it
    assert score["low_pct"] == 0.0


def test_a_route_with_too_little_data_gets_no_index():
    grid = cells()
    lookup = {grid["a"][1]: LOW}
    score = score_route([grid["a"][0]] + [grid["c"][0]] * 3, lookup)    # 25% covered
    assert score["coverage_pct"] == 25
    assert score["risk_index"] is None


def test_routes_outside_the_model_area_are_unknown():
    score = score_route([(20.0, 80.0), (20.01, 80.0)], {})
    assert score["coverage_pct"] == 0 and score["unknown_pct"] == 100
    assert score["risk_index"] is None


def test_scoring_an_empty_route_does_not_crash():
    assert score_route([], {})["risk_index"] is None


# ---------- recommendation ----------

def planned(route_id, minutes, index):
    risk = None if index == "none" else {"risk_index": index}
    return {"id": route_id, "duration_min": minutes, "risk": risk}


def test_a_clear_difference_suggests_the_lower_risk_route_with_the_extra_time():
    result = recommend([planned(1, 10, 60.0), planned(2, 14, 40.0)])
    assert result["fastest_id"] == 1 and result["lowest_risk_id"] == 2
    assert result["confidence"] == "clear"
    assert result["message"].startswith("Suggested: Route 2")
    assert "longer" in result["message"] and "4" in result["message"]
    assert "does not mean safe" in result["message"]


def test_fastest_and_lowest_can_be_the_same_route():
    result = recommend([planned(1, 10, 20.0), planned(2, 14, 40.0)])
    assert result["fastest_id"] == 1 and result["lowest_risk_id"] == 1
    assert result["confidence"] == "clear"
    assert "also the fastest" in result["message"]


def test_a_small_difference_is_suggested_but_called_small():
    result = recommend([planned(1, 10, 50.0), planned(2, 14, 53.0)])
    assert result["lowest_risk_id"] == 1
    assert result["confidence"] == "slight"
    assert "slightly lower" in result["message"] and "small" in result["message"]


def test_identical_scores_give_no_suggestion():
    result = recommend([planned(1, 10, 50.0), planned(2, 14, 50.0)])
    assert result["lowest_risk_id"] is None and result["confidence"] is None
    assert "same estimated risk" in result["message"]


def test_no_route_is_suggested_when_only_one_has_data():
    result = recommend([planned(1, 10, 20.0), planned(2, 14, "none")])
    assert result["lowest_risk_id"] is None and result["confidence"] is None
    assert "too little data" in result["message"]
    assert "Route 1 is the fastest" in result["message"]


def test_routes_without_data_are_left_out_of_the_ranking():
    result = recommend([planned(1, 10, 20.0), planned(2, 14, 40.0), planned(3, 12, "none")])
    assert result["lowest_risk_id"] == 1
    assert "left out" in result["message"]


def test_one_route_has_nothing_to_compare():
    result = recommend([planned(1, 10, 20.0)])
    assert result["lowest_risk_id"] is None
    assert "only one route" in result["message"].lower()
    assert "further apart" in result["message"]


def test_without_a_model_routes_are_not_compared_by_risk():
    result = recommend([planned(1, 10, "none"), planned(2, 14, "none")], risk_model=False)
    assert result["lowest_risk_id"] is None
    assert "not been trained" in result["message"]


# ---------- the API ----------

def test_route_api_needs_login(client, monkeypatch):
    calls = fake_osrm(monkeypatch, FakeResponse(osrm_ok((1000, 600, PATH))))
    response = client.get(route_url())
    assert response.status_code == 401
    assert response.get_json()["error"] == "Please log in."
    assert calls == []


@pytest.mark.parametrize("query", [
    "",
    "?from_lat=17.33&from_lon=76.83",
    "?from_lat=abc&from_lon=76.83&to_lat=17.34&to_lon=76.84",
    "?from_lat=nan&from_lon=76.83&to_lat=17.34&to_lon=76.84",
    "?from_lat=95&from_lon=76.83&to_lat=17.34&to_lon=76.84",
    "?from_lat=17.33&from_lon=76.83&to_lat=17.34&to_lon=181",
    "?from_lat=17.33&from_lon=76.83&to_lat=17.33&to_lon=76.83",      # same place
    "?from_lat=17.33&from_lon=76.83&to_lat=18.50&to_lon=76.84",      # too far apart
    "?from_lat=17.33&from_lon=76.83&to_lat=17.34&to_lon=76.84&when=tomorrow",
])
def test_route_api_rejects_bad_input_without_calling_the_service(user_client, monkeypatch, query):
    calls = fake_osrm(monkeypatch, FakeResponse(osrm_ok((1000, 600, PATH))))
    response = user_client.get("/api/route" + query)
    assert response.status_code == 400
    assert "error" in response.get_json()
    assert calls == []


def test_route_api_without_a_model_still_returns_routes(user_client, monkeypatch):
    fake_osrm(monkeypatch, FakeResponse(osrm_ok((1000, 900, PATH), (1200, 600, PATH))))
    response = user_client.get(route_url())
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    body = response.get_json()
    assert body["status"] == "ok"
    assert body["risk_model"] is False
    assert [r["risk"] for r in body["routes"]] == [None, None]
    assert body["recommendation"]["lowest_risk_id"] is None
    assert "not been trained" in body["recommendation"]["message"]
    fastest = next(r for r in body["routes"] if r["id"] == body["recommendation"]["fastest_id"])
    assert fastest["duration_min"] == 10.0 and "Fastest" in fastest["labels"]


def test_route_api_scores_routes_with_the_model(user_client, with_model, monkeypatch):
    path = inside_cell(modelled_cell())
    fake_osrm(monkeypatch, FakeResponse(osrm_ok((120, 90, path), (150, 100, path))))
    body = user_client.get(route_url("&when=2026-11-20T22:30")).get_json()
    assert body["risk_model"] is True
    assert body["slot"] == "Night" and body["is_weekend"] is False
    assert body["synthetic"] is True
    assert "not a guarantee" in body["disclaimer"]
    for route in body["routes"]:
        assert route["risk"]["coverage_pct"] == 100
        assert 0 <= route["risk"]["risk_index"] <= 100
    # identical routes cannot be told apart
    assert body["recommendation"]["lowest_risk_id"] is None
    assert "same estimated risk" in body["recommendation"]["message"]


def fake_grid(monkeypatch, lookup):
    """Give the route planner a made-up risk grid, so the suggestion can be tested exactly."""
    def build(slot, weekend):
        return {"synthetic": True,
                "cells": [{"id": cid, "probabilities": probabilities} for cid, probabilities in lookup.items()]}
    monkeypatch.setattr("app.services.route_risk.build_risk_grid", build)


def test_route_api_suggests_the_lower_risk_route(user_client, monkeypatch):
    grid = cells()
    fake_grid(monkeypatch, {grid["a"][1]: HIGH, grid["b"][1]: LOW})
    fake_osrm(monkeypatch, FakeResponse(osrm_ok(
        (800, 600, inside(grid["a"][0])),          # fastest, but through a High square
        (900, 900, inside(grid["b"][0])),          # slower, through a Low square
    )))
    body = user_client.get(route_url()).get_json()
    recommendation = body["recommendation"]
    assert recommendation["fastest_id"] == 1
    assert recommendation["lowest_risk_id"] == 2
    assert recommendation["confidence"] == "clear"
    assert recommendation["message"].startswith("Suggested: Route 2")
    assert "longer" in recommendation["message"]
    first, second = body["routes"]
    assert first["labels"] == ["Fastest"]
    assert second["labels"] == ["Lowest estimated risk"]
    assert first["risk"]["risk_index"] == 100.0 and second["risk"]["risk_index"] == 0.0


def test_route_api_ranks_three_routes(user_client, monkeypatch):
    grid = cells()
    fake_grid(monkeypatch, {grid["a"][1]: HIGH, grid["b"][1]: LOW, grid["c"][1]: MODERATE})
    fake_osrm(monkeypatch, FakeResponse(osrm_ok(
        (800, 600, inside(grid["a"][0])),
        (900, 900, inside(grid["b"][0])),
        (850, 700, inside(grid["c"][0])),
    )))
    body = user_client.get(route_url()).get_json()
    assert len(body["routes"]) == 3
    assert [r["risk"]["risk_index"] for r in body["routes"]] == [100.0, 0.0, 50.0]
    assert body["recommendation"]["lowest_risk_id"] == 2


def test_route_api_departure_time_sets_the_slot(user_client, with_model, monkeypatch):
    path = inside_cell(modelled_cell())
    fake_osrm(monkeypatch, FakeResponse(osrm_ok((120, 90, path))))
    body = user_client.get(route_url("&when=2026-11-21T09:00")).get_json()      # a Saturday
    assert body["slot"] == "Morning" and body["slot_index"] == 0
    assert body["is_weekend"] is True


def test_unknown_routes_get_no_score_and_no_recommendation(user_client, with_model, monkeypatch):
    far = [(CENTER_LAT + 0.2, CENTER_LON + 0.2), (CENTER_LAT + 0.201, CENTER_LON + 0.2)]
    fake_osrm(monkeypatch, FakeResponse(osrm_ok((120, 90, far), (150, 100, far))))
    body = user_client.get(route_url()).get_json()
    for route in body["routes"]:
        assert route["risk"]["coverage_pct"] == 0
        assert route["risk"]["risk_index"] is None
    assert body["recommendation"]["lowest_risk_id"] is None
    assert "too little data" in body["recommendation"]["message"]


def test_long_geometry_is_thinned_for_drawing(user_client, monkeypatch):
    line = [(17.33 + i * 0.00001, 76.83) for i in range(2000)]
    fake_osrm(monkeypatch, FakeResponse(osrm_ok((2200, 600, line))))
    geometry = user_client.get(route_url()).get_json()["routes"][0]["geometry"]
    assert len(geometry) <= 600
    assert geometry[0] == [17.33, 76.83]


def test_route_api_exposes_only_route_data(user_client, monkeypatch):
    fake_osrm(monkeypatch, FakeResponse(osrm_ok((1000, 600, PATH))))
    body = user_client.get(route_url()).get_json()
    assert set(body) <= {"status", "travel_mode", "slot", "slot_index", "slot_hours", "is_weekend",
                         "risk_model", "synthetic", "disclaimer", "routes", "recommendation"}
    assert set(body["routes"][0]) == {"id", "distance_km", "duration_min", "geometry", "risk", "labels"}


def test_no_route_gives_a_404_message(user_client, monkeypatch):
    fake_osrm(monkeypatch, FakeResponse({"code": "NoRoute"}, status=400))
    response = user_client.get(route_url())
    assert response.status_code == 404
    assert response.get_json()["status"] == "no_route"


@pytest.mark.parametrize("error", [
    requests.ConnectionError("could not connect to 17.33,76.83"),
    requests.Timeout("timed out for 17.33,76.83"),
])
def test_service_down_gives_a_502_and_never_leaks_coordinates(user_client, monkeypatch, caplog, error):
    fake_osrm(monkeypatch, error=error)
    with caplog.at_level(logging.DEBUG):
        response = user_client.get(route_url())
    assert response.status_code == 502
    assert response.get_json()["status"] == "unavailable"
    assert "17.33" not in response.get_data(as_text=True)
    assert "17.33" not in caplog.text and "76.83" not in caplog.text


# ---------- the page ----------

def test_route_page_needs_login(client):
    response = client.get("/routes")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_route_page_explains_privacy_and_uncertainty(user_client):
    page = user_client.get("/routes").data
    text = b" ".join(page.split())            # line breaks in the HTML do not matter to a reader
    assert b'id="route-map"' in page
    assert b"external routing service" in text
    assert b"does not save them" in text
    assert b"unknown does not mean safe" in text
    assert b"has not been trained yet" in text          # no model in the test setup


def test_route_page_without_the_model_warning_when_a_model_exists(user_client, with_model):
    assert b"has not been trained yet" not in user_client.get("/routes").data