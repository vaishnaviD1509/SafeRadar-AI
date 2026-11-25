"""Admin pages (Phase 11): overview, report review queue, and user management.

Every route needs an administrator: logged-out visitors go to the login page and regular
users get a 403 error. Changes are POST requests with a CSRF token.
"""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.extensions import db
from app.forms.admin import ReviewForm
from app.models import IncidentReport, User
from app.services.admin import (
    ReviewError, get_admin_stats, list_reports, list_users, normalise_filters, report_view,
    review_report, set_user_active,
)
from app.utils.decorators import admin_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

STATUS_OPTIONS = [("pending", "Pending"), ("approved", "Approved"), ("rejected", "Rejected"), ("all", "All")]
SOURCE_OPTIONS = [("real", "Real reports"), ("synthetic", "Synthetic demo data"), ("all", "All")]
DECISION_WORDS = {"approved": "approved", "rejected": "rejected", "pending": "returned to pending"}


@admin_bp.route("/")
@admin_required
def dashboard():
    return render_template("admin/dashboard.html", stats=get_admin_stats())


@admin_bp.route("/reports")
@admin_required
def reports():
    status, source = normalise_filters(request.args.get("status"), request.args.get("source"))
    needs_category = request.args.get("needs_category") == "1"
    page_number = max(request.args.get("page", 1, type=int) or 1, 1)

    page = list_reports(status, source, needs_category, page_number)
    return render_template(
        "admin/reports.html",
        page=page,
        reports=[report_view(report) for report in page.items],
        filters={"status": status, "source": source, "needs_category": needs_category},
        status_options=STATUS_OPTIONS,
        source_options=SOURCE_OPTIONS,
    )


@admin_bp.route("/reports/<int:report_id>", methods=["GET", "POST"])
@admin_required
def report_detail(report_id):
    report = db.session.get(IncidentReport, report_id)
    if report is None:
        abort(404)

    form = ReviewForm()
    detail_url = url_for("admin.report_detail", report_id=report.id)

    if form.validate_on_submit():
        decision = request.form.get("decision")
        try:
            review_report(report, current_user, decision, form.category.data)
        except ReviewError as error:
            flash(str(error), "danger")
            return redirect(detail_url)
        flash(f"Report #{report.id} {DECISION_WORDS[decision]}.", "success")
        return redirect(detail_url if decision == "pending" else url_for("admin.reports"))

    if form.is_submitted():                       # a bad category or a missing CSRF token
        for errors in form.errors.values():
            for error in errors:
                flash(error, "danger")
        return redirect(detail_url)

    form.category.data = report.category or ""
    return render_template("admin/report_detail.html", report=report_view(report), form=form)


@admin_bp.route("/users")
@admin_required
def users():
    rows, total = list_users()
    return render_template("admin/users.html", rows=rows, total=total)


@admin_bp.route("/users/<int:user_id>/active", methods=["POST"])
@admin_required
def set_active(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        abort(404)
    active = request.form.get("active") == "1"
    try:
        set_user_active(current_user, user, active)
    except ValueError as error:
        flash(str(error), "danger")
    else:
        flash(f"{user.full_name} is now {'active' if active else 'deactivated'}.", "success")
    return redirect(url_for("admin.users"))