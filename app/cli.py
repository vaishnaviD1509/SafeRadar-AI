"""Custom commands:
    flask --app run init-db
    flask --app run create-admin
    flask --app run review-report <id> approved|rejected|pending
    flask --app run classify-reports
"""
import click

from app.extensions import db
from app.models import Admin, IncidentReport, User
from app.models.base import utcnow
from app.services.classifier import load_model
from app.services.reports import apply_category


def register_commands(app):
    @app.cli.command("init-db")
    def init_db():
        """Create all database tables (safe to run again)."""
        db.create_all()
        click.echo("Database tables created.")

    @app.cli.command("create-admin")
    @click.option("--name", prompt="Full name")
    @click.option("--email", prompt="Email")
    @click.password_option()
    def create_admin(name, email, password):
        """Create an administrator, or promote an existing user to admin."""
        email = email.strip().lower()
        if len(password) < 8:
            raise click.ClickException("Password must be at least 8 characters.")

        user = User.query.filter_by(email=email).first()
        if user is None:
            user = User(full_name=name.strip(), email=email)
            user.set_password(password)
            db.session.add(user)

        user.role = "admin"
        if user.admin_profile is None:
            user.admin_profile = Admin()
        db.session.commit()
        click.echo(f"Admin ready: {email}")

    @app.cli.command("review-report")
    @click.argument("report_id", type=int)
    @click.argument("decision", type=click.Choice(["approved", "rejected", "pending"]))
    def review_report(report_id, decision):
        """Approve or reject a report. A temporary tool until the admin
        dashboard (Phase 11) lets administrators do this in the browser."""
        report = db.session.get(IncidentReport, report_id)
        if report is None:
            raise click.ClickException(f"No report with id {report_id}.")

        report.status = decision
        report.reviewed_at = None if decision == "pending" else utcnow()
        db.session.commit()
        click.echo(f"Report {report_id} is now {decision}.")

    @app.cli.command("classify-reports")
    def classify_reports():
        """Suggest categories for reports that have none yet.

        Useful for reports saved before the classifier was trained. Report text is
        never printed. An administrator still confirms every report.
        """
        if load_model() is None:
            raise click.ClickException(
                "No text classifier found. Train one first:  python -m scripts.train_classifier"
            )

        reports = IncidentReport.query.filter(IncidentReport.category.is_(None)).all()
        suggested = uncertain = 0
        for report in reports:
            result = apply_category(report)
            if result and result["status"] == "suggested":
                suggested += 1
            else:
                uncertain += 1
        db.session.commit()
        click.echo(f"Checked {len(reports)} reports without a category: "
                   f"{suggested} got a suggestion, {uncertain} left for an administrator.")