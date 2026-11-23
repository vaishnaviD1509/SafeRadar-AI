"""SOS endpoints (Phase 10).

POST /sos/start                 start (or reuse) an alert from the person's position
POST /sos/<id>/update           send a newer position
POST /sos/<id>/end              stop sharing ("resolved" or "cancelled")
GET  /share/<token>             the public page contacts open (no login)
GET  /share/<token>/location    the same information as JSON, polled by that page

Only the owner can update or end an alert. The public pages are marked private: they are
never cached, never indexed by search engines and never leak their address in a Referer header.
"""
from flask import Blueprint, abort, jsonify, make_response, render_template, request, url_for
from flask_login import current_user

from app.services.sos import (
    AlertEnded, TooManyAlerts, alert_view, end_alert, get_alert_by_token, get_owned_alert,
    public_view, start_alert, update_location,
)
from app.utils.timeutils import to_local

sos_bp = Blueprint("sos", __name__, url_prefix="/sos")
share_bp = Blueprint("share", __name__)


def _json(payload, status=200):
    response = jsonify(payload)
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    return response


def _private(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


# ---------- the owner's endpoints ----------

@sos_bp.route("/start", methods=["POST"])
def start():
    if not current_user.is_authenticated:
        return _json({"error": "Please log in."}, 401)
    data = _body()
    if data is None:
        return _json({"error": "Send the location as JSON."}, 400)

    try:
        alert, created = start_alert(
            current_user, data.get("latitude"), data.get("longitude"), data.get("accuracy"))
    except ValueError as error:
        return _json({"error": str(error)}, 400)
    except TooManyAlerts:
        return _json({"error": "You have started too many SOS alerts in the last hour. "
                               "If you need help, call 112."}, 429)

    return _json({"status": "ok", "created": created, "alert": alert_view(current_user, alert)},
                 201 if created else 200)


@sos_bp.route("/<int:alert_id>/update", methods=["POST"])
def update(alert_id):
    if not current_user.is_authenticated:
        return _json({"error": "Please log in."}, 401)
    alert = get_owned_alert(current_user, alert_id)
    if alert is None:
        return _json({"error": "That SOS was not found."}, 404)
    data = _body()
    if data is None:
        return _json({"error": "Send the location as JSON."}, 400)

    try:
        update_location(alert, data.get("latitude"), data.get("longitude"), data.get("accuracy"))
    except ValueError as error:
        return _json({"error": str(error)}, 400)
    except AlertEnded:
        return _json({"error": "This SOS has ended.", "state": alert.status}, 409)

    return _json({"status": "ok", "updated": to_local(alert.updated_at).strftime("%I:%M:%S %p")})


@sos_bp.route("/<int:alert_id>/end", methods=["POST"])
def end(alert_id):
    if not current_user.is_authenticated:
        return _json({"error": "Please log in."}, 401)
    alert = get_owned_alert(current_user, alert_id)
    if alert is None:
        return _json({"error": "That SOS was not found."}, 404)

    data = _body() or {}
    status = data.get("status", "resolved")
    if status not in ("resolved", "cancelled"):
        return _json({"error": "status must be 'resolved' or 'cancelled'."}, 400)

    end_alert(alert, status)
    return _json({"status": "ok", "state": alert.status})


# ---------- the public share pages ----------

@share_bp.route("/share/<token>")
def live(token):
    alert = get_alert_by_token(token)
    if alert is None:
        abort(404)
    response = make_response(render_template(
        "share/live.html",
        state=public_view(alert),
        state_url=url_for("share.location", token=alert.share_token),
    ))
    return _private(response)


@share_bp.route("/share/<token>/location")
def location(token):
    alert = get_alert_by_token(token)
    if alert is None:
        return _private(_json({"error": "This link is not valid."}, 404))
    return _private(_json({"status": "ok", **public_view(alert)}))