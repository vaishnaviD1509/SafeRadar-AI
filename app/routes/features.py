"""Feature pages.

/heatmap (Phase 8), /routes (Phase 9) and /sos (Phase 10) are all real now.
The JSON endpoints behind SOS and the public share pages live in routes/sos.py.
"""
from flask import Blueprint, current_app, render_template
from flask_login import current_user, login_required

from app.ml.risk_dataset import SLOT_HOURS, SLOT_NAMES
from app.services.heatmap import current_slot_and_day, get_heatmap_markers
from app.services.risk import get_model_info
from app.services.sos import alert_view, get_live_alert, is_local_address
from app.utils.timeutils import local_now

features_bp = Blueprint("features", __name__)


@features_bp.route("/heatmap")
@login_required
def heatmap():
    slot, weekend = current_slot_and_day()
    return render_template(
        "features/heatmap.html",
        markers=get_heatmap_markers(),
        model_ready=get_model_info() is not None,
        slot=slot,
        weekend=weekend,
        slot_names=SLOT_NAMES,
        slot_hours=SLOT_HOURS,
        map_center=current_app.config["DEFAULT_MAP_CENTER"],
        map_zoom=current_app.config["DEFAULT_MAP_ZOOM"],
    )


@features_bp.route("/routes")
@login_required
def route_planner():
    now = local_now().replace(second=0, microsecond=0)
    return render_template(
        "features/route_planner.html",
        model_ready=get_model_info() is not None,
        now_local=now.strftime("%Y-%m-%dT%H:%M"),
        map_center=current_app.config["DEFAULT_MAP_CENTER"],
        map_zoom=current_app.config["DEFAULT_MAP_ZOOM"],
    )


@features_bp.route("/sos")
@login_required
def sos():
    alert = get_live_alert(current_user)
    return render_template(
        "features/sos.html",
        active=alert_view(current_user, alert) if alert else None,
        contacts=current_user.contacts,
        local_only=is_local_address(),
        duration_hours=current_app.config.get("SOS_DURATION_MINUTES", 240) / 60,
    )