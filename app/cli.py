"""Custom commands:  flask --app run init-db   and   flask --app run create-admin"""
import click

from app.extensions import db
from app.models import Admin, User


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