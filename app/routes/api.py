"""Small JSON endpoints used by the maps and, later, the route planner.

GET /api/risk?lat=17.33&lon=76.83                    risk estimate now
GET /api/risk?lat=..&lon=..&when=2026-11-20T21:30    estimate for a local date and time
GET /api/risk-grid                                   heatmap squares for the current time slot
GET /api/risk-grid?slot=3&weekend=1                  squares for a chosen slot (0 to 3) and day type
"""
import math
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_login import current_user

from app.services.heatmap import build_risk_grid
from app.services.risk import estimate_risk

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


@api_bp.route("/risk")
def risk():
    if not current_user.is_authenticated:
        return _json({"error": "Please log in."}, 401)

    try:
        lat = _number("lat", -90, 90)
        lon = _number("lon", -180, 180)
        when = None
        if request.args.get("when"):
            try:
                when = datetime.strptime(request.args["when"], "%Y-%m-%dT%H:%M")
            except ValueError:
                raise ValueError("'when' must look like 2026-11-20T21:30 (local time).")
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