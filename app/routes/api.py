"""Small JSON endpoints used by the maps and, later, the route planner.

GET /api/risk?lat=17.33&lon=76.83                    risk estimate now
GET /api/risk?lat=..&lon=..&when=2026-11-20T21:30    estimate for a local date and time
"""
import math
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_login import current_user

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