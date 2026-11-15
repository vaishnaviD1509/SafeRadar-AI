from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.forms.report import SEVERITY_CHOICES, ReportForm
from app.services.reports import count_recent_reports, create_report, list_user_reports
from app.utils.timeutils import local_now

reports_bp = Blueprint("reports", __name__)


@reports_bp.route("/report", methods=["GET", "POST"])
@login_required
def new_report():
    limit = current_app.config["MAX_REPORTS_PER_DAY"]
    used = count_recent_reports(current_user)
    form = ReportForm()

    if form.is_submitted() and used >= limit:
        flash(f"You can submit up to {limit} reports per day. Please try again tomorrow.", "warning")
        return redirect(url_for("reports.my_reports"))

    if form.validate_on_submit():
        create_report(
            current_user,
            description=form.description.data,
            severity=form.severity.data,
            local_time=form.incident_time.data,
            latitude=float(form.latitude.data),
            longitude=float(form.longitude.data),
            place_name=form.place_name.data or None,
        )
        flash("Thank you. Your report was submitted and will appear after review.", "success")
        return redirect(url_for("reports.my_reports"))

    now = local_now().replace(second=0, microsecond=0)
    if not form.is_submitted():
        form.incident_time.data = now  # pre-fill with the current time

    return render_template(
        "reports/new.html",
        form=form,
        severity_choices=SEVERITY_CHOICES,
        now_local=now.strftime("%Y-%m-%dT%H:%M"),
        map_center=current_app.config["DEFAULT_MAP_CENTER"],
        map_zoom=current_app.config["DEFAULT_MAP_ZOOM"],
        limit=limit,
        remaining=max(limit - used, 0),
    )


@reports_bp.route("/my-reports")
@login_required
def my_reports():
    return render_template("reports/my_reports.html", reports=list_user_reports(current_user))