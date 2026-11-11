from flask import Blueprint, current_app, jsonify, render_template

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    return render_template("index.html")


@main_bp.route("/health")
def health():
    """Simple status check, useful for testing that the app is running."""
    return jsonify(status="ok", app="SafeRadar AI", debug=current_app.debug)