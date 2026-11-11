"""Application factory for SafeRadar AI."""
import os

from flask import Flask, render_template

from app.config import config_by_name
from app.extensions import csrf, db


def create_app(config_name=None):
    app = Flask(__name__)

    config_name = config_name or os.environ.get("APP_ENV", "development")
    app.config.from_object(config_by_name[config_name])

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is not set. Add it to your .env file.")

    # The SQLite database file is stored in the instance folder.
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)

    from app.routes import register_blueprints
    register_blueprints(app)
    register_error_handlers(app)

    return app


def register_error_handlers(app):
    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        return render_template("errors/500.html"), 500