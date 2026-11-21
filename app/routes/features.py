"""Feature pages.

/heatmap is real (Phase 8). The others are still placeholders:
    /routes -> Phase 9    /sos -> Phase 10
(The report page became real in Phase 4: see routes/reports.py.)
"""
from flask import Blueprint, current_app, render_template
from flask_login import login_required

from app.ml.risk_dataset import SLOT_HOURS, SLOT_NAMES
from app.services.heatmap import current_slot_and_day, get_heatmap_markers
from app.services.risk import get_model_info

features_bp = Blueprint("features", __name__)


def coming_soon(title, phase, description):
    return render_template(
        "features/coming_soon.html", title=title, phase=phase, description=description
    )


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
    return coming_soon(
        "Safer route planner", 9,
        "Compare routes between two places by estimated risk, not only by distance.",
    )


@features_bp.route("/sos")
@login_required
def sos():
    return coming_soon(
        "Emergency SOS", 10,
        "Capture your location and create a sharing link for your trusted contacts.",
    )