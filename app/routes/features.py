"""Placeholder pages for features built in later phases.

They exist so the dashboard buttons and the navigation bar work.
Each one is replaced by the real page in its own phase:
    /heatmap -> Phase 8    /routes -> Phase 9    /sos -> Phase 10
(The report page became real in Phase 4: see routes/reports.py.)
"""
from flask import Blueprint, render_template
from flask_login import login_required

features_bp = Blueprint("features", __name__)


def coming_soon(title, phase, description):
    return render_template(
        "features/coming_soon.html", title=title, phase=phase, description=description
    )


@features_bp.route("/heatmap")
@login_required
def heatmap():
    return coming_soon(
        "Safety heatmap", 8,
        "An interactive map showing estimated risk levels and incident markers.",
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