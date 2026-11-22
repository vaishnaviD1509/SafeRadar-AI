"""Small JSON endpoints used by the maps and the route planner.

GET /api/risk?lat=17.33&lon=76.83                    risk estimate now
GET /api/risk?lat=..&lon=..&when=2026-11-20T21:30    estimate for a local date and time
GET /api/risk-grid                                   heatmap squares for the current time slot
GET /api/risk-grid?slot=3&weekend=1                  squares for a chosen slot (0 to 3) and day type
GET /api/route?from_lat=..&from_lon=..&to_lat=..&to_lon=..[&when=...]   routes scored by risk
"""
import math
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.services.heatmap import build_risk_grid
from app.services.risk import estimate_risk
from app.services.route_risk import plan_routes
from app.services.routing import MAX_TRIP_KM, MIN_TRIP_M, NoRouteError, RoutingError, haversine_m

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _json(payload, status=200):
    response = jsonify(payload)
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    return response


def _number(name, low, high):
    try:
        value = float(request.args.get(name, ""))
    except ValueError:
        raise ValueError(f"'{name}' must be a number.")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"'{name}' must be between {low} and {high}.")
    return value


def _choice(name, allowed):
    """A whole number from `allowed`, or None when the parameter is not given."""
    raw = request.args.get(name)
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"'{name}' must be a whole number.")
    if value not in allowed:
        raise ValueError(f"'{name}' must be one of {', '.join(str(v) for v in allowed)}.")
    return value


def _when():
    """The optional local date and time in ?when=, or None."""
    if not request.args.get("when"):
        return None
    try:
        return datetime.strptime(request.args["when"], "%Y-%m-%dT%H:%M")
    except ValueError:
        raise ValueError("'when' must look like 2026-11-20T21:30 (local time).")


@api_bp.route("/risk")
def risk():
    if not current_user.is_authenticated:
        return _json({"error": "Please log in."}, 401)

    try:
        lat = _number("lat", -90, 90)
        lon = _number("lon", -180, 180)
        when = _when()
    except ValueError as error:
        return _json({"error": str(error)}, 400)

    result = estimate_risk(lat, lon, when)
    if result is None:
        return _json({"status": "unavailable",
                      "message": "The risk model has not been trained yet. No estimate is available."}, 503)
    return _json(result)


@api_bp.route("/risk-grid")
def risk_grid():
    if not current_user.is_authenticated:
        return _json({"error": "Please log in."}, 401)

    try:
        slot = _choice("slot", (0, 1, 2, 3))
        weekend = _choice("weekend", (0, 1))
    except ValueError as error:
        return _json({"error": str(error)}, 400)

    result = build_risk_grid(slot, weekend)
    if result is None:
        return _json({"status": "unavailable",
                      "message": "The risk model has not been trained yet. No estimate is available."}, 503)
    return _json(result)


@api_bp.route("/route")
def plan_route():
    if not current_user.is_authenticated:
        return _json({"error": "Please log in."}, 401)

    try:
        start = (_number("from_lat", -90, 90), _number("from_lon", -180, 180))
        end = (_number("to_lat", -90, 90), _number("to_lon", -180, 180))
        when = _when()
    except ValueError as error:
        return _json({"error": str(error)}, 400)

    trip_m = haversine_m(*start, *end)
    if trip_m < MIN_TRIP_M:
        return _json({"error": "The start and the end are the same place."}, 400)
    if trip_m > MAX_TRIP_KM * 1000:
        return _json({"error": f"Please choose places less than {MAX_TRIP_KM} km apart."}, 400)

    # The messages below never include the coordinates, and nothing here is logged.
    try:
        result = plan_routes(start, end, when)
    except NoRouteError:
        return _json({"status": "no_route", "message": "No route was found between these two places."}, 404)
    except RoutingError:
        return _json({"status": "unavailable",
                      "message": "The routing service could not be reached. Please try again later."}, 502)
    return _json(result)