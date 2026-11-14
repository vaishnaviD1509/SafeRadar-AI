from flask import Blueprint, render_template

from app.models import User
from app.utils.decorators import admin_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
@admin_required
def dashboard():
    # Placeholder. The full admin dashboard is built in Phase 11.
    stats = {
        "total_users": User.query.filter_by(role="user").count(),
        "total_admins": User.query.filter_by(role="admin").count(),
    }
    return render_template("admin/dashboard.html", stats=stats)